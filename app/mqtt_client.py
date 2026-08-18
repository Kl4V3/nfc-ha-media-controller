import json
import logging
import time
import threading
from typing import Dict, Any, Callable, Optional, List
import paho.mqtt.client as mqtt

from app import __version__
from app.config import AppConfig
from app.database import (
    get_reader_by_id,
    upsert_reader,
    get_tag_by_id,
    auto_discover_or_update_tag,
    add_scan_history
)
from app.audiobookshelf import AudiobookshelfClient

logger = logging.getLogger(__name__)


class MQTTService:
    """Verwaltet die MQTT-Verbindung, Event-Verarbeitung und Publishing."""

    def __init__(self, config: AppConfig, abs_client: AudiobookshelfClient):
        self.config = config
        self.abs_client = abs_client
        self.client: Optional[mqtt.Client] = None
        self.is_connected = False
        self.event_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.Lock()

    def register_event_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """Registriert einen Listener für Live-Events (z. B. WebSocket Dispatcher)."""
        with self._lock:
            if callback not in self.event_listeners:
                self.event_listeners.append(callback)

    def unregister_event_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """Entfernt einen Event-Listener."""
        with self._lock:
            if callback in self.event_listeners:
                self.event_listeners.remove(callback)

    def _broadcast_event(self, event_data: Dict[str, Any]):
        """Sendet Ereignisse an alle registrierten Listener."""
        with self._lock:
            listeners = list(self.event_listeners)
        for listener in listeners:
            try:
                listener(event_data)
            except Exception as e:
                logger.error(f"Fehler beim Aufruf des Event-Listeners: {e}")

    def start(self):
        """Initialisiert und startet den MQTT-Client im Hintergrund-Thread."""
        try:
            # Paho MQTT 2.0 API Support
            if hasattr(mqtt, "CallbackAPIVersion"):
                self.client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id=self.config.mqtt.client_id
                )
            else:
                self.client = mqtt.Client(client_id=self.config.mqtt.client_id)

            if self.config.mqtt.username and self.config.mqtt.password:
                self.client.username_pw_set(
                    self.config.mqtt.username,
                    self.config.mqtt.password
                )

            if self.config.mqtt.tls_enabled:
                self.client.tls_set()

            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            logger.info(f"Verbinde zu MQTT Broker {self.config.mqtt.broker}:{self.config.mqtt.port}...")
            self.client.connect_async(
                self.config.mqtt.broker,
                self.config.mqtt.port,
                keepalive=self.config.mqtt.keepalive
            )
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Fehler beim Starten des MQTT-Clients: {e}")

    def stop(self):
        """Beendet die MQTT-Verbindung sauber."""
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("MQTT-Client gestoppt.")
            except Exception as e:
                logger.warning(f"Fehler beim Stoppen des MQTT-Clients: {e}")

    def publish(self, topic: str, payload: Dict[str, Any]) -> bool:
        """Publiziert eine JSON-Nachricht auf ein MQTT-Topic."""
        if not self.client:
            logger.warning("MQTT-Client nicht initialisiert. Nachricht konnte nicht gesendet werden.")
            return False
        try:
            payload_str = json.dumps(payload, ensure_ascii=False)
            info = self.client.publish(topic, payload_str, qos=1)
            logger.info(f"MQTT Publish an [{topic}]: {payload_str}")
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Fehler beim Publizieren an [{topic}]: {e}")
            return False

    def _publish_ha_discovery(self):
        """Sendet Home Assistant MQTT Discovery-Payloads für automatische Geräteerkennung."""
        try:
            device_info = {
                "identifiers": ["nfc_media_controller"],
                "name": "NFC Media Controller",
                "model": "NFC HA Middleware",
                "manufacturer": "theklave",
                "sw_version": __version__
            }

            # 1. Sensor: Letzter gescannter Titel / Tag
            last_tag_config = {
                "name": "Last Scanned Media",
                "unique_id": "nfc_controller_last_scanned_media",
                "state_topic": self.config.mqtt.topic_action,
                "value_template": "{{ value_json.metadata.title | default(value_json.metadata.alias) | default(value_json.target_id) | default(value_json.status) }}",
                "json_attributes_topic": self.config.mqtt.topic_action,
                "icon": "mdi:nfc-variant",
                "device": device_info
            }
            self.publish("homeassistant/sensor/nfc_media_controller/last_media/config", last_tag_config)

            # 2. Sensor: Letzter aktiver Reader
            last_reader_config = {
                "name": "Last Active Reader",
                "unique_id": "nfc_controller_last_active_reader",
                "state_topic": self.config.mqtt.topic_action,
                "value_template": "{{ value_json.reader_id | default('None') }}",
                "icon": "mdi:radio-tower",
                "device": device_info
            }
            self.publish("homeassistant/sensor/nfc_media_controller/last_reader/config", last_reader_config)

            # 3. Sensor: Status / Aktion
            last_status_config = {
                "name": "Last Action Type",
                "unique_id": "nfc_controller_last_action_type",
                "state_topic": self.config.mqtt.topic_action,
                "value_template": "{{ value_json.action_type | default(value_json.status) }}",
                "icon": "mdi:play-circle-outline",
                "device": device_info
            }
            self.publish("homeassistant/sensor/nfc_media_controller/last_action/config", last_status_config)

            logger.info("Home Assistant MQTT Discovery Payloads erfolgreich publiziert.")
        except Exception as e:
            logger.warning(f"Fehler bei HA Discovery Publishing: {e}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback bei erfolgreicher MQTT-Verbindung."""
        if rc == 0:
            self.is_connected = True
            topic = self.config.mqtt.topic_scanned
            logger.info(f"MQTT verbunden! Abonniere Topic: {topic}")
            client.subscribe(topic, qos=1)
            client.subscribe(f"{topic}/#", qos=1)
            self._publish_ha_discovery()
            self._broadcast_event({
                "type": "mqtt_status",
                "connected": True,
                "broker": self.config.mqtt.broker
            })
        else:
            self.is_connected = False
            logger.error(f"MQTT Verbindung fehlgeschlagen mit Return-Code: {rc}")
            self._broadcast_event({
                "type": "mqtt_status",
                "connected": False,
                "error": f"Return code {rc}"
            })

    def _on_disconnect(self, client, userdata, rc, properties=None):
        """Callback bei Verbindungsabbruch."""
        self.is_connected = False
        logger.warning(f"MQTT Verbindung getrennt (Code {rc}). Automatischer Reconnect aktiv...")
        self._broadcast_event({
            "type": "mqtt_status",
            "connected": False
        })

    def _on_message(self, client, userdata, msg):
        """Callback beim Empfang einer Nachricht auf rfid/scanned."""
        try:
            payload_str = msg.payload.decode("utf-8")
            logger.debug(f"MQTT Nachricht empfangen auf [{msg.topic}]: {payload_str}")
            data = json.loads(payload_str)
            self.process_rfid_event(data)
        except json.JSONDecodeError:
            logger.warning(f"Ungültiges JSON-Format empfangen auf [{msg.topic}]: {msg.payload}")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler bei MQTT-Nachrichtenverarbeitung: {e}", exc_info=True)

    def process_rfid_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Zentrale Geschäftslogik für eingehende RFID-Events (Auflegen/Entfernen).
        Wird auch für den Test-Simulator im Web-Frontend verwendet.
        """
        tag_id = str(data.get("tag_id", "")).strip()
        reader_id = str(data.get("reader_id", "")).strip()
        status = str(data.get("status", "scanned")).strip().lower()

        if not tag_id or not reader_id:
            logger.warning(f"Ungültiger RFID-Event ohne tag_id oder reader_id: {data}")
            return {"error": "Missing tag_id or reader_id"}

        db_path = self.config.database_path

        # 1. Reader aus der Datenbank ermitteln oder neu anlegen (Auto-Discovery)
        reader = get_reader_by_id(db_path, reader_id)
        if reader and reader.get("target_player"):
            target_player = reader["target_player"]
            abs_user_token = reader.get("abs_user_token") or self.config.audiobookshelf.default_token
        else:
            target_player = f"media_player.{reader_id}"
            abs_user_token = self.config.audiobookshelf.default_token
            upsert_reader(db_path, {
                "reader_id": reader_id,
                "target_player": target_player,
                "abs_user_token": "",
                "notes": f"Auto-discovered ({time.strftime('%Y-%m-%d %H:%M')})"
            })
            logger.info(f"Auto-Discovery: Neuer Reader '{reader_id}' registriert -> Default Player: '{target_player}'")
            self._broadcast_event({
                "type": "reader_discovered",
                "reader_id": reader_id,
                "target_player": target_player
            })

        # 2. Tag-Removed-Event (Toniebox-Prinzip)
        if status == "removed":
            stop_payload = {
                "status": "removed",
                "action_type": "stop",
                "reader_id": reader_id,
                "target_player": target_player
            }
            logger.info(f"Tag '{tag_id}' entfernt von '{reader_id}'. Sende Stop-Befehl an '{target_player}'")
            self.publish(self.config.mqtt.topic_action, stop_payload)
            
            add_scan_history(
                db_path,
                tag_id=tag_id,
                reader_id=reader_id,
                status="removed",
                action_executed="stop",
                payload=json.dumps(stop_payload)
            )

            event = {
                "type": "rfid_event",
                "status": "removed",
                "tag_id": tag_id,
                "reader_id": reader_id,
                "target_player": target_player,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._broadcast_event(event)
            return stop_payload

        # 3. Tag-Scanned-Event (Auflegen)
        tag = auto_discover_or_update_tag(db_path, tag_id)
        action_type = (tag.get("action_type") or "").strip()

        # 3a. Auto-Discovery & Unkonfigurierte Tags -> Warn-Sound sofort publizieren
        if tag.get("is_new") or not action_type:
            warn_volume = tag.get("volume") if tag.get("volume") is not None else self.config.media.default_volume
            warning_payload = {
                "status": "warning",
                "action_type": "warning",
                "reader_id": reader_id,
                "target_player": target_player,
                "target_id": self.config.media.warning_sound_uri,
                "volume": warn_volume,
                "message": "Tag not configured in database"
            }
            logger.warning(f"Unkonfigurierter Tag '{tag_id}' auf Reader '{reader_id}' gescannt. Sende Warn-Payload.")
            self.publish(self.config.mqtt.topic_action, warning_payload)

            add_scan_history(
                db_path,
                tag_id=tag_id,
                reader_id=reader_id,
                status="scanned",
                action_executed="warning",
                payload=json.dumps(warning_payload)
            )

            event = {
                "type": "rfid_event",
                "status": "warning",
                "is_new": tag.get("is_new", False),
                "tag_id": tag_id,
                "alias": tag.get("alias"),
                "reader_id": reader_id,
                "target_player": target_player,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._broadcast_event(event)
            return warning_payload

        # 4. Konfigurierter Tag -> Aktion ermitteln
        volume = tag.get("volume") if tag.get("volume") is not None else self.config.media.default_volume
        random_flag = tag.get("random", False)
        extra_params = tag.get("extra_params_parsed", {})
        target_id = tag.get("target_id", "").strip()
        metadata = {
            "alias": tag.get("alias")
        }

        normalized_action = action_type.lower()
        media_type = "track"

        # 4a. Audiobookshelf Serie (dynamische Auflösung des nächsten unfertigen Buchs)
        if normalized_action in ["serie", "abs_serie"]:
            series_id = target_id
            library_id = (tag.get("library_id") or "").strip() or None
            logger.info(f"Ermittle nächstes Buch für ABS-Serie '{series_id}' (Library: '{library_id or 'Auto'}', User-Token: {'vorhanden' if abs_user_token else 'fehlt'})...")
            book_info = self.abs_client.resolve_next_book_in_series(series_id, library_id=library_id, user_token=abs_user_token)

            if book_info and book_info.get("book_id"):
                book_id = book_info["book_id"]
                target_id = f"audiobookshelf://track/{book_id}"
                metadata["title"] = book_info.get("title")
                metadata["series_name"] = book_info.get("series_name")
                metadata["sequence"] = book_info.get("sequence")
                metadata["total_books"] = book_info.get("total_books")
                logger.info(f"ABS Serie '{book_info.get('series_name')}' aufgelöst: '{book_info.get('title')}' (ID: {book_id})")
            else:
                if not (target_id.startswith("audiobookshelf://") or target_id.startswith("mass://")):
                    target_id = f"audiobookshelf://track/{target_id}"
                logger.warning(f"Konnte nächstes Buch für Serie '{series_id}' nicht über ABS auflösen. Sende URI: {target_id}")

            action_type_out = "media"
            media_type = "track"

        # 4b. Einzelnes Hörbuch
        elif normalized_action in ["hoerbuch", "hörbuch", "audiobook"]:
            action_type_out = "media"
            media_type = "track"
            if not (target_id.startswith("audiobookshelf://") or target_id.startswith("mass://") or target_id.startswith("http")):
                target_id = f"audiobookshelf://track/{target_id}"

        # 4c. Album (Music Assistant)
        elif normalized_action in ["album"]:
            action_type_out = "media"
            media_type = "album"
            if not (target_id.startswith("mass://") or target_id.startswith("spotify://") or target_id.startswith("http")):
                target_id = f"mass://album/{target_id}"

        # 4d. Playlist (Music Assistant)
        elif normalized_action in ["playlist"]:
            action_type_out = "media"
            media_type = "playlist"
            if not (target_id.startswith("mass://") or target_id.startswith("spotify://") or target_id.startswith("http")):
                target_id = f"mass://playlist/{target_id}"

        # 4d. Lichtsteuerung
        elif normalized_action in ["licht", "light"]:
            action_type_out = "light"

        # 4e. Szenensteuerung
        elif normalized_action in ["szene", "scene"]:
            action_type_out = "scene"

        # 4f. Benutzerdefiniert
        else:
            action_type_out = action_type.lower()

        # 5. Finalen standardisierten Action-Payload zusammenbauen und publizieren
        final_payload = {
            "status": "scanned",
            "action_type": action_type_out,
            "reader_id": reader_id,
            "target_player": target_player,
            "target_id": target_id,
            "volume": volume,
            "random": random_flag,
            "extra_params": extra_params
        }

        if action_type_out == "media":
            final_payload["media_type"] = media_type

        if metadata:
            final_payload["metadata"] = metadata

        logger.info(f"Publiziere Action für Tag '{tag.get('alias')}' ({tag_id}) an '{target_player}'")
        self.publish(self.config.mqtt.topic_action, final_payload)

        # In Historie speichern
        add_scan_history(
            db_path,
            tag_id=tag_id,
            reader_id=reader_id,
            status="scanned",
            action_executed=action_type_out,
            payload=json.dumps(final_payload)
        )

        # Live Event an UI senden
        event = {
            "type": "rfid_event",
            "status": "scanned",
            "tag_id": tag_id,
            "alias": tag.get("alias"),
            "action_type": action_type_out,
            "media_type": media_type if action_type_out == "media" else None,
            "reader_id": reader_id,
            "target_player": target_player,
            "target_id": target_id,
            "resolved_title": metadata.get("title"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._broadcast_event(event)

        return final_payload
