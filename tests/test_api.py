import os
import tempfile
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import AppConfig
from app.database import init_db
from app.audiobookshelf import AudiobookshelfClient
from app.mqtt_client import MQTTService


@pytest.fixture
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(db_path)

    config = AppConfig(database_path=db_path)
    abs_client = MagicMock(spec=AudiobookshelfClient)
    abs_client.test_connection.return_value = {"success": True, "username": "admin"}
    abs_client.get_libraries.return_value = [{"id": "lib1", "name": "Hörbücher"}]
    abs_client.get_series_list.return_value = [{"id": "ser1", "name": "Bibi", "num_books": 5}]

    mqtt_service = MagicMock(spec=MQTTService)
    mqtt_service.is_connected = True
    mqtt_service.publish.return_value = True

    # Real process_rfid_event logic for simulator
    real_mqtt = MQTTService(config=config, abs_client=abs_client)
    real_mqtt.publish = MagicMock(return_value=True)
    mqtt_service.process_rfid_event.side_effect = real_mqtt.process_rfid_event

    app.state.config = config
    app.state.abs_client = abs_client
    app.state.mqtt_service = mqtt_service

    with TestClient(app) as test_client:
        yield test_client

    if os.path.exists(db_path):
        os.remove(db_path)


def test_index_route(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "NFC Media Controller" in res.text


def test_tags_api_crud(client):
    # 1. Tags abrufen (leer)
    res = client.get("/api/tags")
    assert res.status_code == 200
    assert res.json() == []

    # 2. Tag anlegen
    payload = {
        "tag_id": "TAG_A1",
        "alias": "Lieblingslied",
        "action_type": "Hoerbuch",
        "target_id": "mass://track/123",
        "volume": 35,
        "random": False,
        "extra_params": "{}"
    }
    res_post = client.post("/api/tags", json=payload)
    assert res_post.status_code == 200
    created = res_post.json()
    assert created["tag_id"] == "TAG_A1"
    assert created["alias"] == "Lieblingslied"

    # 3. Tag abrufen
    res_get = client.get("/api/tags/TAG_A1")
    assert res_get.status_code == 200
    assert res_get.json()["volume"] == 35

    # 4. Tag löschen
    res_del = client.delete("/api/tags/TAG_A1")
    assert res_del.status_code == 200
    assert client.get("/api/tags/TAG_A1").status_code == 404


def test_readers_api_crud(client):
    payload = {
        "reader_id": "reader_wohnzimmer",
        "target_player": "media_player.soundbar",
        "abs_user_token": "",
        "notes": "Soundbar im Wohnzimmer"
    }
    res_post = client.post("/api/readers", json=payload)
    assert res_post.status_code == 200
    assert res_post.json()["reader_id"] == "reader_wohnzimmer"

    res_list = client.get("/api/readers")
    assert len(res_list.json()) == 1


def test_scan_simulator_api(client):
    payload = {
        "tag_id": "SIM_TAG_99",
        "reader_id": "reader_kizi",
        "status": "scanned"
    }
    res = client.post("/api/test/scan", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["action_result"]["status"] == "warning"  # Da unkonfiguriert


def test_system_status_api(client):
    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert "mqtt" in data
    assert "audiobookshelf" in data
    assert "media" in data


def test_system_logs_api(client):
    res = client.get("/api/system/logs")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)

