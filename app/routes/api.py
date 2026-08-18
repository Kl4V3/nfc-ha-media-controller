import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, Request
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
    target_id: Optional[str] = Field(default="")
    volume: Optional[int] = Field(default=None, ge=0, le=100)
    random: Optional[bool] = Field(default=False)
    extra_params: Optional[Any] = Field(default="{}")


class ReaderModel(BaseModel):
    reader_id: str = Field(..., min_length=1)
    target_player: str = Field(..., min_length=1)
    abs_user_token: Optional[str] = Field(default="")
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
def get_abs_series(request: Request, library_id: Optional[str] = None, token: Optional[str] = None):
    abs_client = request.app.state.abs_client
    return abs_client.get_series_list(library_id=library_id, user_token=token)


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
    return {
        "success": True,
        "input": sim_data.model_dump(),
        "action_result": result
    }


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
