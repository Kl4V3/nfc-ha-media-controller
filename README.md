# NFC Media Controller 🎵🏷️

[![Docker Image](https://img.shields.io/docker/v/theklave/nfc-ha-media-controller?label=Docker%20Hub&logo=docker)](https://hub.docker.com/r/theklave/nfc-ha-media-controller)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python)](https://www.python.org/)

A modular, event-driven middleware to control multi-room audio (**Music Assistant**, **Audiobookshelf**, **Home Assistant**) and smart home scenes using NFC/RFID tags following the **Toniebox principle** (Tag Placed = Play, Tag Removed = Stop).

---

## 📑 Table of Contents

- [System Architecture](#-system-architecture)
- [Key Features](#-key-features)
- [Quick Start with Docker](#-quick-start-with-docker)
- [Configuration & Environment Variables](#-configuration--environment-variables)
- [Audiobookshelf & Series Progress](#-audiobookshelf--series-progress)
- [Hardware & ESPHome Setup](#-hardware--esphome-setup)
- [Home Assistant Integration](#-home-assistant-integration)
- [Security & NGINX Reverse Proxy](#-security--nginx-reverse-proxy)
- [REST API & WebSocket Reference](#-rest-api--websocket-reference)
- [Development & Building from Source](#-development--building-from-source)
- [License](#-license)

---

## 📐 System Architecture

```text
┌────────────────────────────────────────────────────────┐
│                   1. Hardware & Trigger                │
│ ESPHome (ESP32 / ESP8266 + PN532 or RC522)             │
│   ├── Tag placed  -> MQTT "rfid/scanned" (status: scanned)│
│   └── Tag removed -> MQTT "rfid/scanned" (status: removed)│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                 2. Docker Middleware                   │
│ Python (FastAPI + Paho-MQTT + SQLite)                  │
│   ├── Auto-Discovery & Warning Sound for New Tags      │
│   ├── Audiobookshelf API (Next Unfinished Book)        │
│   ├── Web Dashboard (Port 5000) & REST API             │
│   └── MQTT Publisher -> "rfid/action"                  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               3. Execution (Home Assistant)            │
│ HA Automation / Blueprint                              │
│   ├── status == removed -> media_player.media_stop     │
│   ├── action_type == warning -> Play warning sound     │
│   ├── action_type == media -> mass.play_media          │
│   └── action_type == light/scene -> light.turn_on      │
└───────────────────────────┘
```

---

## 🌟 Key Features

- **Toniebox Presence Detection:**
  - **Tag Placed (`scanned`):** Immediately plays the assigned audiobook, series, or playlist on the room speaker.
  - **Tag Removed (`removed`):** Instantly sends a stop command (`media_player.media_stop`) to the designated player.
- **Audiobookshelf Integration with Series Progress:**
  - Automatically resolves the **next unfinished book** in a series for the respective user.
  - **Multi-User Support:** Assign distinct ABS user tokens to each reader/room to track listening progress independently.
  - **Fault Tolerant:** Enforced 3-second timeout prevents thread blocking if the ABS server is offline.
- **Auto-Discovery & Safe Fallback:**
  - Unknown tags are automatically registered in the SQLite database upon first scan.
  - Unconfigured tags trigger a configurable **warning sound** immediately instead of causing playback errors.
- **Modern Responsive Web Dashboard (Port 5000):**
  - Manage tags, aliases, volumes, shuffle mode, and room reader assignments.
  - Integrated **ABS Series Explorer** (1-click series ID selection).
  - **Real-Time Live Feed** via WebSockets for instant scan visual feedback.
  - **Interactive Hardware Simulator** to test tags and events without physical hardware.

---

## 🚀 Quick Start with Docker

The easiest way to run the NFC Media Controller is using Docker Compose.

### 1. Create `docker-compose.yml`

```yaml
services:
  nfc-media-controller:
    image: theklave/nfc-ha-media-controller:latest
    container_name: nfc_media_controller
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
    environment:
      - TZ=Europe/Berlin
      # MQTT Broker Settings
      - MQTT_BROKER=192.168.1.50
      - MQTT_PORT=1883
      - MQTT_USER=nfc_user
      - MQTT_PASSWORD=secret_password
      - MQTT_TOPIC_SCANNED=rfid/scanned
      - MQTT_TOPIC_ACTION=rfid/action
      # Audiobookshelf Settings (Optional)
      - ABS_BASE_URL=http://192.168.1.50:13378
      - ABS_DEFAULT_TOKEN=your_abs_api_token
      - LOG_LEVEL=INFO
```

### 2. Start the Container

```bash
docker compose up -d
```

### 3. Open the Web Dashboard

Open your browser and navigate to:
👉 **`http://<your-server-ip>:5000`**

---

## ⚙️ Configuration & Environment Variables

All settings can be configured via **Docker Compose environment variables** or by mounting a configuration file to **`/app/data/config.yaml`** (see [`config/config.example.yaml`](config/config.example.yaml)).

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| `MQTT_BROKER` | Hostname or IP of your MQTT Broker | `192.168.1.50` or `mosquitto` |
| `MQTT_PORT` | Port of your MQTT Broker | `1883` |
| `MQTT_USER` | MQTT Username | `nfc_user` |
| `MQTT_PASSWORD` | MQTT Password | `secret_password` |
| `MQTT_TOPIC_SCANNED` | Topic where readers publish scan events | `rfid/scanned` |
| `MQTT_TOPIC_ACTION` | Topic where HA listens for actions | `rfid/action` |
| `ABS_BASE_URL` | Audiobookshelf Server base URL | `http://192.168.1.50:13378` |
| `ABS_DEFAULT_TOKEN` | Fallback ABS API Token | `eyJhbGciOi...` |
| `ABS_TIMEOUT` | Timeout for ABS queries in seconds | `3.0` |
| `WARNING_SOUND_URI` | Sound URL played for unconfigured tags | `http://homeassistant.local:8123/local/sounds/warning.mp3` |
| `DEFAULT_VOLUME` | Default playback volume percentage | `20` |
| `INTEGRATION_MODE` | `mass` (Music Assistant) or `media_player` | `mass` |
| `SERVER_PORT` | Web UI Port | `5000` |
| `LOG_LEVEL` | Log level verbosity | `INFO` (`DEBUG`, `WARNING`) |

---

## 📚 Audiobookshelf & Series Progress

When a tag is configured with the action type **`Serie`**:
1. When placed on a reader, the middleware queries the books in the ABS series (`target_id`).
2. The user's listening progress is checked against `/api/me/progress`.
3. The first book that is not marked as `isFinished` (and <98% listened) is chosen.
4. The media URI (e.g. `audiobookshelf://track/{book_id}`) is published to Home Assistant.

### Multi-User Support (Independent Progress per Room)
In the Web Dashboard under **Readers & Zones**:
- Set each reader's personal ABS User Token (e.g. for `reader_kids_room_1`).
- Each room maintains its own separate listening progress, even when listening to the same series!

---

## 🔌 Hardware & ESPHome Setup

### Recommended Hardware
- **Microcontroller:** ESP32 NodeMCU or ESP8266 (D1 Mini)
- **NFC/RFID Reader:** PN532 (I2C) or RC522 (SPI)
- **Tags:** NTAG213 / NTAG215 / NTAG216 cards, stickers, or tags

### ESPHome Configuration Templates
- **PN532 (I2C):** Complete configuration with presence polling loop in [`esphome/esphome_pn532_i2c.yaml`](esphome/esphome_pn532_i2c.yaml).
- **RC522 (SPI):** Template in [`esphome/esphome_rc522_spi.yaml`](esphome/esphome_rc522_spi.yaml).

---

## 🏠 Home Assistant Integration

Home Assistant requires exactly **one automation** listening to `rfid/action`:

1. Copy the YAML from [`homeassistant/automations.yaml`](homeassistant/automations.yaml) into your Home Assistant automations.
2. Alternatively: Import the Blueprint from [`homeassistant/blueprint_nfc_media.yaml`](homeassistant/blueprint_nfc_media.yaml).

---

## 🔒 Security & NGINX Reverse Proxy

To secure the dashboard from unauthorized access on your local network, place it behind an NGINX reverse proxy with **Basic Authentication** (`.htpasswd`) or IP whitelisting. An example configuration with WebSocket support is provided in [`nginx/nginx_example.conf`](nginx/nginx_example.conf).

---

## 📡 REST API & WebSocket Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/tags` | `GET`, `POST` | List all tags or create/update |
| `/api/tags/{tag_id}` | `GET`, `PUT`, `DELETE` | Read, update, or delete a specific tag |
| `/api/readers` | `GET`, `POST` | List all readers or create/update |
| `/api/readers/{reader_id}` | `GET`, `PUT`, `DELETE` | Manage a specific reader mapping |
| `/api/abs/series` | `GET` | List series from Audiobookshelf |
| `/api/test/scan` | `POST` | Simulate a tag scan (scanned/removed) |
| `/api/history` | `GET` | Retrieve the last 50 scan events |
| `/api/system/status` | `GET` | Check connectivity of MQTT, ABS, and SQLite |
| `/ws` | `WebSocket` | Real-time live event feed |

---

## 🛠️ Development & Building from Source

If you want to contribute or build the container locally:

```bash
# Clone the repository
git clone https://github.com/Kl4V3/nfc-ha-media-controller.git
cd nfc-ha-media-controller

# Setup virtual environment & dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the test suite (16 tests)
pytest -v tests/

# Build and run with Docker Compose locally
docker compose up -d --build
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
