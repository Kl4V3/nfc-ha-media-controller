# NFC Media Controller

[![Docker Image](https://img.shields.io/docker/v/theklave/nfc-ha-media-controller?label=Docker%20Hub&logo=docker)](https://hub.docker.com/r/theklave/nfc-ha-media-controller)
[![Release](https://img.shields.io/badge/version-0.3.6-brightgreen.svg)](https://github.com/Kl4V3/nfc-ha-media-controller/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?logo=python)](https://www.python.org/)

NFC Media Controller is a containerized, event-driven middleware designed to bridge physical NFC/RFID tag presence with distributed media playback and home automation systems. It functions as a centralized integration layer connecting network-attached microcontrollers (ESP32, ESP8266, M5Stack) with execution platforms, primarily Home Assistant, Music Assistant, and Audiobookshelf.

The system enforces deterministic physical presence playback: placing an assigned tag on a reader triggers target media or scene execution, while removing the tag immediately halts playback.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Core Capabilities](#core-capabilities)
- [Supported Media Types & Routing](#supported-media-types--routing)
- [Hardware Configurations & Firmware](#hardware-configurations--firmware)
  - [M5Stack ATOM Lite + RFID 2 Unit (Native C++ / ESPHome)](#1-m5stack-atom-lite--rfid-2-unit-recommended)
  - [ESP32 + NXP PN5180 (ISO-15693 / SLIX2 Toniebox Figures)](#2-esp32--nxp-pn5180-iso-15693--slix2)
  - [Standard ESP32 Setups (PN532 / RC522)](#3-standard-esp32-setups-pn532--rc522)
- [Deployment](#deployment)
  - [Docker Compose](#docker-compose)
  - [Environment Variables](#environment-variables)
- [Downstream Automation Integration (Home Assistant)](#downstream-automation-integration-home-assistant)
  - [Option A: Dedicated Home Assistant Script](#option-a-dedicated-home-assistant-script)
  - [Option B: Direct Automation / Blueprint](#option-b-direct-automation--blueprint)
- [Audiobookshelf Integration & Multi-Room Routing](#audiobookshelf-integration--multi-room-routing)
- [Web Dashboard & Management Interface](#web-dashboard--management-interface)
- [REST API & WebSocket Reference](#rest-api--websocket-reference)
- [Local Development & Verification](#local-development--verification)
- [License](#license)

---

## System Architecture

```text
+------------------------------------------------------------------------+
|                          1. Hardware Readers                           |
|  ESP32 / M5Stack running Native PlatformIO firmware or ESPHome         |
|    - Tag Placed   -> MQTT "rfid/scanned"  {"status": "scanned", ...}   |
|    - Tag Removed  -> MQTT "rfid/scanned"  {"status": "removed", ...}   |
+-----------------------------------┬------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                        2. Middleware Container                         |
|  FastAPI + Paho-MQTT + SQLite + Audiobookshelf Client Engine           |
|    - Tag ID Sanitization (Uniform hex lowercase, stripped separators)  |
|    - Lazy Evaluation & Debounce Protection (< 3s sync buffer)          |
|    - Audiobookshelf Series Auto-Advance (95% completion threshold)     |
|    - Podcast Episode Resolution (Newest unplayed episode priority)     |
|    - Multi-User Token Routing (Room-isolated listening positions)      |
|    - Web Management Dashboard (Port 5000) & Precompiled Firmwares      |
|    - Dispatches Normalized Action Payload -> MQTT "rfid/action"        |
+-----------------------------------┬------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                    3. Execution (Home Assistant)                       |
|  Automation or Script Handler                                          |
|    - status == "removed" -> media_player.media_stop                    |
|    - action == "warning" -> Plays configured missing-tag sound         |
|    - action == "media"   -> music_assistant.play_media                 |
|    - action == "scene"   -> scene.turn_on                              |
+------------------------------------------------------------------------+
```

---

## Core Capabilities

- **Deterministic Physical Presence Playback:**
  - **Tag Placed (`scanned`):** Resolves assigned media and dispatches playback commands to the target player.
  - **Tag Removed (`removed`):** Immediately issues a stop action (`media_player.media_stop`) with playlist clearing.
- **Lazy Evaluation & Debounce State Protection:**
  - Tag removal events immediately trigger playback stoppage without initiating heavy upstream API queries.
  - Scan events occurring within 3 seconds of a removal event automatically trigger an asynchronous debounce delay to allow downstream players and Audiobookshelf sync sessions to settle cleanly.
- **Dynamic Series Progression (Audiobookshelf):**
  - Evaluates series completion states based on a 95% completion threshold (`progress >= 0.95` or `isFinished == true`).
  - Automatically identifies and queues the next unfinished book in sequence.
  - Active server synchronization: Automatically invokes Audiobookshelf's `mark_as_finished` endpoint for completed books to prevent stale resume positions.
  - Seamless loopback: Automatically resets to Book 1 once all titles in a series are complete.
- **Reverse-Chronological Podcast Resolution:**
  - Automatically queries the podcast feed in Audiobookshelf and resolves the newest unplayed episode.
  - Targets the exact episode URI using Music Assistant's composite item identifier schema (`audiobookshelf--<instance>://podcast_episode/<podcast_id> <episode_id>`).
- **Multi-User Progress Isolation:**
  - Assign individual Audiobookshelf authentication tokens per reader/zone. Multiple users in different rooms can track individual progress across the same book or series without state collision.
- **Hardware Agnostic & Pre-Compiled Firmware:**
  - Built-in support for NXP PN5180 (ISO-15693 SLIX2 Privacy Mode password handshake for Tonie figures), M5Stack ATOM Lite + RFID 2 Unit (WS2812 status LED, web diagnostics on port 80), PN532, and RC522.
  - Web UI includes configuration generation and direct pre-compiled binary downloads.
- **Tag ID Normalization & Database Health:**
  - Ingested tag IDs are automatically sanitized into uniform lowercase hex strings without spaces, dashes, or colons.
  - Automatic database schema migration cleans existing records on startup.
  - Dedicated bulk cleanup endpoint for purging unconfigured auto-discovered tags.

---

## Supported Media Types & Routing

| Action Type | Target Configuration | Resolved Payload `target_id` | Downstream Handler |
| :--- | :--- | :--- | :--- |
| **Audiobook / Book** | Audiobookshelf Item ID | `audiobookshelf--<instance>://audiobook/<item_id>` | Music Assistant (`play_media`) |
| **Series** | Audiobookshelf Series ID | `audiobookshelf--<instance>://audiobook/<next_book_id>` | Music Assistant (`play_media`) |
| **Podcast** | Audiobookshelf Podcast ID | `audiobookshelf--<instance>://podcast_episode/<podcast_id> <episode_id>` | Music Assistant (`play_media`) |
| **Native Podcast** | `library://podcast/<id>` | `library://podcast/<id>` with `extra_params: {"start_item": "latest"}` | Music Assistant (`play_media`) |
| **Album** | Music Assistant URI | `library://album/<id>` or `mass://album/<id>` | Music Assistant (`play_media`) |
| **Playlist** | Music Assistant URI | `library://playlist/<id>` or `mass://playlist/<id>` | Music Assistant (`play_media`) |
| **Scene** | Home Assistant Scene Entity | `scene.<name>` | Home Assistant (`scene.turn_on`) |
| **Warning** | Missing/Unconfigured Tag | `media-source://media_source/local/warningMissingNFC.wav` | Media Player (`play_media`) |

---

## Hardware Configurations & Firmware

### 1. M5Stack ATOM Lite + RFID 2 Unit (Recommended)

A compact, solderless reader solution based on the ESP32 and NXP WS1850S (I2C).

- **Hardware:** M5Stack ATOM Lite coupled with the RFID 2 Unit via Grove connector.
- **Visual Feedback:** Integrated WS2812 RGB LED (Green = Ready, Blue = Connecting, Cyan = Tag Active, Orange = Tag Removed, Red = Error).
- **Diagnostics:** Built-in web dashboard accessible on port 80 of the reader displaying device uptime, Wi-Fi RSSI, MQTT status, and live tag scans.
- **Source & Configuration:** Located in `firmware/m5atom_lite_rfid/`.
- **Wiring (Grove Cable):**
  - Yellow: I2C SDA (GPIO 26)
  - White: I2C SCL (GPIO 32)
  - Red: 5V Power
  - Black: Ground

An alternative ESPHome configuration is provided in `esphome/esphome_m5atom_lite_rfid.yaml`.

---

### 2. ESP32 + NXP PN5180 (ISO-15693 / SLIX2)

Required for reading high-frequency ISO-15693 transponders, including original Toniebox figures protected by privacy mode passwords.

- **Operating Principle:** Transmits the SLIX2 privacy password unlock handshake (`0x5B 0x6E 0xFD 0x7F`) over SPI to expose transponder memory.
- **Source:** PlatformIO project located in `firmware/esp32_pn5180/`.

#### SPI Pin Mapping

| PN5180 Pin | ESP32 GPIO | Function |
| :--- | :--- | :--- |
| **MOSI** | **GPIO 23** | SPI Master Out Slave In |
| **MISO** | **GPIO 19** | SPI Master In Slave Out |
| **SCK** | **GPIO 18** | SPI Clock |
| **NSS / CS** | **GPIO 5** | SPI Chip Select |
| **BUSY** | **GPIO 21** | Hardware Busy Signal |
| **RST** | **GPIO 22** | Hardware Reset |
| **3.3V / 5V** | **3.3V / 5V** | Regulated Supply Voltage |
| **GND** | **GND** | Common Ground |

---

### 3. Standard ESP32 Setups (PN532 / RC522)

For standard ISO-14443 Type A tags (NTAG213, NTAG215, NTAG216, Mifare Classic):

- **PN532 (I2C):** GPIO 21 (SDA), GPIO 22 (SCL). Config: `esphome/esphome_pn532_i2c.yaml`.
- **RC522 (SPI):** SCK (GPIO 18), MOSI (GPIO 23), MISO (GPIO 19), CS (GPIO 5), RST (GPIO 22). Config: `esphome/esphome_rc522_spi.yaml`.

---

## Deployment

### Docker Compose

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
      # MQTT Broker Connectivity
      - MQTT_BROKER=192.168.1.50
      - MQTT_PORT=1883
      - MQTT_USER=your_mqtt_user
      - MQTT_PASSWORD=your_mqtt_password
      - MQTT_TOPIC_SCANNED=rfid/scanned
      - MQTT_TOPIC_ACTION=rfid/action
      # Audiobookshelf Server Connectivity
      - ABS_BASE_URL=http://192.168.1.50:13378
      - ABS_DEFAULT_TOKEN=your_api_token
      - MASS_ABS_INSTANCE_ID=xPQT49LN
      # System Configuration
      - UI_LANGUAGE=en # Options: "en" or "de"
      - LOG_LEVEL=INFO
```

### Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `MQTT_BROKER` | Hostname or IP of the MQTT broker | `192.168.1.50` |
| `MQTT_PORT` | MQTT broker port | `1883` |
| `MQTT_USER` | MQTT authentication username | `""` |
| `MQTT_PASSWORD` | MQTT authentication password | `""` |
| `MQTT_TOPIC_SCANNED` | Inbound MQTT topic for reader scan events | `rfid/scanned` |
| `MQTT_TOPIC_ACTION` | Outbound MQTT topic for normalized controller actions | `rfid/action` |
| `ABS_BASE_URL` | Base URL of the Audiobookshelf instance | `""` |
| `ABS_DEFAULT_TOKEN` | Global Audiobookshelf API token | `""` |
| `MASS_ABS_INSTANCE_ID` | Music Assistant Audiobookshelf provider instance prefix | `""` |
| `WARNING_SOUND_URI` | Audio URI triggered when scanning unconfigured tags | `media-source://media_source/local/warningMissingNFC.wav` |
| `DEFAULT_VOLUME` | Fallback volume level (0-100) | `20` |
| `UI_LANGUAGE` | Management interface localization (`en` or `de`) | `en` |
| `LOG_LEVEL` | Application logging verbosity (`DEBUG`, `INFO`, `WARNING`) | `INFO` |

---

## Downstream Automation Integration (Home Assistant)

The controller middleware publishes normalized action payloads to `rfid/action`. You can execute these commands in Home Assistant using either a parameterized script or a standalone automation.

### Option A: Dedicated Home Assistant Script

Create a script named `NFC Media Action` (`script.nfc_media_action`) in Home Assistant:

```yaml
alias: NFC Media Action
mode: parallel
fields:
  payload:
    description: JSON action payload dispatched by NFC Media Controller
sequence:
  - variables:
      action: "{{ payload.action_type }}"
      player: "{{ payload.target_player }}"
      target: "{{ payload.target_id }}"
      vol: "{{ payload.volume }}"
      is_random: "{{ payload.random | default(false) }}"
      m_type: "{{ payload.media_type | default('track') }}"
  - choose:
      # 1. Stop playback on tag removal
      - conditions:
          - condition: template
            value_template: "{{ action == 'stop' }}"
        sequence:
          - action: media_player.media_stop
            target:
              entity_id: "{{ player }}"
          - delay: "00:00:01"
          - action: media_player.clear_playlist
            target:
              entity_id: "{{ player }}"

      # 2. Trigger smart home scene
      - conditions:
          - condition: template
            value_template: "{{ action == 'scene' }}"
        sequence:
          - action: scene.turn_on
            target:
              entity_id: "{{ target }}"

      # 3. Play warning sound for unconfigured tags
      - conditions:
          - condition: template
            value_template: "{{ action == 'warning' }}"
        sequence:
          - action: media_player.play_media
            target:
              entity_id: "{{ player }}"
            data:
              media_content_id: "{{ target }}"
              media_content_type: music

      # 4. Stream media via Music Assistant
      - conditions:
          - condition: template
            value_template: "{{ action == 'media' or action == 'play' }}"
        sequence:
          - choose:
              - conditions:
                  - condition: template
                    value_template: "{{ vol is not none and vol != '' }}"
                sequence:
                  - action: media_player.volume_set
                    target:
                      entity_id: "{{ player }}"
                    data:
                      volume_level: "{{ (vol | float) / 100 }}"
          - action: media_player.shuffle_set
            target:
              entity_id: "{{ player }}"
            data:
              shuffle: "{{ is_random }}"
          - action: music_assistant.play_media
            target:
              entity_id: "{{ player }}"
            data:
              media_id: "{{ target }}"
              media_type: "{{ m_type }}"
              enqueue: replace
```

Connect MQTT to the script with a lightweight trigger automation:

```yaml
alias: "NFC Controller: Trigger Bridge"
mode: queued
max: 10
trigger:
  - platform: mqtt
    topic: "rfid/action"
action:
  - action: script.nfc_media_action
    data:
      payload: "{{ trigger.payload_json }}"
```

---

### Option B: Direct Automation / Blueprint

For an all-in-one automation without a separate script, import `homeassistant/blueprint_nfc_media.yaml` or use `homeassistant/automations.yaml`:

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

  - choose:
      - conditions:
          - condition: template
            value_template: "{{ status == 'removed' or action_type == 'stop' }}"
          - condition: template
            value_template: "{{ target_player != '' }}"
        sequence:
          - action: media_player.media_stop
            target:
              entity_id: "{{ target_player }}"

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

      - conditions:
          - condition: template
            value_template: "{{ action_type == 'media' and target_player != '' and target_id != '' }}"
        sequence:
          - if:
              - condition: template
                value_template: "{{ volume is not none and volume != '' }}"
            then:
              - action: media_player.volume_set
                target:
                  entity_id: "{{ target_player }}"
                data:
                  volume_level: "{{ (volume | float) / 100 }}"
          - action: media_player.shuffle_set
            target:
              entity_id: "{{ target_player }}"
            data:
              shuffle: "{{ random_flag }}"
          - action: music_assistant.play_media
            target:
              entity_id: "{{ target_player }}"
            data:
              media_id: "{{ target_id }}"
              media_type: "{{ media_type }}"
              enqueue: replace

      - conditions:
          - condition: template
            value_template: "{{ action_type == 'scene' and target_id != '' }}"
        sequence:
          - action: scene.turn_on
            target:
              entity_id: "{{ target_id }}"
```

---

## Audiobookshelf Integration & Multi-Room Routing

### Multi-Room Isolation

In the **Readers & Zones** tab of the web dashboard, assign a distinct Audiobookshelf user token (`abs_user_token`) to each physical reader:

- Multiple readers can trigger the same book or series tag simultaneously without progress interference.
- Progress updates are committed to the designated user profile in Audiobookshelf.

### URI Structure Details

- **Single Audiobooks:** `audiobookshelf--<instance>://audiobook/<item_id>`
- **Series (Auto-Advanced):** `audiobookshelf--<instance>://audiobook/<resolved_book_id>`
- **Podcasts (Episode Resolution):** `audiobookshelf--<instance>://podcast_episode/<podcast_id> <episode_id>`
  - Music Assistant's provider unpacks the composite identifier to look up the episode within the specified podcast feed.
- **Native Music Assistant Podcasts:** `library://podcast/<id>` with `extra_params: {"start_item": "latest"}`

---

## Web Dashboard & Management Interface

The built-in web management interface is available on port 5000 (`http://<host-ip>:5000`):

- **Tag Management:** Provision aliases, bind media IDs, configure default playback volume, toggle shuffle, and enable the "Always start from beginning" flag.
- **Bulk Maintenance:** Delete unconfigured auto-discovered tags in a single operation.
- **Reader Assignment:** Bind hardware reader IDs to Home Assistant entity IDs (`media_player.*`) and dedicated Audiobookshelf tokens.
- **Audiobookshelf Explorer:** Integrated browser and search tool for direct binding of books, series, and podcasts without manual ID copying.
- **Firmware Builder & Flasher:** Web-based generator for custom `config.h` headers and ESPHome YAML configurations, including direct downloads of pre-compiled binaries.
- **Real-Time Diagnostics:** WebSocket-powered event feed displaying raw scan events, routing calculations, and dispatched MQTT actions.

---

## REST API & WebSocket Reference

### Tag Management

- `GET /api/tags`: List all registered tags.
- `POST /api/tags`: Create or update a tag mapping.
- `GET /api/tags/{tag_id}`: Retrieve a specific tag by ID.
- `DELETE /api/tags/{tag_id}`: Delete an individual tag.
- `DELETE /api/tags/unconfigured`: Bulk delete all auto-discovered unconfigured tags.

### Reader Management

- `GET /api/readers`: List all configured readers and zone assignments.
- `POST /api/readers`: Create or update a reader configuration.
- `DELETE /api/readers/{reader_id}`: Remove a reader.

### Audiobookshelf Endpoints

- `GET /api/abs/status`: Check connection state and user profile validity.
- `GET /api/abs/libraries`: List accessible libraries.
- `GET /api/abs/series`: Query series list with optional search filter.
- `GET /api/abs/podcasts`: Query podcast feeds.

### Firmware & Profiles

- `GET /api/firmware/templates`: Retrieve hardware pinout profiles and specifications.
- `GET /api/firmware/generate-yaml`: Generate customized `config.h` or ESPHome YAML.
- `GET /api/firmware/download-bin/{hardware_type}`: Download pre-compiled `.bin` firmware.
- `GET /api/firmware/manifest/{hardware_type}`: ESP Web Tools manifest for browser-based USB flashing.

### Diagnostics & Monitoring

- `POST /api/test/scan`: Simulate an RFID scan or removal event via JSON payload.
- `GET /api/history`: Retrieve recent scan and action logs.
- `GET /api/system/status`: Connectivity status for MQTT, Audiobookshelf, and database.
- `GET /api/system/logs`: In-memory log stream.
- `WebSocket /ws`: Full-duplex real-time event distribution stream.

---

## Local Development & Verification

Execute the automated test suite using Docker:

```bash
# Clone the repository
git clone https://github.com/Kl4V3/nfc-ha-media-controller.git
cd nfc-ha-media-controller

# Run the complete test suite (48 automated test cases)
docker run --rm -v $(pwd):/app -w /app nfc-test-nfc-media-controller pytest -v

# Start the local development container
docker compose up -d --build
```

---

## License

This project is licensed under the [MIT License](LICENSE).
