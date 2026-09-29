# M5Stack ATOM Lite + RFID Unit Custom Firmware

Dedicated PlatformIO (C++/Arduino) firmware for the M5Stack ATOM Lite coupled with the M5Stack RFID / RFID 2 Unit (WS1850S / MFRC522 via Grove I2C).

---

## Capabilities & Architecture

- **Robust Debouncing (Zero Jitter / Glitch Resistance):** Continuous polling with `MAX_MISSING_CYCLES` (Default: 3 cycles of 200ms = 600ms debounce window) prevents accidental playback stoppage during transient RF dropouts.
- **WUPA & REQA Support:** Reliably detects both newly presented tags (IDLE) and tags already resting on the antenna (HALT).
- **Integrated Web Diagnostics (Port 80):**
  - Real-time color-coded event log console (Play, Stop, MQTT, Hardware events).
  - Wi-Fi signal strength (RSSI in dBm), IP address, uptime, and free heap metrics.
  - Active tag ID and detected IC type display.
  - Controls to clear the log buffer and trigger a remote ESP32 reboot.
- **RGB Status LED Feedback (GPIO 27):**
  - Blue: Connecting to Wi-Fi.
  - Orange: Wi-Fi connected, negotiating MQTT connection.
  - Dim Green: Connected and idle (Normal ready state).
  - Bright Cyan (350ms): Tag detected -> Play command published.
  - Bright Orange (350ms): Tag removed -> Stop command published.
  - Red: Connectivity error (Wi-Fi dropped).
- **Hardware Button (GPIO 39):**
  - Short press (< 1s): Transmits MQTT status heartbeat ping (`rfid/status` alive) with yellow LED flash.
  - Long press (> 3s): Reboots the ESP32 microcontroller with red LED flash.
- **Periodic Heartbeat:** Automatically sends an MQTT status heartbeat every 60 seconds.

---

## Hardware Pinout & Wiring

Connect the RFID 2 Unit to the ATOM Lite using the official M5Stack Grove cable:

| Signal | ATOM Lite GPIO | Grove Cable Color | Function |
| :--- | :--- | :--- | :--- |
| **SDA** | **GPIO 26** | Yellow | I2C Data Line |
| **SCL** | **GPIO 32** | White | I2C Clock Line |
| **5V** | **5V** | Red | Power Supply |
| **GND** | **GND** | Black | Ground |

Internal ATOM Lite hardware:
- **RGB Status LED:** GPIO 27 (SK6812 / WS2812)
- **Front Button:** GPIO 39 (Active LOW)

---

## Setup & Flashing

### 1. Configure Credentials (`config.h`)

Copy the configuration template:
```bash
cd firmware/m5atom_lite_rfid/include
cp config.example.h config.h
```

Update your network and broker settings in `config.h`:
```cpp
const char* WIFI_SSID       = "Your_WiFi_SSID";
const char* WIFI_PASSWORD   = "Your_WiFi_Password";
const char* MQTT_BROKER     = "192.168.1.50";
const int   MQTT_PORT       = 1883;
const char* MQTT_USER       = "your_mqtt_user";
const char* MQTT_PASSWORD   = "your_mqtt_password";
const char* READER_ID       = "Living_Room_NFC_Reader";
```

### 2. Flash with PlatformIO

Connect the ATOM Lite via USB-C to your development computer:

```bash
cd firmware/m5atom_lite_rfid
pio run -t upload
```

To open the serial console:
```bash
pio device monitor -b 115200
```

---

## MQTT Specification

- **Tag Detected (Play):**
  - Topic: `rfid/scanned`
  - Payload: `{"tag_id": "04a1b2c3d4e5f6", "reader_id": "Living_Room_NFC_Reader", "status": "scanned"}`
- **Tag Removed (Stop):**
  - Topic: `rfid/scanned`
  - Payload: `{"tag_id": "04a1b2c3d4e5f6", "reader_id": "Living_Room_NFC_Reader", "status": "removed"}`
- **Status Heartbeat:**
  - Topic: `rfid/status`
  - Payload: `{"reader_id": "Living_Room_NFC_Reader", "status": "alive"}`
