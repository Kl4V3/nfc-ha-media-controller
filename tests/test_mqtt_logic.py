import os
import tempfile
from unittest.mock import MagicMock
import pytest

from app.config import AppConfig
from app.database import init_db, upsert_reader, upsert_tag
from app.audiobookshelf import AudiobookshelfClient
from app.mqtt_client import MQTTService


@pytest.fixture
def temp_env():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)

    config = AppConfig(database_path=db_path)
    config.mqtt.topic_action = "rfid/action"
    config.media.warning_sound_uri = "http://ha.local/warning.mp3"
    config.media.default_volume = 25

    # Reader einrichten
    upsert_reader(db_path, {
        "reader_id": "reader_kizi",
        "target_player": "media_player.kinderzimmer",
        "abs_user_token": "token_kizi"
    })

    abs_client = MagicMock(spec=AudiobookshelfClient)

    mqtt_service = MQTTService(config=config, abs_client=abs_client)
    mqtt_service.publish = MagicMock(return_value=True)

    yield {
        "db_path": db_path,
        "config": config,
        "abs_client": abs_client,
        "mqtt_service": mqtt_service
    }

    if os.path.exists(db_path):
        os.remove(db_path)


def test_tag_removed_event(temp_env):
    mqtt_service = temp_env["mqtt_service"]

    event_data = {
        "tag_id": "TAG_123",
        "reader_id": "reader_kizi",
        "status": "removed"
    }

    result = mqtt_service.process_rfid_event(event_data)

    assert result["status"] == "removed"
    assert result["action_type"] == "stop"
    assert result["target_player"] == "media_player.kinderzimmer"
    mqtt_service.publish.assert_called_once_with(
        "rfid/action",
        {
            "status": "removed",
            "action_type": "stop",
            "reader_id": "reader_kizi",
            "target_player": "media_player.kinderzimmer",
            "target_id": "",
            "volume": 0,
            "random": False,
            "extra_params": {},
            "metadata": {
                "tag_id": "TAG_123"
            }
        }
    )


def test_unconfigured_tag_warning(temp_env):
    mqtt_service = temp_env["mqtt_service"]

    event_data = {
        "tag_id": "NEW_UNCONFIGURED_TAG",
        "reader_id": "reader_kizi",
        "status": "scanned"
    }

    result = mqtt_service.process_rfid_event(event_data)

    assert result["status"] == "warning"
    assert result["action_type"] == "warning"
    assert result["target_player"] == "media_player.kinderzimmer"
    assert result["target_id"] == "http://ha.local/warning.mp3"
    assert result["volume"] == 25
    assert result["extra_params"] == {"enqueue": "replace"}
    mqtt_service.publish.assert_called_once()


def test_configured_abs_series_tag(temp_env):
    mqtt_service = temp_env["mqtt_service"]
    abs_client = temp_env["abs_client"]
    db_path = temp_env["db_path"]

    # Tag konfigurieren
    upsert_tag(db_path, {
        "tag_id": "SERIES_TAG",
        "alias": "Bibi Blocksberg Serie",
        "action_type": "Serie",
        "library_id": "lib_bibi",
        "target_id": "ser_bibi",
        "volume": 30,
        "random": False
    })

    # ABS Mock Auflösung
    abs_client.resolve_next_book_in_series.return_value = {
        "series_id": "ser_bibi",
        "series_name": "Bibi Blocksberg",
        "book_id": "book_folge_42",
        "title": "Folge 42: Das Schulfest",
        "sequence": "42"
    }

    event_data = {
        "tag_id": "SERIES_TAG",
        "reader_id": "reader_kizi",
        "status": "scanned"
    }

    result = mqtt_service.process_rfid_event(event_data)

    assert result["status"] == "scanned"
    assert result["action_type"] == "media"
    assert result["media_type"] == "audiobook"
    assert result["target_player"] == "media_player.kinderzimmer"
    assert result["target_id"] == "audiobookshelf://audiobook/book_folge_42"
    assert result["volume"] == 30
    abs_client.resolve_next_book_in_series.assert_called_once_with("ser_bibi", library_id="lib_bibi", user_token="token_kizi")
    mqtt_service.publish.assert_called_once()


def test_configured_album_tag(temp_env):
    mqtt_service = temp_env["mqtt_service"]
    db_path = temp_env["db_path"]

    upsert_tag(db_path, {
        "tag_id": "ALBUM_TAG",
        "alias": "Rock Anthems Album",
        "action_type": "Album",
        "target_id": "mass://album/rock_classics",
        "volume": 40,
        "random": False
    })

    event_data = {
        "tag_id": "ALBUM_TAG",
        "reader_id": "reader_kizi",
        "status": "scanned"
    }

    result = mqtt_service.process_rfid_event(event_data)

    assert result["status"] == "scanned"
    assert result["action_type"] == "media"
    assert result["media_type"] == "album"
    assert result["target_player"] == "media_player.kinderzimmer"
    assert result["target_id"] == "library://album/rock_classics"
    assert result["volume"] == 40


def test_configured_playlist_tag(temp_env):
    mqtt_service = temp_env["mqtt_service"]
    db_path = temp_env["db_path"]

    upsert_tag(db_path, {
        "tag_id": "PLAYLIST_TAG",
        "alias": "Favorite Songs",
        "action_type": "Playlist",
        "target_id": "30",
        "volume": 35,
        "random": True
    })

    event_data = {
        "tag_id": "PLAYLIST_TAG",
        "reader_id": "reader_kizi",
        "status": "scanned"
    }

    result = mqtt_service.process_rfid_event(event_data)

    assert result["status"] == "scanned"
    assert result["action_type"] == "media"
    assert result["media_type"] == "playlist"
    assert result["target_player"] == "media_player.kinderzimmer"
    assert result["target_id"] == "library://playlist/30"
    assert result["volume"] == 35


def test_abs_custom_provider_prefix(temp_env):
    mqtt_service = temp_env["mqtt_service"]
    abs_client = temp_env["abs_client"]
    db_path = temp_env["db_path"]

    # Reader mit spezifischem ABS Provider Prefix
    upsert_reader(db_path, {
        "reader_id": "reader_custom_abs",
        "target_player": "media_player.wz",
        "abs_user_token": "tok_wz",
        "abs_provider_prefix": "audiobookshelf--xPQT49LN"
    })

    upsert_tag(db_path, {
        "tag_id": "ABS_TAG",
        "alias": "Single Audiobook",
        "action_type": "Hoerbuch",
        "target_id": "abe67622-a0af-42f7-9d53-35e0ea59dd23",
        "volume": 20
    })

    event_data = {
        "tag_id": "ABS_TAG",
        "reader_id": "reader_custom_abs",
        "status": "scanned"
    }

    result = mqtt_service.process_rfid_event(event_data)

    assert result["status"] == "scanned"
    assert result["action_type"] == "media"
    assert result["media_type"] == "audiobook"
    assert result["target_id"] == "audiobookshelf--xPQT49LN://audiobook/abe67622-a0af-42f7-9d53-35e0ea59dd23"


