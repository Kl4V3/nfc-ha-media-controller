import os
import tempfile
import pytest

from app.database import (
    init_db,
    get_all_tags,
    get_tag_by_id,
    auto_discover_or_update_tag,
    upsert_tag,
    delete_tag,
    get_all_readers,
    get_reader_by_id,
    upsert_reader,
    delete_reader,
    add_scan_history,
    get_scan_history
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_init_db(temp_db):
    assert os.path.exists(temp_db)
    tags = get_all_tags(temp_db)
    assert len(tags) == 0
    readers = get_all_readers(temp_db)
    assert len(readers) == 0


def test_auto_discovery_tag(temp_db):
    # 1. Neuer Tag gescannt
    res = auto_discover_or_update_tag(temp_db, "04AABBCCDD")
    assert res["is_new"] is True
    assert res["tag_id"] == "04AABBCCDD"
    assert res["action_type"] == ""
    assert "Unbekannter Tag" in res["alias"]

    # In DB prüfen
    tag = get_tag_by_id(temp_db, "04AABBCCDD")
    assert tag is not None
    assert tag["tag_id"] == "04AABBCCDD"
    assert tag["last_scanned"] is not None

    # 2. Zweiter Scan des gleichen Tags (sollte is_new = False sein)
    res2 = auto_discover_or_update_tag(temp_db, "04AABBCCDD")
    assert res2["is_new"] is False


def test_upsert_and_delete_tag(temp_db):
    tag_data = {
        "tag_id": "TAG123",
        "alias": "Die drei ??? Kids",
        "action_type": "Serie",
        "target_id": "ser_abc456",
        "volume": 25,
        "random": True,
        "extra_params": '{"test": 123}'
    }
    saved = upsert_tag(temp_db, tag_data)
    assert saved["tag_id"] == "TAG123"
    assert saved["alias"] == "Die drei ??? Kids"
    assert saved["action_type"] == "Serie"
    assert saved["volume"] == 25
    assert saved["random"] is True
    assert saved["extra_params_parsed"] == {"test": 123}

    # Löschen
    deleted = delete_tag(temp_db, "TAG123")
    assert deleted is True
    assert get_tag_by_id(temp_db, "TAG123") is None


def test_readers_crud(temp_db):
    reader_data = {
        "reader_id": "reader_kizi",
        "target_player": "media_player.kinderzimmer",
        "abs_user_token": "token_jonas",
        "notes": "Kinderzimmer Jonas"
    }
    saved = upsert_reader(temp_db, reader_data)
    assert saved["reader_id"] == "reader_kizi"
    assert saved["target_player"] == "media_player.kinderzimmer"
    assert saved["abs_user_token"] == "token_jonas"

    readers = get_all_readers(temp_db)
    assert len(readers) == 1
    assert readers[0]["reader_id"] == "reader_kizi"

    # Löschen
    deleted = delete_reader(temp_db, "reader_kizi")
    assert deleted is True
    assert get_reader_by_id(temp_db, "reader_kizi") is None


def test_scan_history(temp_db):
    add_scan_history(temp_db, "TAG99", "reader_kizi", "scanned", "media", '{"test": 1}')
    history = get_scan_history(temp_db, limit=10)
    assert len(history) == 1
    assert history[0]["tag_id"] == "TAG99"
    assert history[0]["action_executed"] == "media"
