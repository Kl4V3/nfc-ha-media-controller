import os
import logging
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field


class MQTTConfig(BaseModel):
    broker: str = Field(default="localhost")
    port: int = Field(default=1883)
    username: Optional[str] = Field(default="")
    password: Optional[str] = Field(default="")
    client_id: str = Field(default="nfc_media_middleware")
    topic_scanned: str = Field(default="rfid/scanned")
    topic_action: str = Field(default="rfid/action")
    keepalive: int = Field(default=60)
    tls_enabled: bool = Field(default=False)


class AudiobookshelfConfig(BaseModel):
    base_url: str = Field(default="http://localhost:13378")
    default_token: str = Field(default="")
    timeout: float = Field(default=3.0)
    provider_prefix: str = Field(default="")  # z. B. "audiobookshelf--xPQT49LN"
    mass_instance_id: str = Field(default="")  # z. B. "xPQT49LN"


class MediaConfig(BaseModel):
    warning_sound_uri: str = Field(default="media-source://media_source/local/warningMissingNFC.wav")
    default_volume: int = Field(default=20)
    integration_mode: str = Field(default="mass")  # "mass" oder "media_player"


class ServerConfig(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=5000)
    log_level: str = Field(default="INFO")


class AppConfig(BaseModel):
    mqtt: MQTTConfig = Field(default_factory=MQTTConfig)
    audiobookshelf: AudiobookshelfConfig = Field(default_factory=AudiobookshelfConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    database_path: str = Field(default="/app/data/database.db")


def find_config_file() -> Optional[Path]:
    """Sucht nach einer vorhandenen config.yaml Datei an typischen Pfaden."""
    custom_path = os.getenv("CONFIG_PATH")
    if custom_path and Path(custom_path).is_file():
        return Path(custom_path)

    search_paths = [
        Path("/app/data/config.yaml"),
        Path("/app/config/config.yaml"),
        Path("./data/config.yaml"),
        Path("./config/config.yaml"),
        Path("./config/config.example.yaml"),
    ]
    for p in search_paths:
        if p.is_file():
            return p
    return None


def get_default_db_path() -> str:
    """Ermittelt den Pfad zur SQLite-Datenbank."""
    env_db = os.getenv("DATABASE_PATH")
    if env_db:
        return env_db
    
    # Prüfe ob /app/data existiert (Docker Container)
    if Path("/app/data").exists():
        return "/app/data/database.db"
    
    # Lokale Entwicklung
    local_data_dir = Path("./data")
    local_data_dir.mkdir(parents=True, exist_ok=True)
    return str(local_data_dir / "database.db")


def load_config() -> AppConfig:
    """Lädt die Konfiguration aus YAML und wendet Umgebungsvariablen-Overrides an."""
    config_dict = {}
    config_file = find_config_file()

    if config_file:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                if isinstance(content, dict):
                    config_dict = content
        except Exception as e:
            logging.warning(f"Konnte Konfigurationsdatei {config_file} nicht laden: {e}")

    # Pydantic Modell instanziieren
    config = AppConfig(**config_dict)
    config.database_path = get_default_db_path()

    # Environment Variable Overrides
    if os.getenv("MQTT_BROKER"):
        config.mqtt.broker = os.getenv("MQTT_BROKER")
    if os.getenv("MQTT_PORT"):
        try:
            config.mqtt.port = int(os.getenv("MQTT_PORT"))
        except ValueError:
            pass
    if os.getenv("MQTT_USERNAME") or os.getenv("MQTT_USER"):
        config.mqtt.username = os.getenv("MQTT_USERNAME") or os.getenv("MQTT_USER")
    if os.getenv("MQTT_PASSWORD"):
        config.mqtt.password = os.getenv("MQTT_PASSWORD")
    if os.getenv("MQTT_CLIENT_ID"):
        config.mqtt.client_id = os.getenv("MQTT_CLIENT_ID")
    if os.getenv("MQTT_TOPIC_SCANNED"):
        config.mqtt.topic_scanned = os.getenv("MQTT_TOPIC_SCANNED")
    if os.getenv("MQTT_TOPIC_ACTION"):
        config.mqtt.topic_action = os.getenv("MQTT_TOPIC_ACTION")

    if os.getenv("ABS_BASE_URL"):
        config.audiobookshelf.base_url = os.getenv("ABS_BASE_URL")
    if os.getenv("ABS_DEFAULT_TOKEN") or os.getenv("ABS_TOKEN"):
        config.audiobookshelf.default_token = os.getenv("ABS_DEFAULT_TOKEN") or os.getenv("ABS_TOKEN")
    if os.getenv("ABS_TIMEOUT"):
        try:
            config.audiobookshelf.timeout = float(os.getenv("ABS_TIMEOUT"))
        except ValueError:
            pass
    if os.getenv("ABS_PROVIDER_PREFIX") or os.getenv("AUDIOBOOKSHELF_PROVIDER_PREFIX") or os.getenv("MASS_ABS_PROVIDER_PREFIX"):
        config.audiobookshelf.provider_prefix = (
            os.getenv("ABS_PROVIDER_PREFIX")
            or os.getenv("AUDIOBOOKSHELF_PROVIDER_PREFIX")
            or os.getenv("MASS_ABS_PROVIDER_PREFIX")
        )
    if os.getenv("MASS_ABS_INSTANCE_ID") or os.getenv("ABS_INSTANCE_ID"):
        config.audiobookshelf.mass_instance_id = os.getenv("MASS_ABS_INSTANCE_ID") or os.getenv("ABS_INSTANCE_ID")

    if os.getenv("WARNING_SOUND_URI"):
        config.media.warning_sound_uri = os.getenv("WARNING_SOUND_URI")
    if os.getenv("DEFAULT_VOLUME"):
        try:
            config.media.default_volume = int(os.getenv("DEFAULT_VOLUME"))
        except ValueError:
            pass
    if os.getenv("INTEGRATION_MODE"):
        config.media.integration_mode = os.getenv("INTEGRATION_MODE")

    if os.getenv("SERVER_HOST"):
        config.server.host = os.getenv("SERVER_HOST")
    if os.getenv("SERVER_PORT"):
        try:
            config.server.port = int(os.getenv("SERVER_PORT"))
        except ValueError:
            pass
    if os.getenv("LOG_LEVEL"):
        config.server.log_level = os.getenv("LOG_LEVEL")

    return config
