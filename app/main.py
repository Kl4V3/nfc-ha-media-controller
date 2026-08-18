import os
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_config, AppConfig
from app.database import init_db
from app.audiobookshelf import AudiobookshelfClient
from app.mqtt_client import MQTTService
from app.routes.api import api_router
from app.routes.ws import ws_router, ws_manager

# Logging einrichten
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nfc_controller")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle-Manager für Initialisierung und sauberes Herunterfahren."""
    logger.info("Starte NFC Media Controller...")

    # 1. Konfiguration laden (falls nicht für Tests vorinitialisiert)
    if not hasattr(app.state, "config") or not app.state.config:
        config: AppConfig = load_config()
        app.state.config = config
    else:
        config = app.state.config

    # Log Level anpassen
    logging.getLogger().setLevel(getattr(logging, config.server.log_level.upper(), logging.INFO))

    # 2. SQLite-Datenbank initialisieren
    init_db(config.database_path)

    # 3. Audiobookshelf Client erstellen
    if not hasattr(app.state, "abs_client") or not app.state.abs_client:
        abs_client = AudiobookshelfClient(
            base_url=config.audiobookshelf.base_url,
            default_token=config.audiobookshelf.default_token,
            timeout=config.audiobookshelf.timeout
        )
        app.state.abs_client = abs_client
    else:
        abs_client = app.state.abs_client

    # 4. MQTT Service initialisieren & starten
    if not hasattr(app.state, "mqtt_service") or not app.state.mqtt_service:
        mqtt_service = MQTTService(config=config, abs_client=abs_client)
        app.state.mqtt_service = mqtt_service
    else:
        mqtt_service = app.state.mqtt_service

    # Event-Bridge: Leitet synchrone MQTT-Events an den asynchronen WebSocket-Manager weiter
    main_loop = asyncio.get_running_loop()

    def sync_event_listener(event_data: dict):
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast(event_data),
            main_loop
        )

    mqtt_service.register_event_listener(sync_event_listener)
    mqtt_service.start()

    yield

    # Shutdown
    logger.info("Beende NFC Media Controller...")
    mqtt_service.unregister_event_listener(sync_event_listener)
    mqtt_service.stop()


app = FastAPI(
    title="NFC Media Controller",
    description="RFID/NFC Middleware für ESPHome, Audiobookshelf & Home Assistant",
    version="1.0.0",
    lifespan=lifespan
)

# Statische Dateien und Templates
base_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(base_dir / "templates"))

# Router einbinden
app.include_router(api_router)
app.include_router(ws_router)


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Liefert das Haupt-Dashboard / Frontend aus."""
    config: AppConfig = request.app.state.config
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "config": config,
            "version": "1.0.0"
        }
    )


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(
        "app.main:app",
        host=cfg.server.host,
        port=cfg.server.port,
        reload=False
    )
