import os
import time
import tempfile
import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app import __version__
from app.config import AppConfig
from app.database import (
    init_db,
    sanitize_tag_id,
    get_all_tags,
    get_tag_by_id,
    upsert_tag,
    upsert_reader,
    delete_unconfigured_tags,
    auto_discover_or_update_tag,
)
from app.audiobookshelf import AudiobookshelfClient
from app.mqtt_client import MQTTService
from app.main import app


def test_version_v36():
    """Verify system version is bumped to 0.3.6."""
    assert __version__ == "0.3.6"


# -----------------------------------------------------------------------------
# 1 & 3: Audiobookshelf 95% Completion Threshold & Active Cleanup
# -----------------------------------------------------------------------------

def test_abs_completion_threshold():
    """Verify media item is finished if isFinished == True OR progress >= 0.95."""
    client = AudiobookshelfClient("http://abs.local", "dummy_token")

    # Not finished: progress < 0.95 and isFinished is False
    assert client._is_item_finished({"isFinished": False, "progress": 0.94}) is False
    assert client._is_item_finished({"isFinished": False, "progress": 0.0}) is False
    assert client._is_item_finished({"progress": 0.9499}) is False

    # Finished: progress >= 0.95
    assert client._is_item_finished({"isFinished": False, "progress": 0.95}) is True
    assert client._is_item_finished({"isFinished": False, "progress": 0.98}) is True
    assert client._is_item_finished({"progress": 1.0}) is True

    # Finished: isFinished is True regardless of progress
    assert client._is_item_finished({"isFinished": True, "progress": 0.10}) is True
    assert client._is_item_finished({"isFinished": True}) is True

    # Empty / none
    assert client._is_item_finished({}) is False
    assert client._is_item_finished(None) is False


def test_abs_mark_as_finished():
    """Verify mark_as_finished issues PATCH request with isFinished=True."""
    client = AudiobookshelfClient("http://abs.local", "default_token")

    with patch("requests.patch") as mock_patch:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_patch.return_value = mock_resp

        res = client.mark_as_finished("item_abc_123", user_token="custom_token_456")
        assert res is True

        mock_patch.assert_called_once()
        args, kwargs = mock_patch.call_args
        assert args[0] == "http://abs.local/api/me/progress/item_abc_123"
        assert kwargs["headers"]["Authorization"] == "Bearer custom_token_456"
        assert kwargs["json"] == {"isFinished": True}


@patch("requests.get")
def test_abs_series_active_cleanup(mock_get):
    """Verify series resolution marks previous book finished when progress >= 0.95."""
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token123", timeout=3.0)

    # Mock series response (2 books)
    series_resp = MagicMock()
    series_resp.status_code = 200
    series_resp.json.return_value = {
        "id": "ser_xyz",
        "name": "Test Series",
        "books": [
            {"id": "book_1", "sequence": "1", "title": "Episode 1"},
            {"id": "book_2", "sequence": "2", "title": "Episode 2"}
        ]
    }

    # Mock user progress (Book 1 has progress 0.96 but isFinished=False)
    progress_resp = MagicMock()
    progress_resp.status_code = 200
    progress_resp.json.return_value = {
        "mediaProgress": [
            {
                "libraryItemId": "book_1",
                "isFinished": False,
                "currentTime": 960,
                "duration": 1000,
                "progress": 0.96,
                "lastUpdate": 1700000000
            }
        ]
    }

    def side_effect(url, **kwargs):
        if "/api/series/ser_xyz" in url:
            return series_resp
        elif "/api/me/progress" in url:
            return progress_resp
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    with patch.object(client, "mark_as_finished", return_value=True) as mock_mark:
        resolved = client.resolve_next_book_in_series("ser_xyz", user_token="user_tok")

        # Book 1 had progress 0.96 with isFinished=False -> mark_as_finished must be called
        mock_mark.assert_called_once_with("book_1", user_token="user_tok")
        # And next book (Episode 2) should be selected
        assert resolved is not None
        assert resolved["book_id"] == "book_2"
        assert resolved["title"] == "Episode 2"


# -----------------------------------------------------------------------------
# 2: Lazy Evaluation & Debounce for Series Resolution
# -----------------------------------------------------------------------------

def test_mqtt_removed_lazy_evaluation():
    """Verify removed event executes zero series calculations."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)
        upsert_reader(db_path, {
            "reader_id": "reader_kizi",
            "target_player": "media_player.kinderzimmer"
        })

        config = AppConfig(database_path=db_path)
        config.mqtt.topic_action = "rfid/action"

        abs_mock = MagicMock(spec=AudiobookshelfClient)
        service = MQTTService(config=config, abs_client=abs_mock)
        service.publish = MagicMock(return_value=True)

        # Trigger removed event
        service.process_rfid_event({
            "status": "removed",
            "reader_id": "reader_kizi",
            "tag_id": "04-BC-D9-68-B8-2A-81",
        })

        # Verify reader was recorded in _last_removed_events
        assert "reader_kizi" in service._last_removed_events
        assert "media_player.kinderzimmer" in service._last_removed_events
        # Ensure ABS client was never queried during removed
        abs_mock.resolve_next_book_in_series.assert_not_called()
        abs_mock.get_user_progress.assert_not_called()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_mqtt_scanned_debounce_timing():
    """Verify rapid re-scan (< 3s after removed) triggers sleep before querying ABS."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)
        upsert_reader(db_path, {
            "reader_id": "reader_kizi",
            "target_player": "media_player.kinderzimmer",
            "abs_user_token": "token_kizi"
        })
        upsert_tag(db_path, {
            "tag_id": "04bcd968b82a81",
            "alias": "Series Tag",
            "action_type": "abs_serie",
            "target_id": "ser_123"
        })

        config = AppConfig(database_path=db_path)
        config.mqtt.topic_action = "rfid/action"

        abs_mock = MagicMock(spec=AudiobookshelfClient)
        abs_mock.resolve_next_book_in_series.return_value = {
            "book_id": "book_1",
            "title": "B1",
            "sequence": 1
        }

        service = MQTTService(config=config, abs_client=abs_mock)
        service.publish = MagicMock(return_value=True)

        # 1. Simulate removed event at t=100.0
        service._last_removed_events["reader_kizi"] = 100.0
        service._last_removed_events["media_player.kinderzimmer"] = 100.0

        # 2. Simulate scanned event at t=101.5 (diff = 1.5s < 3.0s)
        with patch("time.time", return_value=101.5), \
             patch.object(service, "_force_async_sleep") as mock_sleep:

            service.process_rfid_event({
                "status": "scanned",
                "reader_id": "reader_kizi",
                "tag_id": "04-BC-D9-68-B8-2A-81",
            })

            # Debounce sleep should be triggered with remainder 3.0 - 1.5 = 1.5
            mock_sleep.assert_called_once()
            args, _ = mock_sleep.call_args
            assert pytest.approx(args[0], 0.05) == 1.5
            abs_mock.resolve_next_book_in_series.assert_called_once()

        # 3. Simulate scanned event when diff >= 3.0s
        service._last_removed_events["reader_kizi"] = 100.0
        with patch("time.time", return_value=105.0), \
             patch.object(service, "_force_async_sleep") as mock_sleep_no_op:

            abs_mock.reset_mock()
            service.process_rfid_event({
                "status": "scanned",
                "reader_id": "reader_kizi",
                "tag_id": "04-BC-D9-68-B8-2A-81",
            })

            # Sleep should NOT be triggered
            mock_sleep_no_op.assert_not_called()
            abs_mock.resolve_next_book_in_series.assert_called_once()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# -----------------------------------------------------------------------------
# 4: Tag ID Normalization & DB Migration
# -----------------------------------------------------------------------------

def test_sanitize_tag_id():
    """Verify sanitize_tag_id strips hyphens, colons, spaces, and lowercases."""
    assert sanitize_tag_id("04-BC-D9-68-B8-2A-81") == "04bcd968b82a81"
    assert sanitize_tag_id("04:BC:D9:68:B8:2A:81") == "04bcd968b82a81"
    assert sanitize_tag_id(" 04-bc-d9 ") == "04bcd9"
    assert sanitize_tag_id("TAG-123-XYZ") == "tag123xyz"
    assert sanitize_tag_id("") == ""
    assert sanitize_tag_id(None) == ""


def test_database_startup_migration():
    """Verify init_db migrates legacy hyphenated tags and scan history cleanly."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Create legacy schema manually
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE tags (
                tag_id TEXT PRIMARY KEY,
                alias TEXT,
                action_type TEXT,
                library_id TEXT,
                target_id TEXT,
                volume INTEGER,
                random BOOLEAN DEFAULT 0,
                start_from_beginning BOOLEAN DEFAULT 0,
                extra_params TEXT,
                last_scanned DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_id TEXT,
                reader_id TEXT,
                status TEXT,
                action_executed TEXT,
                payload TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert legacy hyphenated records including a collision case
        cur.execute("INSERT INTO tags (tag_id, alias, action_type, target_id) VALUES ('04-BC-D9-01', 'Tag 1', 'abs_item', 'item_1')")
        cur.execute("INSERT INTO tags (tag_id, alias, action_type, target_id) VALUES ('04-BC-D9-02', 'Tag 2', 'none', '')")
        # Collision: insert both '04-BC-D9-03' and '04bcd903'
        cur.execute("INSERT INTO tags (tag_id, alias, action_type, target_id) VALUES ('04-BC-D9-03', 'Legacy Tag 3', 'abs_series', 'series_old')")
        cur.execute("INSERT INTO tags (tag_id, alias, action_type, target_id) VALUES ('04bcd903', 'Modern Tag 3', 'abs_series', 'series_new')")

        # Insert legacy scan history
        cur.execute("INSERT INTO scan_history (reader_id, tag_id, status) VALUES ('r1', '04-BC-D9-01', 'scanned')")
        conn.commit()
        conn.close()

        # Run init_db which should execute the migration
        init_db(db_path)

        all_tags = get_all_tags(db_path)
        tag_ids = [t["tag_id"] for t in all_tags]

        # All tag IDs must be lowercase and hyphen-free
        for tid in tag_ids:
            assert "-" not in tid
            assert tid == tid.lower()

        assert "04bcd901" in tag_ids
        assert "04bcd902" in tag_ids
        assert "04bcd903" in tag_ids

        # Scan history must also be normalized
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT tag_id FROM scan_history")
        hist_tags = [row[0] for row in cur.fetchall()]
        conn.close()
        assert hist_tags == ["04bcd901"]
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# -----------------------------------------------------------------------------
# 5: Bulk Delete for Unconfigured Tags
# -----------------------------------------------------------------------------

def test_delete_unconfigured_tags_db():
    """Verify delete_unconfigured_tags removes tags without valid actions/targets."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)

        # 1. Configured tag
        upsert_tag(db_path, {
            "tag_id": "tag_conf_1",
            "action_type": "ha_script",
            "target_id": "script.bedtime"
        })
        # 2. Unconfigured (action_type is empty)
        upsert_tag(db_path, {
            "tag_id": "tag_unconf_1",
            "action_type": "",
            "target_id": ""
        })
        # 3. Unconfigured (action_type is 'none')
        upsert_tag(db_path, {
            "tag_id": "tag_unconf_2",
            "action_type": "none",
            "target_id": "something"
        })
        # 4. Unconfigured (action_type set but target_id empty)
        upsert_tag(db_path, {
            "tag_id": "tag_unconf_3",
            "action_type": "abs_item",
            "target_id": ""
        })

        assert len(get_all_tags(db_path)) == 4

        deleted_count = delete_unconfigured_tags(db_path)
        assert deleted_count == 3

        remaining = get_all_tags(db_path)
        assert len(remaining) == 1
        assert remaining[0]["tag_id"] == "tag_conf_1"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_api_delete_unconfigured_tags():
    """Verify DELETE /api/tags/unconfigured endpoint."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)
        upsert_tag(db_path, {
            "tag_id": "tag_active",
            "action_type": "abs_item",
            "target_id": "item_99"
        })
        upsert_tag(db_path, {
            "tag_id": "tag_idle",
            "action_type": "none",
            "target_id": ""
        })

        client = TestClient(app)
        with patch.object(app.state.config, "database_path", db_path):
            resp = client.delete("/api/tags/unconfigured")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert data["deleted_count"] == 1

            # Check that only tag_active remains
            resp_list = client.get("/api/tags")
            assert resp_list.status_code == 200
            tags = resp_list.json()
            assert len(tags) == 1
            assert tags[0]["tag_id"] == "tag_active"
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# -----------------------------------------------------------------------------
# 6: Custom Firmware & Download Bin Endpoint
# -----------------------------------------------------------------------------

def test_firmware_template_and_download_bin():
    """Verify m5atom_lite_rfid_native is listed and binary download works."""
    client = TestClient(app)

    # 1. Check templates list includes m5atom_lite_rfid_native
    resp_templates = client.get("/api/firmware/templates")
    assert resp_templates.status_code == 200
    templates = resp_templates.json()
    hw_ids = [t["id"] for t in templates]
    assert "m5atom_lite_rfid_native" in hw_ids

    # 2. Check binary download for m5atom_lite_rfid_native
    resp_bin = client.get("/api/firmware/download-bin/m5atom_lite_rfid_native")
    assert resp_bin.status_code == 200
    assert "application/octet-stream" in resp_bin.headers.get("content-type", "")
    assert "m5atom_lite_rfid_native" in resp_bin.headers.get("content-disposition", "")
    assert len(resp_bin.content) > 0

    # 3. Check binary download for invalid hardware returns 404
    resp_404 = client.get("/api/firmware/download-bin/non_existent_hw")
    assert resp_404.status_code == 404


def test_podcast_newest_to_older_resolution():
    """Verify podcast episodes resolve newest first, then move to older, with active cleanup."""
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token123")

    mock_podcast = {
        "id": "pod_news",
        "name": "Tech News Daily",
        "media": {
            "metadata": {"title": "Tech News Daily"},
            "episodes": [
                {
                    "id": "ep_jan",
                    "title": "Episode 1 (January)",
                    "pubDate": "Wed, 10 Jan 2024 10:00:00 +0000"
                },
                {
                    "id": "ep_feb",
                    "title": "Episode 2 (February)",
                    "pubDate": "Sat, 10 Feb 2024 10:00:00 +0000"
                },
                {
                    "id": "ep_mar",
                    "title": "Episode 3 (March - Newest)",
                    "pubDate": "Sun, 10 Mar 2024 10:00:00 +0000"
                }
            ]
        }
    }

    # 1. No progress -> selects Episode 3 (newest, March)
    with patch.object(client, "get_podcast_details", return_value=mock_podcast), \
         patch.object(client, "get_user_progress", return_value={}):
        res = client.resolve_latest_podcast_episode("pod_news")
        assert res is not None
        assert res["episode_id"] == "ep_mar"

    # 2. Episode 3 is finished at 96% -> active cleanup triggers mark_as_finished and advances to Episode 2 (older, February)
    mock_progress_ep3 = {
        "ep_mar": {
            "episodeId": "ep_mar",
            "isFinished": False,
            "progress": 0.96,
            "currentTime": 960,
            "duration": 1000,
            "lastUpdate": 1700000000
        }
    }
    with patch.object(client, "get_podcast_details", return_value=mock_podcast), \
         patch.object(client, "get_user_progress", return_value=mock_progress_ep3), \
         patch.object(client, "mark_as_finished", return_value=True) as mock_mark:
        res = client.resolve_latest_podcast_episode("pod_news", user_token="tok")
        mock_mark.assert_called_once_with("ep_mar", user_token="tok")
        assert res is not None
        assert res["episode_id"] == "ep_feb"

    # 3. Episode 3 and Episode 2 are finished -> advances to Episode 1 (oldest, January)
    mock_progress_both = {
        "ep_mar": {"isFinished": True, "progress": 1.0},
        "ep_feb": {"isFinished": True, "progress": 1.0}
    }
    with patch.object(client, "get_podcast_details", return_value=mock_podcast), \
         patch.object(client, "get_user_progress", return_value=mock_progress_both):
        res = client.resolve_latest_podcast_episode("pod_news")
        assert res is not None
        assert res["episode_id"] == "ep_jan"

