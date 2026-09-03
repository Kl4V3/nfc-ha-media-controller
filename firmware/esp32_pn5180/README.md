# ESP32 + PN5180 Firmware (Toniebox & ISO-15693 NFC Reader)

This directory contains the dedicated **PlatformIO (Arduino)** firmware for the **ESP32 + NXP PN5180** NFC reader setup.

---

## 🌟 Why the PN5180?

Standard NFC chips (like the RC522 or PN532) are limited to ISO-14443 tags (Mifare Classic, NTAG213/215/216) and cannot properly interact with Toniebox figures.

**Toniebox figures** utilize **NXP ICODE SLIX2 (ISO-15693)** RFID transponders that operate in **Privacy Mode**. In this mode, the chip ignores standard inventory scans until an authenticated password handshake is executed.

The **PN5180** features full hardware support for ISO-15693 protocol commands and custom SPI frames, enabling:
- **Toniebox Figure Support:** Automatic password handshake bypass (`0x5B 0x6E 0xFD 0x7F`).
- **ISO-15693 & ISO-14443 Support:** Reads Tonie figures, SLIX/SLIX2 chips, and standard NFC cards/stickers.
- **Continuous Polling (No LPCD):** Instant scan response without sleep latency.
- **Toniebox Presence Detection:** Placing a tag publishes `scanned` (Play), removing it publishes `removed` (instant Stop).
- **Built-in Web Diagnostics:** Built-in web server on port 80 showing Wi-Fi RSSI, connection status, and real-time serial logs.

---

## 🔌 Hardware & Pinout

Connect the **PN5180** module to the **ESP32** (NodeMCU / WROOM-32) using SPI:

| PN5180 Pin | ESP32 GPIO | Description |
| :--- | :--- | :--- |
| **MOSI** | **GPIO 23** | SPI Master Out Slave In |
| **MISO** | **GPIO 19** | SPI Master In Slave Out |
| **SCK** | **GPIO 18** | SPI Clock |
| **NSS / CS** | **GPIO 5** | SPI Chip Select |
| **BUSY** | **GPIO 21** | PN5180 Busy Flag |
| **RST** | **GPIO 22** | PN5180 Reset |
| **3.3V / 5V** | **3.3V / 5V** | Power Supply (Ensure stable 3.3V/5V) |
| **GND** | **GND** | Ground |

---

## 🚀 Quick Setup & Flashing

### 1. Copy and Configure `config.h`

```bash
cd firmware/esp32_pn5180/include
cp config.example.h config.h
```

Edit `config.h` with your Wi-Fi credentials, MQTT Broker IP, and Reader ID:

```cpp
const char* WIFI_SSID       = "Your_WiFi_SSID";
const char* WIFI_PASSWORD   = "Your_WiFi_Password";
const char* MQTT_BROKER     = "192.168.1.50";
const int   MQTT_PORT       = 1883;
const char* MQTT_USER       = "your_mqtt_user";
const char* MQTT_PASSWORD   = "your_mqtt_password";
const char* READER_ID       = "reader_kidsroom";
```

> **Note:** `config.h` is excluded in `.gitignore` so your personal credentials will never be committed.

### 2. Build and Upload with PlatformIO

Connect the ESP32 via USB and run:

```bash
cd firmware/esp32_pn5180
pio run -t upload
```

To monitor serial output:

```bash
pio device monitor -b 115200
```

---

## 📡 MQTT Contract

The firmware communicates directly with the Docker `nfc-ha-media-controller` middleware:

- **Tag Placed:**
  ```json
  // Topic: rfid/scanned
  {"status": "scanned", "reader_id": "reader_kidsroom", "tag_id": "e00403501b7f2493"}
  ```
- **Tag Removed:**
  ```json
  // Topic: rfid/scanned
  {"status": "removed", "reader_id": "reader_kidsroom"}
  ```
