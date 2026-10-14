# ESP32-C3 Super Mini + PN5180 Firmware (Toniebox & ISO-15693 NFC Reader)

Dieses Verzeichnis enthält die dedizierte **PlatformIO (Arduino)** Firmware für die ultrakompakte **ESP32-C3 Super Mini + NXP PN5180** NFC Reader Kombination.

---

## 🌟 Warum PN5180 auf ESP32-C3 Super Mini?

- **Ultrakompakte Bauform:** Der ESP32-C3 Super Mini ist winzig und eignet sich ideal für den Einbau in kleine Gehäuse, Toniebox-Umbauten oder Regalböden.
- **Nativer USB-CDC Support:** Direkte serielle Ausgabe und Flashen über die integrierte USB-C Schnittstelle des RISC-V SoC.
- **Toniebox-Figuren-Unterstützung:** Automatischer Privacy-Passwort-Handshake (`0x5B 0x6E 0xFD 0x7F`) für NXP ICODE SLIX2 (ISO-15693).
- **ISO-14443A Tag-Unterstützung:** Vollständige Unterstützung für NTAG213, NTAG215, NTAG216, MIFARE Ultralight und MIFARE Classic.
- **Multi-Protocol Multiplexing:** Sticky-Protocol-Caching während der Wiedergabe für blitzschnelle Latenzen (< 2 ms) und schnelles Fallback-Scanning im Standby.
- **Continuous Polling:** Schnelle Präsenzerkennung ohne Sleep-Latenz (Auflegen = Play, Wegnehmen = sofort Stop).
- **Web-Diagnose & Live-Logs:** Integrierter Webserver auf Port 80 zur Anzeige von Wi-Fi Signalstärke (RSSI), Verbindungsstatus, Tag-UID, Chip-Typ und Live-Logausgabe.

---

## 🔌 Hardware & Pinout

Verdrahtung des **PN5180** Moduls mit dem **ESP32-C3 Super Mini**:

| PN5180 Pin | Signal | ESP32-C3 Super Mini GPIO | Beschreibung |
| :--- | :--- | :--- | :--- |
| **MOSI** | SPI MOSI | **GPIO 6** | SPI Master Out Slave In |
| **MISO** | SPI MISO | **GPIO 5** | SPI Master In Slave Out |
| **SCK** | SPI Clock | **GPIO 4** | SPI Clock |
| **NSS / CS** | Chip Select | **GPIO 7** | SPI Chip Select |
| **BUSY** | Busy Flag | **GPIO 0** | PN5180 Busy Status Flag |
| **RST** | Reset | **GPIO 1** | PN5180 Hardware Reset |
| **3.3V / 5V** | Power Supply | **5V & 3V3** | Stabile Spannungsversorgung |
| **GND** | Ground | **GND** | Gemeinsame Masse |

---

## 🚀 Setup & Flashen

### 1. `config.h` erstellen

```bash
cd firmware/esp32_c3_pn5180/include
cp config.example.h config.h
```

Passe `config.h` mit deinen WLAN-Zugangsdaten, deiner MQTT-Broker IP und deiner gewünschten Reader-ID an:

```cpp
const char* WIFI_SSID       = "Dein_WLAN_Name";
const char* WIFI_PASSWORD   = "Dein_WLAN_Passwort";
const char* MQTT_BROKER     = "192.168.1.50";
const int   MQTT_PORT       = 1883;
const char* MQTT_USER       = "dein_mqtt_user";
const char* MQTT_PASSWORD   = "dein_mqtt_passwort";
const char* READER_ID       = "reader_c3_supermini";
```

> **Hinweis:** `config.h` ist in `.gitignore` eingetragen und wird nicht ins Git-Repository übertragen.

### 2. Bauen und Flashen mit PlatformIO

Schließe den ESP32-C3 Super Mini per USB-C an den PC an:

```bash
cd firmware/esp32_c3_pn5180
pio run -t upload
```

Seriellen Monitor starten:

```bash
pio device monitor -b 115200
```

---

## 📡 MQTT Schnittstelle

Die Firmware sendet Events direkt an die `nfc-ha-media-controller` Middleware:

- **Tag aufgelegt:**
  ```json
  // Topic: rfid/scanned
  {"status": "scanned", "reader_id": "reader_c3_supermini", "tag_id": "e00403501b7f2493"}
  ```
- **Tag entfernt:**
  ```json
  // Topic: rfid/scanned
  {"status": "removed", "reader_id": "reader_c3_supermini"}
  ```
