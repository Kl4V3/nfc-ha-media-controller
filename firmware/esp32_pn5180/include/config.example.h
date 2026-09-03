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

// MQTT Topic for nfc-ha-media-controller
const char* MQTT_TOPIC_SCANNED = "rfid/scanned";

// ============================================================================
// READER IDENTIFICATION
// ============================================================================
const char* READER_ID          = "reader_kidsroom";

// ============================================================================
// POLLING & DEBOUNCE SETTINGS
// ============================================================================
const unsigned long SCAN_INTERVAL_MS = 200;
const int MAX_MISSING_CYCLES = 2; // 2 * 200ms = 400ms debounce time

// ============================================================================
// TONIEBOX & TEDDYCLOUD PRIVACY PASSWORDS & COMMANDS
// ============================================================================
struct PrivacyKeyEntry {
  const char* label;
  uint8_t cmdCode;  // 0xB3 (Set Password) or 0xBA (Privacy Command)
  int8_t  pwdId;    // 0x04 (SLIX2), 0x03 (SLIX-L), or -1 (no password ID)
  uint8_t key[4];
};

const PrivacyKeyEntry KNOWN_PRIVACY_KEYS[] = {
  { "Toniebox Original (Boxine)",    0xB3,  0x04, { 0x5B, 0x6E, 0xFD, 0x7F } },
  { "Toniebox Original (BE)",        0xB3,  0x04, { 0x7F, 0xFD, 0x6E, 0x5B } },
  { "Tonie SLIX-L (0xBA Privacy)",   0xBA, -0x01, { 0x5B, 0x6E, 0xFD, 0x7F } },
  { "Tonie SLIX-L (0xB3 ID 0x03)",   0xB3,  0x03, { 0x5B, 0x6E, 0xFD, 0x7F } },
  { "TeddyCloud/NXP (0xBA Privacy)", 0xBA, -0x01, { 0x0F, 0x0F, 0x0F, 0x0F } },
  { "TeddyCloud/NXP (0xB3 ID 0x04)", 0xB3,  0x04, { 0x0F, 0x0F, 0x0F, 0x0F } },
  { "TeddyCloud/Zero (0xBA Privacy)",0xBA, -0x01, { 0x00, 0x00, 0x00, 0x00 } },
  { "TeddyCloud/Zero (0xB3 ID 0x04)",0xB3,  0x04, { 0x00, 0x00, 0x00, 0x00 } }
};
const size_t NUM_KNOWN_KEYS = sizeof(KNOWN_PRIVACY_KEYS) / sizeof(KNOWN_PRIVACY_KEYS[0]);

#endif // CONFIG_H
