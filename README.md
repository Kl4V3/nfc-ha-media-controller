# NFC Media Controller 🎵🏷️

[![Docker Image](https://img.shields.io/docker/v/theklave/nfc-ha-media-controller?label=Docker%20Hub&logo=docker)](https://hub.docker.com/r/theklave/nfc-ha-media-controller)
[![Release](https://img.shields.io/badge/version-0.3.5-brightgreen.svg)](https://github.com/Kl4V3/nfc-ha-media-controller/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python)](https://www.python.org/)

An event-driven, multi-room audio and smart home middleware designed around the **Toniebox principle** (**Place Tag = Play, Remove Tag = Stop**).

Seamlessly connects custom RFID/NFC hardware readers to **Home Assistant**, **Music Assistant**, and **Audiobookshelf**.

---

## 📑 Table of Contents

- [System Architecture](#-system-architecture)
- [Key Features](#-key-features)
- [Hardware Setups](#-hardware-setups)
  - [ESP32 + PN5180 (Toniebox Figures & ISO-15693 / ISO-14443)](#1--esp32--nxp-pn5180-recommended-for-toniebox-figures)
  - [M5Stack ATOM Lite + RFID 2 Unit (Plug & Play Grove)](#2--m5stack-atom-lite--rfid-2-unit-plug--play-no-soldering)
  - [Other ESPHome Setups (PN532 / RC522)](#3-esp32-with-pn532-or-rc522)
- [Quick Start with Docker](#-quick-start-with-docker)
- [Configuration & Environment Variables](#-configuration--environment-variables)
- [Home Assistant Automation Setup](#-home-assistant-automation-setup)
- [Audiobookshelf, Series & Podcast Management](#-audiobookshelf-series--podcast-management)
- [Web Dashboard & Firmware Flasher](#-web-dashboard--firmware-flasher)
- [REST API & WebSocket Reference](#-rest-api--websocket-reference)
- [Local Development & Testing](#-local-development--testing)
- [License](#-license)

---

## 📐 System Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          1. Hardware Readers                           │
│  ESP32 + PN5180 (Tonie figures & NFC) OR M5Stack / ESPHome RFID       │
│    ├── Tag placed  -> MQTT "rfid/scanned"  {"status": "scanned", ...}  │
│    └── Tag removed -> MQTT "rfid/scanned"  {"status": "removed", ...}  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        2. Docker Middleware                            │
│  FastAPI + Paho-MQTT + SQLite + Audiobookshelf API                     │
│    ├── Auto-Discovery & Warning Sound for New/Unconfigured Tags        │
│    ├── Audiobookshelf API (Resolves next unplayed book or podcast)     │
│    ├── Multi-User Token Routing (Room-specific listening progress)     │
│    ├── "Always Start from Beginning" Progress Reset & Seek             │
│    ├── Web Dashboard (Port 5000) & Firmware Config Generator           │
│    └── Dispatches Unified Action Payload -> MQTT "rfid/action"         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    3. Execution (Home Assistant)                       │
│  Home Assistant Script / Automation                                    │
│    ├── status == "removed" -> media_player.media_stop                  │
│    ├── action == "warning" -> Plays configurable missing tag sound     │
│    ├── action == "media"   -> music_assistant.play_media               │
│    │                          + media_player.media_seek (if from start)│
│    └── action == "scene"   -> scene.turn_on                            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🌟 Key Features

- **True Toniebox Presence Detection:**
  - **Tag Placed (`scanned`):** Immediately plays the assigned audiobook, series, podcast, or album on the designated media player.
  - **Tag Removed (`removed`):** Instantly stops playback (`media_player.media_stop`).
- **Full Toniebox Figure Support:**
  - Dedicated firmware for **NXP PN5180** NFC readers unlocks original Tonie figures using the **iCode SLIX2 Privacy Mode password handshake** (`0x5B 0x6E 0xFD 0x7F`).
- **Smart Audiobook & Series Progress (Audiobookshelf):**
  - For series, the middleware automatically resolves the **next unfinished book** in chronological order based on the user's progress.
  - When all books in a series are completed, it seamlessly loops back to book 1.
- **Always Start from Beginning (⏮️):**
  - Optional setting for individual audiobooks and series to always start playback from `0:00`, while preserving series auto-advancement logic.
- **Podcast Episode Resolution:**
  - Automatically identifies and queues the **latest unfinished podcast episode** from Audiobookshelf or Music Assistant (`library://podcast/<id>`).
- **Multi-User Progress Isolation:**
  - Assign separate Audiobookshelf user tokens to different readers/rooms so multiple listeners can enjoy the same series independently without overwriting each other's progress.
- **Auto-Discovery & Safe Missing-Tag Fallback:**
  - Scanned unknown tags are automatically registered in the SQLite database.
  - Unconfigured tags trigger a pleasant warning sound notification instead of silent playback failures.
- **Responsive Web Dashboard:**
  - Default **English interface** with German translation support (`language: "de"`).
  - Audiobookshelf Explorer & In-Modal Picker for 1-click book/series/podcast ID assignment.
  - Firmware generator with ready-to-flash `config.h` and ESPHome YAML outputs.
  - Real-time live event feed via WebSockets.

---

## 🔌 Hardware Setups

### 1. ⭐ ESP32 + NXP PN5180 (Recommended for Toniebox Figures)

Standard NFC modules (such as RC522 or PN532) only support ISO-14443 and cannot read Toniebox figures. Original Toniebox figures use **NXP ICODE SLIX2 (ISO-15693)** chips operating in a special **Privacy Mode**.

The **NXP PN5180** features full ISO-15693 hardware support and can execute custom SPI commands to unlock and read Tonie figures.

#### Wiring Diagram (SPI)

| PN5180 Pin | ESP32 GPIO | Description |
| :--- | :--- | :--- |
| **MOSI** | **GPIO 23** | SPI Master Out Slave In |
| **MISO** | **GPIO 19** | SPI Master In Slave Out |
| **SCK** | **GPIO 18** | SPI Clock |
| **NSS / CS** | **GPIO 5** | SPI Chip Select |
| **BUSY** | **GPIO 21** | PN5180 Busy State |
| **RST** | **GPIO 22** | PN5180 Reset |
| **3.3V / 5V** | **3.3V / 5V** | Power Supply (Ensure clean 3.3V/5V) |
| **GND** | **GND** | Ground |

#### Firmware Installation
The complete PlatformIO firmware is included in [`firmware/esp32_pn5180/`](firmware/esp32_pn5180/):
1. Copy `config.example.h` to `config.h` (or generate it directly from the Web Dashboard's **Firmware & Flasher** tab).
2. Fill in your Wi-Fi and MQTT credentials.
3. Flash the ESP32 using PlatformIO:
   ```bash
   cd firmware/esp32_pn5180
   pio run -t upload
   ```

---

### 2. ⭐ M5Stack ATOM Lite + RFID 2 Unit (Plug & Play, No Soldering)

For standard NFC cards, stickers, and keyfobs (NTAG213/215/216, Mifare Classic):

- **No soldering needed:** Connect via the included Grove cable.
- **Integrated RGB Status LED:** Visual state feedback (Green = Ready, Blue = Connecting, Cyan = Play, Orange = Stop, Red = Error).
- **Integrated Push Button:** For status ping and reboot.
- **ESPHome Template:** Pre-configured in [`esphome/esphome_m5atom_lite_rfid.yaml`](esphome/esphome_m5atom_lite_rfid.yaml).

| Grove Wire | Signal | ATOM Lite GPIO |
| :--- | :--- | :--- |
| **Yellow** | I2C SDA | **GPIO 26** |
| **White** | I2C SCL | **GPIO 32** |
| **Red** | Power (5V) | **5V** |
| **Black** | Ground | **GND** |

---

### 3. ESP32 with PN532 or RC522

- **PN532 (I2C):** Uses GPIO 21 (SDA) and GPIO 22 (SCL). Config: [`esphome/esphome_pn532_i2c.yaml`](esphome/esphome_pn532_i2c.yaml).
- **RC522 (SPI):** Uses SCK (18), MOSI (23), MISO (19), CS (5), RST (22). Config: [`esphome/esphome_rc522_spi.yaml`](esphome/esphome_rc522_spi.yaml).

---

## 🚀 Quick Start with Docker

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
      - MQTT_USER=your_mqtt_user
      - MQTT_PASSWORD=your_mqtt_password
      - MQTT_TOPIC_SCANNED=rfid/scanned
      - MQTT_TOPIC_ACTION=rfid/action
      # Audiobookshelf Settings (Optional)
      - ABS_BASE_URL=http://192.168.1.50:13378
      - ABS_DEFAULT_TOKEN=your_audiobookshelf_token
      - MASS_ABS_INSTANCE_ID=xPQT49LN
      # UI Settings
      - UI_LANGUAGE=en # Options: "en" or "de"
      - LOG_LEVEL=INFO
```

### 2. Start the Service

```bash
docker compose up -d
```

### 3. Access the Dashboard

Open your browser at:  
👉 **`http://<server-ip>:5000`**

---

## ⚙️ Configuration & Environment Variables

Settings can be specified via environment variables or inside `/app/data/config.yaml` (see [`config/config.example.yaml`](config/config.example.yaml)).

| Variable | Description | Default |
| :--- | :--- | :--- |
| `MQTT_BROKER` | Hostname or IP of your MQTT Broker | `192.168.1.50` |
| `MQTT_PORT` | MQTT Port | `1883` |
| `MQTT_USER` | MQTT Username | `""` |
| `MQTT_PASSWORD` | MQTT Password | `""` |
| `MQTT_TOPIC_SCANNED` | Topic where readers publish scan events | `rfid/scanned` |
| `MQTT_TOPIC_ACTION` | Topic where Home Assistant listens | `rfid/action` |
| `ABS_BASE_URL` | Audiobookshelf server URL | `""` |
| `ABS_DEFAULT_TOKEN` | Audiobookshelf API token | `""` |
| `MASS_ABS_INSTANCE_ID` | Music Assistant ABS Provider ID prefix | `""` |
| `WARNING_SOUND_URI` | Media URI for unconfigured tags | `media-source://media_source/local/warningMissingNFC.wav` |
| `DEFAULT_VOLUME` | Default playback volume (0-100) | `20` |
| `UI_LANGUAGE` | Dashboard UI language (`en` or `de`) | `en` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) | `INFO` |

---

## 🏠 Home Assistant Automation Setup

The Docker container publishes all processed actions as structured JSON to `rfid/action`.

Create a single automation in Home Assistant (or import [`homeassistant/automations.yaml`](homeassistant/automations.yaml)):

```yaml
alias: "NFC Controller: MQTT Action Handler"
mode: queued
max: 10
trigger:
  - platform: mqtt
    topic: "rfid/action"
action:
  - variables:
      data: "{{ trigger.payload_json }}"
      status: "{{ data.status | default('') }}"
      action_type: "{{ data.action_type | default('') }}"
      media_type: "{{ data.media_type | default('track') }}"
      target_player: "{{ data.target_player | default('') }}"
      target_id: "{{ data.target_id | default('') }}"
      volume: "{{ data.volume | default(none) }}"
      random_flag: "{{ data.random | default(false) }}"
      start_from_beginning: "{{ data.start_from_beginning | default(false) }}"

  - choose:
      # 1. STOP ON TAG REMOVAL (Toniebox behavior)
      - conditions:
          - condition: template
            value_template: "{{ status == 'removed' or action_type == 'stop' }}"
          - condition: template
            value_template: "{{ target_player != '' }}"
        sequence:
          - action: media_player.media_stop
            target:
              entity_id: "{{ target_player }}"

      # 2. WARNING SOUND FOR UNCONFIGURED TAGS
      - conditions:
          - condition: template
            value_template: "{{ action_type == 'warning' }}"
        sequence:
          - action: media_player.play_media
            target:
              entity_id: "{{ target_player }}"
            data:
              media_content_id: "{{ target_id }}"
              media_content_type: music

      # 3. MEDIA PLAYBACK (Music Assistant)
      - conditions:
          - condition: template
            value_template: "{{ action_type == 'media' and target_player != '' and target_id != '' }}"
        sequence:
          # Set Volume if defined
          - if:
              - condition: template
                value_template: "{{ volume is not none and volume != '' }}"
            then:
              - action: media_player.volume_set
                target:
                  entity_id: "{{ target_player }}"
                data:
                  volume_level: "{{ (volume | float) / 100 }}"

          # Set Shuffle State
          - action: media_player.shuffle_set
            target:
              entity_id: "{{ target_player }}"
            data:
              shuffle: "{{ random_flag }}"

          # Trigger Playback via Music Assistant
          - action: music_assistant.play_media
            target:
              entity_id: "{{ target_player }}"
            data:
              media_id: "{{ target_id }}"
              media_type: "{{ media_type }}"
              enqueue: replace

      # 4. SCENE ACTIVATION
      - conditions:
          - condition: template
            value_template: "{{ action_type == 'scene' and target_id != '' }}"
        sequence:
          - action: scene.turn_on
            target:
              entity_id: "{{ target_id }}"
```

---

## 📚 Audiobookshelf, Series & Podcast Management

### Multi-Room User Tokens
Under **Readers & Zones** in the dashboard, assign a unique `abs_user_token` to each reader:
- Player A (Child 1) and Player B (Child 2) can listen to the same series.
- Child 1's progress advances independently without skipping chapters for Child 2.

### URI Formats Supported
- **Audiobookshelf Series:** `audiobookshelf--<instance>://audiobook/<resolved_book_id>`
- **Audiobookshelf Podcast Episode:** `audiobookshelf--<instance>://podcast_episode/<resolved_episode_id>`
- **Music Assistant Native Podcast:** `library://podcast/<id>` with `extra_params: {"start_item": "latest"}`
- **Music Assistant Albums/Playlists:** `library://album/<id>`, `library://playlist/<id>`

---

## 💻 Web Dashboard & Firmware Flasher

Access the dashboard at `http://<ip>:5000`:
- **NFC Tags:** View, search, edit, and assign actions, volumes, and playback options.
- **Readers & Zones:** Assign readers to specific Home Assistant media players and Audiobookshelf user tokens.
- **Live History:** Live WebSocket stream showing tag placements, removals, and executed actions.
- **Test Simulator & ABS:** Test tag scanning virtually and browse Audiobookshelf libraries.
- **Firmware & Flasher:** Select your hardware profile, enter your Wi-Fi credentials, and download a pre-configured `config.h` or ESPHome YAML file.

---

## 📡 REST API & WebSocket Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET`, `POST` | `/api/tags` | List all tags or add/update tags |
| `GET`, `DELETE` | `/api/tags/{tag_id}` | Retrieve or delete a specific tag |
| `GET`, `POST` | `/api/readers` | List or register hardware readers |
| `GET` | `/api/firmware/templates` | Retrieve hardware profiles and pinout guides |
| `GET` | `/api/firmware/generate-yaml` | Generate tailored `config.h` or ESPHome YAML |
| `GET` | `/api/abs/series` | Search and list series from Audiobookshelf |
| `GET` | `/api/abs/podcasts` | Search and list podcasts from Audiobookshelf |
| `POST` | `/api/test/scan` | Simulate a scan or remove event via API |
| `GET` | `/api/system/status` | Real-time health status of MQTT, ABS, and SQLite |
| `GET` | `/api/system/logs` | In-memory container log viewer |
| `WebSocket` | `/ws` | Real-time event feed |

---

## 🛠️ Local Development & Testing

```bash
# Clone the repository
git clone https://github.com/Kl4V3/nfc-ha-media-controller.git
cd nfc-ha-media-controller

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the automated test suite (35 tests)
pytest -v

# Run local test container
docker compose up -d --build
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
