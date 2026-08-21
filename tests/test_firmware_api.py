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
    config.mqtt.broker = "192.168.1.88"
    config.mqtt.port = 1883
    config.mqtt.username = "custom_nfc_user"
    config.mqtt.password = "custom_secret"

    abs_client = MagicMock(spec=AudiobookshelfClient)
    abs_client.test_connection.return_value = {"success": True, "username": "admin"}

    mqtt_service = MagicMock(spec=MQTTService)
    mqtt_service.is_connected = True

    app.state.config = config
    app.state.abs_client = abs_client
    app.state.mqtt_service = mqtt_service

    with TestClient(app) as test_client:
        yield test_client

    if os.path.exists(db_path):
        os.remove(db_path)


def test_list_firmware_templates(client):
    res = client.get("/api/firmware/templates")
    assert res.status_code == 200
    templates = res.json()
    assert len(templates) >= 3
    ids = [t["id"] for t in templates]
    assert "m5atom_lite_rfid" in ids
    assert "esp32_pn532_i2c" in ids
    assert "esp32_rc522_spi" in ids

    # Check M5Atom details
    m5atom = next(t for t in templates if t["id"] == "m5atom_lite_rfid")
    assert m5atom["recommended"] is True
    assert len(m5atom["pinout"]) > 0
    assert len(m5atom["led_states"]) > 0


def test_generate_firmware_yaml_json(client):
    res = client.get("/api/firmware/generate-yaml?hardware_type=m5atom_lite_rfid&reader_id=reader_kizi")
    assert res.status_code == 200
    data = res.json()
    assert data["hardware_type"] == "m5atom_lite_rfid"
    assert data["reader_id"] == "reader_kizi"
    assert data["filename"] == "esphome_reader_kizi.yaml"
    yaml_text = data["yaml"]
    
    # Assert substitutions took effect
    assert 'reader_id: "reader_kizi"' in yaml_text
    assert 'mqtt_broker: "192.168.1.88"' in yaml_text
    assert 'mqtt_port: "1883"' in yaml_text
    assert 'mqtt_user: "custom_nfc_user"' in yaml_text
    assert 'mqtt_password: "custom_secret"' in yaml_text


def test_generate_firmware_yaml_custom_override(client):
    res = client.get(
        "/api/firmware/generate-yaml"
        "?hardware_type=esp32_pn532_i2c"
        "&reader_id=reader_flur"
        "&wifi_ssid=MyHomeWLAN"
        "&wifi_password=SecretPass123"
        "&mqtt_broker=10.0.0.5"
        "&mqtt_port=8883"
    )
    assert res.status_code == 200
    yaml_text = res.json()["yaml"]
    assert 'reader_id: "reader_flur"' in yaml_text
    assert 'mqtt_broker: "10.0.0.5"' in yaml_text
    assert 'mqtt_port: "8883"' in yaml_text
    assert 'wifi_ssid: "MyHomeWLAN"' in yaml_text
    assert 'wifi_password: "SecretPass123"' in yaml_text


def test_generate_firmware_yaml_download(client):
    res = client.get("/api/firmware/generate-yaml?hardware_type=m5atom_lite_rfid&reader_id=reader_kueche&download=true")
    assert res.status_code == 200
    assert "attachment; filename=\"esphome_reader_kueche.yaml\"" in res.headers.get("content-disposition", "")
    assert 'reader_id: "reader_kueche"' in res.text


def test_generate_firmware_yaml_invalid_type(client):
    res = client.get("/api/firmware/generate-yaml?hardware_type=non_existent_hardware")
    assert res.status_code == 400


def test_get_firmware_manifest(client):
    res = client.get("/api/firmware/manifest/m5atom_lite_rfid")
    assert res.status_code == 200
    manifest = res.json()
    assert "name" in manifest
    assert "builds" in manifest
    assert manifest["home_assistant_domain"] == "esphome"
