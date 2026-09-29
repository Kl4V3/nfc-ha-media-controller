#ifndef CONFIG_H
#define CONFIG_H

#include <Arduino.h>

// ============================================================================
// WI-FI CONFIGURATION
// ============================================================================
const char* WIFI_SSID       = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD   = "YOUR_WIFI_PASSWORD";

// ============================================================================
// MQTT BROKER CONFIGURATION
// ============================================================================
const char* MQTT_BROKER     = "192.168.1.50";
const int   MQTT_PORT       = 1883;
const char* MQTT_USER       = "your_mqtt_user";
const char* MQTT_PASSWORD   = "your_mqtt_password";

// MQTT Topics
const char* MQTT_TOPIC_SCANNED = "rfid/scanned";
const char* MQTT_TOPIC_STATUS  = "rfid/status";

// ============================================================================
// READER IDENTIFICATION
// ============================================================================
const char* READER_ID          = "Wohnzimmer_NFC_Reader";

// ============================================================================
// POLLING & DEBOUNCE SETTINGS
// ============================================================================
// SCAN_INTERVAL_MS: Zeit zwischen zwei Lesezyklen
const unsigned long SCAN_INTERVAL_MS = 200;

// MAX_MISSING_CYCLES: Anzahl aufeinanderfolgender Fehlversuche, bevor ein Tag
// als entfernt (removed) gemeldet wird.
// 3 Zyklen * 200ms = 600ms stabiles Debounce-Fenster gegen kurze Aussetzer.
const int MAX_MISSING_CYCLES = 3;

// ============================================================================
// HARDWARE PIN ASSIGNMENTS (M5Stack ATOM Lite + Grove RFID)
// ============================================================================
#ifndef GROVE_SDA
#define GROVE_SDA 26
#endif

#ifndef GROVE_SCL
#define GROVE_SCL 32
#endif

#ifndef ATOM_LED_PIN
#define ATOM_LED_PIN 27
#endif

#ifndef ATOM_BTN_PIN
#define ATOM_BTN_PIN 39
#endif

// I2C-Adresse der M5Stack RFID / RFID 2 Unit (WS1850S / RC522)
const uint8_t MFRC522_I2C_ADDR = 0x28;

#endif // CONFIG_H
