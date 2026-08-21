import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.config import AppConfig
from app.database import (
    get_all_tags,
    get_tag_by_id,
    upsert_tag,
    delete_tag,
    get_all_readers,
    get_reader_by_id,
    upsert_reader,
    delete_reader,
    get_scan_history
)

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")


# ==============================================================================
# Pydantic Models
# ==============================================================================

class TagModel(BaseModel):
    tag_id: str = Field(..., min_length=1)
    alias: Optional[str] = Field(default="")
    action_type: Optional[str] = Field(default="")
    library_id: Optional[str] = Field(default="")
    target_id: Optional[str] = Field(default="")
    volume: Optional[int] = Field(default=None, ge=0, le=100)
    random: Optional[bool] = Field(default=False)
    extra_params: Optional[Any] = Field(default="{}")


class ReaderModel(BaseModel):
    reader_id: str = Field(..., min_length=1)
    target_player: str = Field(..., min_length=1)
    abs_user_token: Optional[str] = Field(default="")
    abs_provider_prefix: Optional[str] = Field(default="")
    notes: Optional[str] = Field(default="")


class ScanSimulationModel(BaseModel):
    tag_id: str = Field(..., min_length=1)
    reader_id: str = Field(..., min_length=1)
    status: str = Field(default="scanned")  # "scanned" oder "removed"


# ==============================================================================
# TAGS ENDPOINTS
# ==============================================================================

@api_router.get("/tags", response_model=List[Dict[str, Any]])
def list_tags(request: Request):
    config: AppConfig = request.app.state.config
    return get_all_tags(config.database_path)


@api_router.get("/tags/{tag_id}", response_model=Dict[str, Any])
def get_tag(tag_id: str, request: Request):
    config: AppConfig = request.app.state.config
    tag = get_tag_by_id(config.database_path, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@api_router.post("/tags", response_model=Dict[str, Any])
@api_router.put("/tags/{tag_id}", response_model=Dict[str, Any])
def save_tag(tag_data: TagModel, request: Request, tag_id: Optional[str] = None):
    config: AppConfig = request.app.state.config
    data = tag_data.model_dump()
    if tag_id:
        data["tag_id"] = tag_id
    saved = upsert_tag(config.database_path, data)
    return saved


@api_router.delete("/tags/{tag_id}")
def remove_tag(tag_id: str, request: Request):
    config: AppConfig = request.app.state.config
    success = delete_tag(config.database_path, tag_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"success": True, "message": f"Tag {tag_id} deleted"}


# ==============================================================================
# READERS ENDPOINTS
# ==============================================================================

@api_router.get("/readers", response_model=List[Dict[str, Any]])
def list_readers(request: Request):
    config: AppConfig = request.app.state.config
    return get_all_readers(config.database_path)


@api_router.get("/readers/{reader_id}", response_model=Dict[str, Any])
def get_reader(reader_id: str, request: Request):
    config: AppConfig = request.app.state.config
    reader = get_reader_by_id(config.database_path, reader_id)
    if not reader:
        raise HTTPException(status_code=404, detail="Reader not found")
    return reader


@api_router.post("/readers", response_model=Dict[str, Any])
@api_router.put("/readers/{reader_id}", response_model=Dict[str, Any])
def save_reader(reader_data: ReaderModel, request: Request, reader_id: Optional[str] = None):
    config: AppConfig = request.app.state.config
    data = reader_data.model_dump()
    if reader_id:
        data["reader_id"] = reader_id
    saved = upsert_reader(config.database_path, data)
    return saved


@api_router.delete("/readers/{reader_id}")
def remove_reader(reader_id: str, request: Request):
    config: AppConfig = request.app.state.config
    success = delete_reader(config.database_path, reader_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reader not found")
    return {"success": True, "message": f"Reader {reader_id} deleted"}


# ==============================================================================
# SCAN HISTORY
# ==============================================================================

@api_router.get("/history", response_model=List[Dict[str, Any]])
def list_history(request: Request, limit: int = 50):
    config: AppConfig = request.app.state.config
    return get_scan_history(config.database_path, limit=limit)


# ==============================================================================
# AUDIOBOOKSHELF HELPERS
# ==============================================================================

@api_router.get("/abs/test")
def test_abs(request: Request, token: Optional[str] = None):
    abs_client = request.app.state.abs_client
    return abs_client.test_connection(user_token=token)


@api_router.get("/abs/libraries")
def get_abs_libraries(request: Request, token: Optional[str] = None):
    abs_client = request.app.state.abs_client
    return abs_client.get_libraries(user_token=token)


@api_router.get("/abs/series")
def get_abs_series(request: Request, q: Optional[str] = None, library_id: Optional[str] = None, token: Optional[str] = None):
    abs_client = request.app.state.abs_client
    if q and q.strip():
        return abs_client.search_series(query=q, library_id=library_id, user_token=token)
    return abs_client.get_series_list(library_id=library_id, user_token=token)


@api_router.get("/abs/items")
def get_abs_items(request: Request, q: Optional[str] = None, library_id: Optional[str] = None, token: Optional[str] = None, limit: int = 100):
    abs_client = request.app.state.abs_client
    if q and q.strip():
        return abs_client.search_items(query=q, library_id=library_id, user_token=token)
    return abs_client.get_items_list(library_id=library_id, user_token=token, limit=limit)


@api_router.get("/abs/series/{series_id}")
def get_abs_series_details(series_id: str, request: Request, token: Optional[str] = None):
    abs_client = request.app.state.abs_client
    details = abs_client.get_series_details(series_id, user_token=token)
    if not details:
        raise HTTPException(status_code=404, detail="Series not found or ABS unreachable")
    return details


@api_router.get("/abs/resolve-series/{series_id}")
def resolve_abs_series(series_id: str, request: Request, token: Optional[str] = None):
    abs_client = request.app.state.abs_client
    res = abs_client.resolve_next_book_in_series(series_id, user_token=token)
    if not res:
        raise HTTPException(status_code=404, detail="Could not resolve book in series")
    return res


# ==============================================================================
# TEST SIMULATOR
# ==============================================================================

@api_router.post("/test/scan")
def simulate_scan(sim_data: ScanSimulationModel, request: Request):
    mqtt_service = request.app.state.mqtt_service
    result = mqtt_service.process_rfid_event(sim_data.model_dump())
    return result


# ==============================================================================
# SYSTEM STATUS
# ==============================================================================

@api_router.get("/system/status")
def system_status(request: Request):
    config: AppConfig = request.app.state.config
    mqtt_service = request.app.state.mqtt_service
    abs_client = request.app.state.abs_client

    abs_status = abs_client.test_connection()

    return {
        "mqtt": {
            "connected": mqtt_service.is_connected,
            "broker": config.mqtt.broker,
            "port": config.mqtt.port,
            "topic_scanned": config.mqtt.topic_scanned,
            "topic_action": config.mqtt.topic_action
        },
        "audiobookshelf": {
            "base_url": config.audiobookshelf.base_url,
            "reachable": abs_status.get("success", False),
            "username": abs_status.get("username")
        },
        "media": {
            "warning_sound_uri": config.media.warning_sound_uri,
            "default_volume": config.media.default_volume,
            "integration_mode": config.media.integration_mode
        },
        "database": {
            "path": config.database_path
        }
    }


@api_router.get("/system/logs")
def get_system_logs(request: Request):
    """Liefert die letzten Log-Zeilen des Servers."""
    log_buf = getattr(request.app.state, "log_buffer", None)
    if log_buf:
        return {"logs": log_buf.get_logs()}
    return {"logs": ["Kein Log-Buffer aktiv."]}


class AbsDebugRequest(BaseModel):
    series_id: str
    library_id: Optional[str] = ""
    user_token: Optional[str] = ""


@api_router.post("/debug/abs-series")
def debug_abs_series(req_data: AbsDebugRequest, request: Request):
    """Führt eine detaillierte ABS-Diagnose für eine Serie und einen Token aus."""
    abs_client = request.app.state.abs_client
    token = req_data.user_token.strip() if req_data.user_token else None
    series_id = req_data.series_id.strip()
    library_id = req_data.library_id.strip() if req_data.library_id else None

    # 1. Verbindung und User-Check
    auth_info = abs_client.test_connection(user_token=token)

    # 2. Serien-Details
    series_details = abs_client.get_series_details(series_id, library_id=library_id, user_token=token)

    # 3. User Progress
    progress_map = abs_client.get_user_progress(user_token=token)

    # 4. Auflösung
    resolution = abs_client.resolve_next_book_in_series(series_id, library_id=library_id, user_token=token)

    books_breakdown = []
    if series_details:
        raw_books = series_details.get("books") or series_details.get("libraryItems") or series_details.get("items") or []
        for b in raw_books:
            b_id = str(b.get("id") or b.get("libraryItemId") or "")
            m_id = str(b.get("media", {}).get("id") or "") if isinstance(b.get("media"), dict) else ""
            b_title = b.get("media", {}).get("metadata", {}).get("title") or b.get("title") or b.get("name") or b_id
            seq_val = abs_client._extract_sequence(b, series_id)
            prog = progress_map.get(b_id) or (progress_map.get(m_id) if m_id else None)
            
            books_breakdown.append({
                "id": b_id,
                "media_id": m_id,
                "title": b_title,
                "sequence": seq_val,
                "has_progress_entry": prog is not None,
                "progress_details": prog
            })

    return {
        "auth_user": auth_info,
        "series_id": series_id,
        "library_id": library_id,
        "series_found": series_details is not None,
        "series_name": series_details.get("name") if series_details else None,
        "total_books_found": len(books_breakdown),
        "total_user_progress_entries": len(progress_map),
        "resolution_result": resolution,
        "books": books_breakdown
    }


# ==============================================================================
# FIRMWARE & FLASHER ENDPOINTS
# ==============================================================================

FIRMWARE_TEMPLATES = {
    "m5atom_lite_rfid": {
        "id": "m5atom_lite_rfid",
        "name": "M5Stack ATOM Lite + RFID 2 Unit (Grove I2C)",
        "recommended": True,
        "filename": "esphome_m5atom_lite_rfid.yaml",
        "description": "Kompakter ESP32 Controller mit integrierter RGB-Status-LED und Plug & Play Grove-Kabel.",
        "features": [
            "Plug & Play Grove-Kabelanschluss (kein Löten)",
            "RGB NeoPixel Status-LED für visuelles Feedback (Grün/Blau/Cyan/Orange/Rot)",
            "Hardware-Button für Status-Ping & Neustart",
            "Toniebox Präsenzerkennung (Auflegen = Play, Wegnehmen = Stop)",
            "Improv Wi-Fi & Web-Serial Flashing Support"
        ],
        "pinout": [
            {"pin": "Grove Gelb", "signal": "I2C SDA", "gpio": "GPIO 26"},
            {"pin": "Grove Weiß", "signal": "I2C SCL", "gpio": "GPIO 32"},
            {"pin": "Grove Rot", "signal": "Power (5V)", "gpio": "5V"},
            {"pin": "Grove Schwarz", "signal": "GND", "gpio": "GND"},
            {"pin": "Status LED", "signal": "WS2812 RGB", "gpio": "GPIO 27"},
            {"pin": "Front Button", "signal": "Push Button", "gpio": "GPIO 39"}
        ],
        "led_states": [
            {"color": "#10b981", "name": "Grün", "state": "Verbunden & Bereit (Normalbetrieb)"},
            {"color": "#3b82f6", "name": "Blau", "state": "Verbindungsaufbau zu WLAN / MQTT"},
            {"color": "#06b6d4", "name": "Cyan", "state": "Tag erkannt (Play-Befehl gesendet)"},
            {"color": "#f97316", "name": "Orange", "state": "Tag entfernt (Stop-Befehl gesendet)"},
            {"color": "#ef4444", "name": "Rot", "state": "Verbindungsfehler (WLAN/MQTT getrennt)"}
        ]
    },
    "esp32_pn532_i2c": {
        "id": "esp32_pn532_i2c",
        "name": "ESP32 NodeMCU + PN532 NFC (I2C)",
        "recommended": False,
        "filename": "esphome_pn532_i2c.yaml",
        "description": "Klassisches ESP32 Entwicklungsboard mit PN532 NFC Modul über I2C Bus.",
        "features": [
            "Hohe NFC-Reichweite",
            "I2C Bus Anbindung",
            "Toniebox Präsenzerkennung (Auflegen/Wegnehmen)"
        ],
        "pinout": [
            {"pin": "SDA", "signal": "I2C SDA", "gpio": "GPIO 21"},
            {"pin": "SCL", "signal": "I2C SCL", "gpio": "GPIO 22"},
            {"pin": "VCC", "signal": "Power (3.3V/5V)", "gpio": "3.3V oder 5V"},
            {"pin": "GND", "signal": "GND", "gpio": "GND"}
        ],
        "led_states": []
    },
    "esp32_rc522_spi": {
        "id": "esp32_rc522_spi",
        "name": "ESP32 NodeMCU + RC522 RFID (SPI)",
        "recommended": False,
        "filename": "esphome_rc522_spi.yaml",
        "description": "ESP32 Entwicklungsboard mit RC522 RFID Modul über SPI Bus.",
        "features": [
            "Kostengünstiges RFID Setup",
            "SPI Bus Anbindung",
            "Toniebox Präsenzerkennung (Auflegen/Wegnehmen)"
        ],
        "pinout": [
            {"pin": "SCK", "signal": "SPI Clock", "gpio": "GPIO 18"},
            {"pin": "MOSI", "signal": "SPI MOSI", "gpio": "GPIO 23"},
            {"pin": "MISO", "signal": "SPI MISO", "gpio": "GPIO 19"},
            {"pin": "SDA / CS", "signal": "Chip Select", "gpio": "GPIO 5"},
            {"pin": "RST", "signal": "Reset", "gpio": "GPIO 22"},
            {"pin": "3.3V", "signal": "Power", "gpio": "3.3V"},
            {"pin": "GND", "signal": "GND", "gpio": "GND"}
        ],
        "led_states": []
    }
}


def find_template_file(filename: str) -> Optional[Path]:
    """Sucht nach einer ESPHome Template-Datei in den typischen Pfaden."""
    search_dirs = [
        Path("/app/esphome"),
        Path("./esphome"),
        Path(__file__).parent.parent.parent / "esphome",
        Path(__file__).parent.parent / "esphome",
    ]
    for d in search_dirs:
        candidate = d / filename
        if candidate.is_file():
            return candidate
    return None


def substitute_yaml(template_content: str, substitutions: Dict[str, str]) -> str:
    """Ersetzt substitutions im ESPHome YAML sauber und erhält alle Kommentare."""
    content = template_content
    for k, v in substitutions.items():
        safe_v = str(v).replace('"', '\\"')
        content = re.sub(
            rf'(?m)^(\s*{re.escape(k)}:\s*)[^\n]+',
            rf'\1"{safe_v}"',
            content
        )
    return content


@api_router.get("/firmware/templates")
def list_firmware_templates():
    """Liefert alle verfügbaren Hardware- und Firmware-Profile."""
    return list(FIRMWARE_TEMPLATES.values())


@api_router.get("/firmware/generate-yaml")
def generate_firmware_yaml(
    request: Request,
    hardware_type: str = "m5atom_lite_rfid",
    reader_id: Optional[str] = None,
    device_name: Optional[str] = None,
    friendly_name: Optional[str] = None,
    wifi_ssid: Optional[str] = None,
    wifi_password: Optional[str] = None,
    mqtt_broker: Optional[str] = None,
    mqtt_port: Optional[int] = None,
    mqtt_user: Optional[str] = None,
    mqtt_password: Optional[str] = None,
    download: bool = False
):
    """Generiert eine maßgeschneiderte ESPHome-YAML mit den Docker MQTT-Zugangsdaten."""
    config: AppConfig = request.app.state.config

    if hardware_type not in FIRMWARE_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unbekannter Hardware-Typ: {hardware_type}")

    tmpl_info = FIRMWARE_TEMPLATES[hardware_type]
    tmpl_path = find_template_file(tmpl_info["filename"])
    if not tmpl_path:
        raise HTTPException(status_code=404, detail=f"Template-Datei {tmpl_info['filename']} nicht gefunden.")

    with open(tmpl_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # Standardwerte aus Config / Parametern ableiten
    final_reader_id = (reader_id or "reader_atom_1").strip()
    clean_dev_id = re.sub(r'[^a-zA-Z0-9_-]', '-', final_reader_id.lower()).replace('_', '-')
    
    final_device_name = (device_name or f"nfc-{clean_dev_id}").strip()
    final_friendly_name = (friendly_name or f"NFC Reader {final_reader_id.replace('_', ' ').title()}").strip()

    final_mqtt_broker = (mqtt_broker if mqtt_broker is not None else config.mqtt.broker) or "192.168.1.50"
    final_mqtt_port = mqtt_port if mqtt_port is not None else config.mqtt.port
    final_mqtt_user = (mqtt_user if mqtt_user is not None else (config.mqtt.username or ""))
    final_mqtt_pass = (mqtt_password if mqtt_password is not None else (config.mqtt.password or ""))

    final_wifi_ssid = (wifi_ssid or "YourWiFiSSID").strip()
    final_wifi_pass = (wifi_password or "YourWiFiPassword").strip()

    subs = {
        "device_name": final_device_name,
        "friendly_name": final_friendly_name,
        "reader_id": final_reader_id,
        "mqtt_broker": final_mqtt_broker,
        "mqtt_port": str(final_mqtt_port),
        "mqtt_user": final_mqtt_user,
        "mqtt_password": final_mqtt_pass,
        "wifi_ssid": final_wifi_ssid,
        "wifi_password": final_wifi_pass,
    }

    rendered_yaml = substitute_yaml(template_content, subs)
    filename = f"esphome_{final_reader_id}.yaml"

    if download:
        return PlainTextResponse(
            rendered_yaml,
            media_type="application/x-yaml",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    return {
        "yaml": rendered_yaml,
        "filename": filename,
        "hardware_type": hardware_type,
        "reader_id": final_reader_id,
        "substitutions": subs
    }


@api_router.get("/firmware/manifest/{hardware_type}")
def get_firmware_manifest(hardware_type: str):
    """Liefert ein ESP Web Tools Manifest für Browser-Flashen."""
    if hardware_type not in FIRMWARE_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unbekannter Hardware-Typ: {hardware_type}")

    tmpl_info = FIRMWARE_TEMPLATES[hardware_type]
    return {
        "name": tmpl_info["name"],
        "version": "0.3.1",
        "home_assistant_domain": "esphome",
        "new_install_prompt_erase": True,
        "builds": [
            {
                "chipFamily": "ESP32",
                "parts": [
                    {"path": f"/static/firmware/{hardware_type}/firmware.bin", "offset": 0}
                ]
            }
        ]
    }

