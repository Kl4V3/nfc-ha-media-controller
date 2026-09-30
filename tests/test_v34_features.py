import os
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app import __version__
from app.i18n import get_translations
from app.config import load_config, AppConfig
from app.database import init_db, get_all_tags, get_tag_by_id, upsert_tag, auto_discover_or_update_tag
from app.audiobookshelf import AudiobookshelfClient
from app.mqtt_client import MQTTService
from app.main import app


def test_version():
    assert __version__ == "0.4.0"


def test_i18n_translations():
    en = get_translations("en")
    de = get_translations("de")

    assert en["tab_tags"] == "NFC Tags"
    assert de["tab_tags"] == "NFC-Tags"
    assert en["modal_start_from_beginning"] == "Always start from beginning (resets progress to 0:00)"
    assert de["modal_start_from_beginning"] == "Immer von vorne starten (setzt Fortschritt auf 0:00 zurück)"

    # Default is English
    default_t = get_translations("")
    assert default_t["tab_tags"] == "NFC Tags"


def test_config_language(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write("server:\n  port: 5000\n")
        tmp_cfg = f.name

    try:
        monkeypatch.delenv("UI_LANGUAGE", raising=False)
        monkeypatch.delenv("LANGUAGE", raising=False)
        cfg = load_config(tmp_cfg)
        assert cfg.server.language == "en"

        monkeypatch.setenv("UI_LANGUAGE", "de")
        cfg_de = load_config(tmp_cfg)
        assert cfg_de.server.language == "de"
    finally:
        os.unlink(tmp_cfg)


def test_database_start_from_beginning():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)

        # 1. Auto-discover
        tag = auto_discover_or_update_tag(db_path, "TEST_TAG_1")
        assert tag["start_from_beginning"] is False

        # 2. Upsert with start_from_beginning = True
        saved = upsert_tag(db_path, {
            "tag_id": "TEST_TAG_1",
            "alias": "Test Hörbuch",
            "action_type": "Hoerbuch",
            "library_id": "lib-1",
            "target_id": "item-123",
            "volume": 25,
            "random": False,
            "start_from_beginning": True
        })
        assert saved["start_from_beginning"] is True

        fetched = get_tag_by_id(db_path, "TEST_TAG_1")
        assert fetched["start_from_beginning"] is True

        all_tags = get_all_tags(db_path)
        assert len(all_tags) == 1
        assert all_tags[0]["start_from_beginning"] is True
    finally:
        os.unlink(db_path)


def test_podcast_resolution_in_abs():
    client = AudiobookshelfClient(base_url="http://abs.local:13378", default_token="test-token")

    mock_podcast = {
        "id": "podcast-xyz",
        "name": "Wissen macht Ah!",
        "media": {
            "metadata": {"title": "Wissen macht Ah!"},
            "episodes": [
                {
                    "id": "ep-1",
                    "title": "Folge 1 - Älteste Folge",
                    "publishedAt": 1609459200000
                },
                {
                    "id": "ep-2",
                    "title": "Folge 2 - Mittlere Folge",
                    "publishedAt": 1640995200000
                },
                {
                    "id": "ep-3",
                    "title": "Folge 3 - Neueste Folge",
                    "publishedAt": 1672531100000
                }
            ]
        }
    }

    # Fall 1: Keine Folge bisher gehört -> wählt Folge 3 (neueste)
    with patch.object(client, "get_podcast_details", return_value=mock_podcast), \
         patch.object(client, "get_user_progress", return_value={}):
        res = client.resolve_latest_podcast_episode("podcast-xyz")
        assert res is not None
        assert res["episode_id"] == "ep-3"
        assert res["episode_title"] == "Folge 3 - Neueste Folge"

    # Fall 2: Folge 3 ist fertig gehört -> wählt Folge 2
    mock_progress = {
        "ep-3": {"isFinished": True, "progress": 1.0}
    }
    with patch.object(client, "get_podcast_details", return_value=mock_podcast), \
         patch.object(client, "get_user_progress", return_value=mock_progress):
        res = client.resolve_latest_podcast_episode("podcast-xyz")
        assert res is not None
        assert res["episode_id"] == "ep-2"

    # Fall 3: Alle Folgen fertig gehört -> Fallback auf neueste Folge (Folge 3)
    mock_all_finished = {
        "ep-1": {"isFinished": True},
        "ep-2": {"isFinished": True},
        "ep-3": {"isFinished": True}
    }
    with patch.object(client, "get_podcast_details", return_value=mock_podcast), \
         patch.object(client, "get_user_progress", return_value=mock_all_finished):
        res = client.resolve_latest_podcast_episode("podcast-xyz")
        assert res is not None
        assert res["episode_id"] == "ep-3"


def test_mqtt_service_start_from_beginning_and_random_restrictions():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        init_db(db_path)
        config = AppConfig()
        config.database_path = db_path
        config.audiobookshelf.mass_instance_id = "xPQT49LN"
        mock_abs = MagicMock()
        mock_abs.reset_item_progress.return_value = True
        mock_abs.resolve_next_book_in_series.return_value = {
            "book_id": "book-abc",
            "title": "Buch 2",
            "series_name": "Die drei ???",
            "sequence": 2,
            "total_books": 10
        }

        service = MQTTService(config=config, abs_client=mock_abs)
        service.publish = MagicMock()

        # 1. Serie mit start_from_beginning=True und random=True
        upsert_tag(db_path, {
            "tag_id": "TAG_SERIE",
            "alias": "Die drei ??? Serie",
            "action_type": "Serie",
            "library_id": "lib-1",
            "target_id": "series-123",
            "volume": 20,
            "random": True,
            "start_from_beginning": True
        })

        payload = service.process_rfid_event({
            "reader_id": "reader_kizi",
            "tag_id": "TAG_SERIE",
            "status": "scanned"
        })

        # random muss False sein für Serie!
        assert payload["random"] is False
        assert payload["start_from_beginning"] is True
        mock_abs.reset_item_progress.assert_called_with("book-abc", user_token="")

        # 2. Album mit random=True
        upsert_tag(db_path, {
            "tag_id": "TAG_ALBUM",
            "alias": "Cooles Album",
            "action_type": "Album",
            "target_id": "mass://album/42",
            "volume": 20,
            "random": True,
            "start_from_beginning": False
        })

        payload_album = service.process_rfid_event({
            "reader_id": "reader_kizi",
            "tag_id": "TAG_ALBUM",
            "status": "scanned"
        })

        # random bleibt True für Album!
        assert payload_album["random"] is True

        # 3. Podcast (Music Assistant Bibliothek)
        upsert_tag(db_path, {
            "tag_id": "TAG_PODCAST_MASS",
            "alias": "Mein Podcast",
            "action_type": "Podcast",
            "target_id": "library://podcast/10",
            "volume": 20,
            "random": True,
            "start_from_beginning": False
        })

        payload_pod = service.process_rfid_event({
            "reader_id": "reader_kizi",
            "tag_id": "TAG_PODCAST_MASS",
            "status": "scanned"
        })

        assert payload_pod["random"] is False
        assert payload_pod["target_id"] == "library://podcast/10"
        assert payload_pod["extra_params"]["start_item"] == "latest"

        # 4. Podcast (Audiobookshelf mit Instanz)
        mock_abs.resolve_latest_podcast_episode.return_value = {
            "podcast_id": "pod-abs-1",
            "podcast_title": "Daily News",
            "episode_id": "ep-99",
            "episode_title": "News Heute",
            "pub_date": "2026-09-03",
            "total_episodes": 100
        }

        upsert_tag(db_path, {
            "tag_id": "TAG_PODCAST_ABS",
            "alias": "Daily News",
            "action_type": "Podcast",
            "target_id": "pod-abs-1",
            "volume": 20,
            "random": False,
            "start_from_beginning": False
        })

        payload_abs_pod = service.process_rfid_event({
            "reader_id": "reader_kizi",
            "tag_id": "TAG_PODCAST_ABS",
            "status": "scanned"
        })

        assert payload_abs_pod["media_type"] == "podcast"
        assert payload_abs_pod["target_id"] == "audiobookshelf--xPQT49LN://podcast_episode/pod-abs-1 ep-99"
        assert payload_abs_pod["metadata"]["title"] == "News Heute"
        assert payload_abs_pod["metadata"]["episode_id"] == "ep-99"

    finally:
        os.unlink(db_path)


def test_api_podcasts_and_manifest():
    client = TestClient(app)

    # Firmware Manifest Version
    resp = client.get("/api/firmware/manifest/m5atom_lite_rfid")
    assert resp.status_code == 200
    manifest = resp.json()
    assert manifest["version"] == "0.4.0"

    # ABS Podcasts endpoint
    with patch.object(app.state.abs_client, "get_podcast_list", return_value=[{"id": "p1", "title": "Podcast 1"}]):
        resp = client.get("/api/abs/podcasts")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["id"] == "p1"