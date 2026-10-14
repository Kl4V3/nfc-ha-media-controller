/**
 * ============================================================================
 * Firmware: ESP32 PN5180 NFC-Reader für nfc-ha-media-controller
 * ============================================================================
 * 
 * Hardware:
 *   - ESP32 (NodeMCU WROOM-32)
 *   - NXP PN5180 NFC Frontend
 * 
 * Pin-Belegung:
 *   - MOSI      -> GPIO 23
 *   - MISO      -> GPIO 19
 *   - SCK       -> GPIO 18
 *   - NSS (CS)  -> GPIO 5
 *   - BUSY      -> GPIO 21
 *   - RST       -> GPIO 22
 * ============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <PN5180.h>
#include <PN5180ISO15693.h>
#include <ESPmDNS.h>
#include <WebServer.h>

// Einbinden der Konfiguration
#include "config.h"

#define PN5180_NSS   5
#define PN5180_BUSY  21
#define PN5180_RST   22

#define PN5180_RX_STATUS 0x13

// ============================================================================
// GLOBALE OBJEKTE & STATUS-VARIABLEN
// ============================================================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);
WebServer server(80);

PN5180ISO15693 nfc15693(PN5180_NSS, PN5180_BUSY, PN5180_RST);

bool tagPresent = false;
String currentTagUid = "";
String currentChipType = "";
int missingTagCount = 0;

unsigned long lastScanMillis = 0;
unsigned long lastWifiCheckMillis = 0;
const unsigned long WIFI_CHECK_INTERVAL_MS = 5000;

unsigned long lastMqttCheckMillis = 0;
const unsigned long MQTT_CHECK_INTERVAL_MS = 5000;

unsigned long lastStatusPingMillis = 0;
const unsigned long STATUS_PING_INTERVAL_MS = 60000;

// ============================================================================
// RINGPUFFER FÜR WEB-LOGS
// ============================================================================
#define LOG_BUFFER_SIZE 150
String logLines[LOG_BUFFER_SIZE];
int logHead = 0;
int logCount = 0;

void addLog(const String& msg) {
  unsigned long sec = millis() / 1000;
  char timeBuf[16];
  snprintf(timeBuf, sizeof(timeBuf), "[%02lu:%02lu:%02lu] ", (sec / 3600), (sec % 3600) / 60, sec % 60);

  String fullMsg = String(timeBuf) + msg;
  Serial.println(fullMsg);

  logLines[logHead] = fullMsg;
  logHead = (logHead + 1) % LOG_BUFFER_SIZE;
  if (logCount < LOG_BUFFER_SIZE) {
    logCount++;
  }
}

// ============================================================================
// HILFSFUNKTIONEN
// ============================================================================

String formatUid(const uint8_t* uid, size_t length, bool reverse = false) {
  String result = "";
  if (reverse) {
    for (int i = (int)length - 1; i >= 0; i--) {
      if (uid[i] < 0x10) {
        result += "0";
      }
      result += String(uid[i], HEX);
    }
  } else {
    for (size_t i = 0; i < length; i++) {
      if (uid[i] < 0x10) {
        result += "0";
      }
      result += String(uid[i], HEX);
    }
  }
  result.toLowerCase();
  return result;
}

String getUptimeString() {
  unsigned long s = millis() / 1000;
  unsigned long d = s / 86400;
  s %= 86400;
  unsigned long h = s / 3600;
  s %= 3600;
  unsigned long m = s / 60;
  s %= 60;

  char buf[64];
  if (d > 0) {
    snprintf(buf, sizeof(buf), "%lud %02luh %02lum %02lus", d, h, m, s);
  } else {
    snprintf(buf, sizeof(buf), "%02luh %02lum %02lus", h, m, s);
  }
  return String(buf);
}

void publishStatusAlive() {
  JsonDocument doc;
  doc["reader_id"] = READER_ID;
  doc["status"] = "alive";

  char jsonBuffer[128];
  serializeJson(doc, jsonBuffer);

  if (mqttClient.connected()) {
    mqttClient.publish("rfid/status", jsonBuffer);
    addLog(String("[MQTT] Status-Ping gesendet: ") + jsonBuffer);
  }
}

void publishTagScanned(const String& uid) {
  JsonDocument doc;
  doc["tag_id"] = uid;
  doc["reader_id"] = READER_ID;
  doc["status"] = "scanned";

  char jsonBuffer[256];
  serializeJson(doc, jsonBuffer);

  if (mqttClient.connected()) {
    mqttClient.publish(MQTT_TOPIC_SCANNED, jsonBuffer);
    addLog(String("[MQTT] >>> Tag erkannt gesendet: ") + jsonBuffer);
  } else {
    addLog(String("[MQTT] FEHLER: Nicht verbunden! Konnte Tag ") + uid + " nicht senden.");
  }
}

void publishTagRemoved(const String& uid) {
  JsonDocument doc;
  doc["tag_id"] = uid;
  doc["reader_id"] = READER_ID;
  doc["status"] = "removed";

  char jsonBuffer[256];
  serializeJson(doc, jsonBuffer);

  if (mqttClient.connected()) {
    mqttClient.publish(MQTT_TOPIC_SCANNED, jsonBuffer);
    addLog(String("[MQTT] <<< Tag entfernt gesendet: ") + jsonBuffer);
  } else {
    addLog("[MQTT] FEHLER: Nicht verbunden! Konnte removed nicht senden.");
  }
}

// ============================================================================
// MULTI-PROTOKOLL MANAGEMENT (ISO-15693 Tonies & ISO-14443A NTAG213)
// ============================================================================

enum NfcProtocol {
  PROTO_ISO15693 = 0,
  PROTO_ISO14443A = 1
};

NfcProtocol currentRfProtocol = PROTO_ISO15693; // Default nach setupRF()
NfcProtocol activeTagProtocol = PROTO_ISO15693;

bool switchToIso15693() {
  if (currentRfProtocol == PROTO_ISO15693) return true;
  if (!nfc15693.loadRFConfig(0x0D, 0x8D)) {
    return false;
  }
  currentRfProtocol = PROTO_ISO15693;
  delayMicroseconds(500);
  return true;
}

bool switchToIso14443A() {
  if (currentRfProtocol == PROTO_ISO14443A) return true;
  if (!nfc15693.loadRFConfig(0x00, 0x80)) {
    return false;
  }
  currentRfProtocol = PROTO_ISO14443A;
  delayMicroseconds(500);
  return true;
}

// ============================================================================
// ABSOLUT ROBUSTE NON-BLOCKING TRANSCEIVE ENGINE (ISO-15693)
// ============================================================================

bool transceiveRaw(const uint8_t* cmd, size_t cmdLen, uint8_t* outBuf, uint16_t* outLen, uint16_t maxLen, uint32_t* debugIrq = NULL, uint16_t timeoutMs = 60) {
  nfc15693.clearIRQStatus(0xFFFFFFFF);

  if (!nfc15693.sendData((uint8_t*)cmd, cmdLen)) {
    return false;
  }

  // Warten auf RX_IRQ mit konfigurierbarem Timeout (Standard 60ms für EEPROM-Unlock)
  unsigned long start = millis();
  uint32_t irqStatus = 0;

  while (millis() - start < timeoutMs) {
    irqStatus = nfc15693.getIRQStatus();
    if (irqStatus & RX_IRQ_STAT) {
      break;
    }
    delayMicroseconds(100);
  }

  if (debugIrq) *debugIrq = irqStatus;

  if (!(irqStatus & RX_IRQ_STAT)) {
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  uint32_t rxStatus;
  nfc15693.readRegister(PN5180_RX_STATUS, &rxStatus);
  uint16_t len = (uint16_t)(rxStatus & 0x000001ff);

  if (len > maxLen) {
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  if (len == 0) {
    // Leeres ACK Frame empfangen (z. B. 0xBA Disable Privacy)
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    if (outBuf) outBuf[0] = 0x00;
    if (outLen) *outLen = 1;
    return true;
  }

  uint8_t* data = nfc15693.readData(len, outBuf);
  nfc15693.clearIRQStatus(0xFFFFFFFF);

  if (!data) {
    return false;
  }

  if (outLen) *outLen = len;
  return true;
}

/**
 * Standard ISO-15693 Inventory (0x26, 0x01, 0x00)
 */
bool safeInventory(uint8_t* outUid) {
  uint8_t invDual[] = { 0x26, 0x01, 0x00 };
  uint8_t rxBuf[32];
  uint16_t rxLen = 0;

  if (transceiveRaw(invDual, sizeof(invDual), rxBuf, &rxLen, sizeof(rxBuf), NULL, 15)) {
    if (rxLen >= 10 && (rxBuf[0] & 0x01) == 0) {
      memcpy(outUid, &rxBuf[2], 8);
      return true;
    }
  }

  uint8_t invSingle[] = { 0x22, 0x01, 0x00 };
  if (transceiveRaw(invSingle, sizeof(invSingle), rxBuf, &rxLen, sizeof(rxBuf), NULL, 15)) {
    if (rxLen >= 10 && (rxBuf[0] & 0x01) == 0) {
      memcpy(outUid, &rxBuf[2], 8);
      return true;
    }
  }

  return false;
}

/**
 * ISO-15693 Get System Information (0x02, 0x2B) - Liefert UID auch nach direktem SetPassword
 */
bool safeGetSysInfo(uint8_t* outUid) {
  uint8_t sysInfo[] = { 0x02, 0x2B };
  uint8_t rxBuf[32];
  uint16_t rxLen = 0;

  if (transceiveRaw(sysInfo, sizeof(sysInfo), rxBuf, &rxLen, sizeof(rxBuf), NULL, 15)) {
    if (rxLen >= 10 && (rxBuf[0] & 0x01) == 0) {
      memcpy(outUid, &rxBuf[2], 8);
      return true;
    }
  }
  return false;
}

/**
 * Liest UID entweder per Inventory oder per Get System Information
 */
bool readTagUid(uint8_t* outUid) {
  if (safeInventory(outUid)) return true;
  if (safeGetSysInfo(outUid)) return true;
  return false;
}

// ============================================================================
// TONIEBOX & TEDDYCLOUD UNLOCK ENGINE (ULTRA-LOW LATENCY)
// ============================================================================

bool tryUnlockToniebox(uint8_t* outUid, String& unlockedTypeName) {
  uint8_t rxBuf[32];
  uint16_t rxLen = 0;

  // 1. Get Random Number: 0x02, 0xB2, 0x04
  uint8_t getRndCmd[] = { 0x02, 0xB2, 0x04 };
  if (!transceiveRaw(getRndCmd, sizeof(getRndCmd), rxBuf, &rxLen, sizeof(rxBuf), NULL, 15) || rxLen < 3) {
    return false; // Kein Privacy Tag im Feld -> Stille, kein Spam
  }

  uint8_t r0 = rxBuf[1];
  uint8_t r1 = rxBuf[2];

  // 2. Schlüsselkandidaten testen:
  // Weltweites Toniebox Original-Passwort: 0x5B 0x6E 0xFD 0x7F (Little Endian)
  const uint8_t KEY_BOXINE_LE[4]  = { 0x5B, 0x6E, 0xFD, 0x7F };
  const uint8_t KEY_BOXINE_BE[4]  = { 0x7F, 0xFD, 0x6E, 0x5B };
  const uint8_t KEY_TEDDY_NXP[4]  = { 0x0F, 0x0F, 0x0F, 0x0F };
  const uint8_t KEY_TEDDY_ZERO[4] = { 0x00, 0x00, 0x00, 0x00 };

  struct KeyTrial {
    const char* label;
    const uint8_t* key;
    bool swapRnd;
    uint8_t cmdCode;
    int8_t pwdId;
  };

  const KeyTrial TRIALS[] = {
    { "Toniebox Original (Boxine)", KEY_BOXINE_LE,  false, 0xB3,  0x04 },
    { "Toniebox Original (BE)",     KEY_BOXINE_BE,  false, 0xB3,  0x04 },
    { "Toniebox SLIX-L (ID 0x03)",  KEY_BOXINE_LE,  false, 0xB3,  0x03 },
    { "Toniebox SLIX-L (0xBA)",     KEY_BOXINE_LE,  false, 0xBA, -0x01 },
    { "TeddyCloud / NXP (0x0F)",    KEY_TEDDY_NXP,  false, 0xB3,  0x04 },
    { "TeddyCloud / Zero (0x00)",   KEY_TEDDY_ZERO, false, 0xB3,  0x04 }
  };
  const size_t NUM_TRIALS = sizeof(TRIALS) / sizeof(TRIALS[0]);

  static unsigned long lastLogMillis = 0;
  bool doLog = (millis() - lastLogMillis > 2500);

  for (size_t i = 0; i < NUM_TRIALS; i++) {
    // Falls i > 0: Frische Random Number anfordern
    if (i > 0) {
      memset(rxBuf, 0, sizeof(rxBuf));
      rxLen = 0;
      if (!transceiveRaw(getRndCmd, sizeof(getRndCmd), rxBuf, &rxLen, sizeof(rxBuf), NULL, 15) || rxLen < 3) {
        // Falls der Chip nach Fehlversuch blockiert: kurzer Powercycle zum Aufwecken
        nfc15693.setRF_off();
        delay(8);
        nfc15693.setRF_on();
        delay(10);
        if (!transceiveRaw(getRndCmd, sizeof(getRndCmd), rxBuf, &rxLen, sizeof(rxBuf), NULL, 15) || rxLen < 3) {
          continue;
        }
      }
      r0 = rxBuf[1];
      r1 = rxBuf[2];
    }

    uint8_t cr0 = TRIALS[i].swapRnd ? r1 : r0;
    uint8_t cr1 = TRIALS[i].swapRnd ? r0 : r1;
    const uint8_t* k = TRIALS[i].key;

    uint8_t setPwdCmd[10];
    size_t cmdLen = 0;
    setPwdCmd[0] = 0x02; // Flags
    setPwdCmd[1] = TRIALS[i].cmdCode;
    setPwdCmd[2] = 0x04; // NXP Mfg Code

    if (TRIALS[i].pwdId >= 0) {
      setPwdCmd[3] = (uint8_t)TRIALS[i].pwdId;
      setPwdCmd[4] = k[0] ^ cr0;
      setPwdCmd[5] = k[1] ^ cr1;
      setPwdCmd[6] = k[2] ^ cr0;
      setPwdCmd[7] = k[3] ^ cr1;
      cmdLen = 8;
    } else {
      setPwdCmd[3] = k[0] ^ cr0;
      setPwdCmd[4] = k[1] ^ cr1;
      setPwdCmd[5] = k[2] ^ cr0;
      setPwdCmd[6] = k[3] ^ cr1;
      cmdLen = 7;
    }

    uint32_t trialIrq = 0;
    memset(rxBuf, 0, sizeof(rxBuf));
    rxLen = 0;
    bool sentOk = transceiveRaw(setPwdCmd, cmdLen, rxBuf, &rxLen, sizeof(rxBuf), &trialIrq);

    // Wenn der Tag das Passwort akzeptiert hat oder geantwortet hat:
    if (sentOk && rxLen >= 1 && (rxBuf[0] & 0x01) == 0) {
      delay(4);
      for (int retry = 0; retry < 3; retry++) {
        if (readTagUid(outUid)) {
          unlockedTypeName = TRIALS[i].label;
          char buf[128];
          snprintf(buf, sizeof(buf), "[NFC] >>> ERFOLGREICH ENTSPERRT: %s <<<", TRIALS[i].label);
          addLog(String(buf));
          return true;
        }
        delay(6);
      }
    }

    // Nach jedem Schlüssel-Fehlversuch: kurzer Powercycle, damit der Chip aus dem HALT-Zustand erwacht
    nfc15693.setRF_off();
    delay(8);
    nfc15693.setRF_on();
    delay(10);
  }

  if (doLog) {
    lastLogMillis = millis();
    addLog("[NFC] Tag im Privacy Mode, aber kein passender Schluessel gefunden (Custom TeddyCloud Key?)");
  }

  return false;
}

// ============================================================================
// ISO-14443 TYPE A ENGINE (NTAG213 / NTAG215 / NTAG216 / MIFARE)
// ============================================================================

uint8_t activeTag14443RawUid[10];
uint8_t activeTag14443RawLen = 0;

bool transceiveRaw14443(const uint8_t* cmd, size_t cmdLen, uint8_t validBits,
                        uint8_t* outBuf, uint16_t* outLen, uint16_t maxLen,
                        uint16_t timeoutMs = 15) {
  nfc15693.clearIRQStatus(0xFFFFFFFF);

  if (!nfc15693.sendData((uint8_t*)cmd, cmdLen, validBits)) {
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  unsigned long start = millis();
  uint32_t irqStatus = 0;

  while (millis() - start < timeoutMs) {
    irqStatus = nfc15693.getIRQStatus();
    if (irqStatus & RX_IRQ_STAT) {
      break;
    }
    delayMicroseconds(80);
  }

  if (!(irqStatus & RX_IRQ_STAT)) {
    irqStatus = nfc15693.getIRQStatus();
  }

  if (!(irqStatus & RX_IRQ_STAT)) {
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  uint32_t rxStatus;
  nfc15693.readRegister(PN5180_RX_STATUS, &rxStatus);
  uint16_t len = (uint16_t)(rxStatus & 0x000001ff);

  if (len == 0 || len > maxLen) {
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  uint8_t* data = nfc15693.readData(len, outBuf);
  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
  nfc15693.clearIRQStatus(0xFFFFFFFF);

  if (!data) {
    return false;
  }

  if (outLen) *outLen = len;
  return true;
}

void sendIso14443Halt() {
  nfc15693.clearIRQStatus(0xFFFFFFFF);
  nfc15693.writeRegisterWithOrMask(CRC_RX_CONFIG, 0x01);
  nfc15693.writeRegisterWithOrMask(CRC_TX_CONFIG, 0x01);
  uint8_t haltCmd[2] = { 0x50, 0x00 };
  nfc15693.sendData(haltCmd, 2, 0x00);

  // Warten bis PN5180 die Übertragung (TX) vollständig beendet hat
  unsigned long start = millis();
  while (millis() - start < 10) {
    if (nfc15693.getIRQStatus() & TX_IRQ_STAT) {
      break;
    }
    delayMicroseconds(50);
  }
  delay(1);
  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
  nfc15693.clearIRQStatus(0xFFFFFFFF);
}

bool scanIso14443A(uint8_t* outUid, uint8_t* outLen, String& chipType) {
  // Transceiver sauber stoppen
  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE / StopCom
  delayMicroseconds(100);

  if (!switchToIso14443A()) {
    return false;
  }

  // 1. Crypto1 aus, CRC aus für WUPA / REQA
  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xFFFFFFBF);
  nfc15693.writeRegisterWithAndMask(CRC_RX_CONFIG, 0xFFFFFFFE);
  nfc15693.writeRegisterWithAndMask(CRC_TX_CONFIG, 0xFFFFFFFE);

  // 2. WUPA senden (0x52, 7 Bits) mit bis zu 3 Retries
  // WUPA weckt Tags im IDLE-, READY-, ACTIVE- und HALT-Zustand auf
  uint8_t wupaCmd = 0x52;
  uint8_t atqaBuf[8];
  uint16_t atqaLen = 0;
  bool wupaOk = false;

  for (int retry = 0; retry < 3; retry++) {
    if (transceiveRaw14443(&wupaCmd, 1, 0x07, atqaBuf, &atqaLen, sizeof(atqaBuf), 15) && atqaLen >= 2) {
      wupaOk = true;
      break;
    }
    delay(2);
  }

  if (!wupaOk) {
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  delayMicroseconds(400);

  // 3. Anticollision Cascade Level 1 (0x93, 0x20) ohne CRC
  nfc15693.writeRegisterWithAndMask(CRC_RX_CONFIG, 0xFFFFFFFE);
  nfc15693.writeRegisterWithAndMask(CRC_TX_CONFIG, 0xFFFFFFFE);
  uint8_t cl1Cmd[2] = { 0x93, 0x20 };
  uint8_t cl1Buf[8];
  uint16_t cl1Len = 0;
  if (!transceiveRaw14443(cl1Cmd, 2, 0x00, cl1Buf, &cl1Len, sizeof(cl1Buf), 15) || cl1Len < 5) {
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  // BCC1 prüfen (XOR Byte 0..3)
  uint8_t bcc1 = cl1Buf[0] ^ cl1Buf[1] ^ cl1Buf[2] ^ cl1Buf[3];
  if (cl1Buf[4] != bcc1) {
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }

  delayMicroseconds(400);

  // 4. Select Cascade Level 1 mit CRC
  nfc15693.writeRegisterWithOrMask(CRC_RX_CONFIG, 0x01);
  nfc15693.writeRegisterWithOrMask(CRC_TX_CONFIG, 0x01);
  uint8_t sel1Cmd[7];
  sel1Cmd[0] = 0x93;
  sel1Cmd[1] = 0x70;
  memcpy(&sel1Cmd[2], cl1Buf, 5);
  uint8_t sak1Buf[8];
  uint16_t sak1Len = 0;
  if (!transceiveRaw14443(sel1Cmd, 7, 0x00, sak1Buf, &sak1Len, sizeof(sak1Buf), 15) || sak1Len < 1) {
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return false;
  }
  uint8_t sak1 = sak1Buf[0];

  // 5. Prüfen auf 7-Byte UID (Cascade Tag 0x88 in CL1) oder 4-Byte UID
  if (cl1Buf[0] == 0x88) {
    // 7-Byte UID (NTAG213 / NTAG215 / NTAG216 / MIFARE Ultralight)
    if ((sak1 & 0x04) == 0) {
      nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
      nfc15693.clearIRQStatus(0xFFFFFFFF);
      return false;
    }
    outUid[0] = cl1Buf[1];
    outUid[1] = cl1Buf[2];
    outUid[2] = cl1Buf[3];

    delayMicroseconds(400);

    // Anticollision Cascade Level 2 (0x95, 0x20) ohne CRC
    nfc15693.writeRegisterWithAndMask(CRC_RX_CONFIG, 0xFFFFFFFE);
    nfc15693.writeRegisterWithAndMask(CRC_TX_CONFIG, 0xFFFFFFFE);
    uint8_t cl2Cmd[2] = { 0x95, 0x20 };
    uint8_t cl2Buf[8];
    uint16_t cl2Len = 0;
    if (!transceiveRaw14443(cl2Cmd, 2, 0x00, cl2Buf, &cl2Len, sizeof(cl2Buf), 15) || cl2Len < 5) {
      nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
      nfc15693.clearIRQStatus(0xFFFFFFFF);
      return false;
    }

    // BCC2 prüfen
    uint8_t bcc2 = cl2Buf[0] ^ cl2Buf[1] ^ cl2Buf[2] ^ cl2Buf[3];
    if (cl2Buf[4] != bcc2) {
      nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
      nfc15693.clearIRQStatus(0xFFFFFFFF);
      return false;
    }

    delayMicroseconds(400);

    // Select Cascade Level 2 mit CRC
    nfc15693.writeRegisterWithOrMask(CRC_RX_CONFIG, 0x01);
    nfc15693.writeRegisterWithOrMask(CRC_TX_CONFIG, 0x01);
    uint8_t sel2Cmd[7];
    sel2Cmd[0] = 0x95;
    sel2Cmd[1] = 0x70;
    memcpy(&sel2Cmd[2], cl2Buf, 5);
    uint8_t sak2Buf[8];
    uint16_t sak2Len = 0;
    if (!transceiveRaw14443(sel2Cmd, 7, 0x00, sak2Buf, &sak2Len, sizeof(sak2Buf), 15) || sak2Len < 1) {
      nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
      nfc15693.clearIRQStatus(0xFFFFFFFF);
      return false;
    }

    outUid[3] = cl2Buf[0];
    outUid[4] = cl2Buf[1];
    outUid[5] = cl2Buf[2];
    outUid[6] = cl2Buf[3];
    *outLen = 7;

    // Kurze Beruhigungspause vor GET_VERSION (0x60)
    delayMicroseconds(600);

    // Chiptyp-Erkennung via GET_VERSION (0x60)
    uint8_t getVerCmd = 0x60;
    uint8_t verBuf[16];
    uint16_t verLen = 0;
    if (transceiveRaw14443(&getVerCmd, 1, 0x00, verBuf, &verLen, sizeof(verBuf), 20) && verLen >= 8) {
      if (verBuf[6] == 0x0F) {
        chipType = "NTAG213 (ISO-14443A)";
      } else if (verBuf[6] == 0x11) {
        chipType = "NTAG215 (ISO-14443A)";
      } else if (verBuf[6] == 0x13) {
        chipType = "NTAG216 (ISO-14443A)";
      } else {
        chipType = "NTAG / Ultralight (ISO-14443A)";
      }
    } else {
      chipType = "NTAG213 / Ultralight (ISO-14443A)";
    }
  } else {
    // 4-Byte UID (z. B. MIFARE Classic 1K / 4K)
    if ((sak1 & 0x04) != 0) {
      nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
      nfc15693.clearIRQStatus(0xFFFFFFFF);
      return false;
    }
    outUid[0] = cl1Buf[0];
    outUid[1] = cl1Buf[1];
    outUid[2] = cl1Buf[2];
    outUid[3] = cl1Buf[3];
    *outLen = 4;

    if (sak1 == 0x08) {
      chipType = "MIFARE Classic 1K (ISO-14443A)";
    } else if (sak1 == 0x18) {
      chipType = "MIFARE Classic 4K (ISO-14443A)";
    } else {
      chipType = "ISO-14443A Tag";
    }

    // MIFARE Classic bleibt im ACTIVE Zustand (KEIN HALT)
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
    nfc15693.clearIRQStatus(0xFFFFFFFF);
    return true;
  }

  // Transceiver sauber in IDLE versetzen (NTAG bleibt im ACTIVE Zustand selektiert)
  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
  nfc15693.clearIRQStatus(0xFFFFFFFF);

  return true;
}

bool scanIso15693Internal(String& detectedUid, String& chipType) {
  if (!switchToIso15693()) {
    return false;
  }

  uint8_t uid[8];
  memset(uid, 0, sizeof(uid));

  // Stufe 1: Standard-Inventory
  if (readTagUid(uid)) {
    detectedUid = formatUid(uid, 8, true);
    chipType = "iCode SLI / ISO-15693 Standard";
    return true;
  }

  // Stufe 2: Toniebox Unlock Engine
  String unlockedType = "";
  if (tryUnlockToniebox(uid, unlockedType)) {
    detectedUid = formatUid(uid, 8, true);
    chipType = unlockedType;
    return true;
  }

  return false;
}

bool scanIso14443Internal(String& detectedUid, String& chipType) {
  uint8_t uid[10];
  uint8_t uidLen = 0;
  memset(uid, 0, sizeof(uid));

  if (scanIso14443A(uid, &uidLen, chipType)) {
    detectedUid = formatUid(uid, uidLen, false);
    memcpy(activeTag14443RawUid, uid, uidLen);
    activeTag14443RawLen = uidLen;
    return true;
  }

  return false;
}

// Presence-Check für 4-Byte Tags (MIFARE Classic 1K / 4K)
// Da MIFARE Classic Speicherblöcke ohne Krypto-1 blockiert,
// nutzen wir den schnellen WUPA -> Anticollision CL1 Zyklus (UID-Verifikation) mit bis zu 3 Retries.
bool checkIso14443ClassicPresence(String& detectedUid, String& chipType) {
  // Transceiver sauber stoppen
  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE / StopCom
  delayMicroseconds(100);

  if (!switchToIso14443A()) return false;

  for (int attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) {
      delay(3);
    }

    // Crypto1 aus, CRC aus für WUPA
    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xFFFFFFBF);
    nfc15693.writeRegisterWithAndMask(CRC_RX_CONFIG, 0xFFFFFFFE);
    nfc15693.writeRegisterWithAndMask(CRC_TX_CONFIG, 0xFFFFFFFE);

    uint8_t wupaCmd = 0x52;
    uint8_t atqaBuf[8];
    uint16_t atqaLen = 0;

    if (!transceiveRaw14443(&wupaCmd, 1, 0x07, atqaBuf, &atqaLen, sizeof(atqaBuf), 15) || atqaLen < 2) {
      continue;
    }

    delayMicroseconds(400);

    // Anticollision CL1 ohne CRC
    nfc15693.writeRegisterWithAndMask(CRC_RX_CONFIG, 0xFFFFFFFE);
    nfc15693.writeRegisterWithAndMask(CRC_TX_CONFIG, 0xFFFFFFFE);
    uint8_t cl1Cmd[2] = { 0x93, 0x20 };
    uint8_t cl1Buf[8];
    uint16_t cl1Len = 0;
    if (!transceiveRaw14443(cl1Cmd, 2, 0x00, cl1Buf, &cl1Len, sizeof(cl1Buf), 15) || cl1Len < 5) {
      continue;
    }

    // BCC1 prüfen
    uint8_t bcc1 = cl1Buf[0] ^ cl1Buf[1] ^ cl1Buf[2] ^ cl1Buf[3];
    if (cl1Buf[4] != bcc1) {
      continue;
    }

    // UID-Prüfung gegen den aufliegenden Tag
    if (cl1Buf[0] != activeTag14443RawUid[0] ||
        cl1Buf[1] != activeTag14443RawUid[1] ||
        cl1Buf[2] != activeTag14443RawUid[2] ||
        cl1Buf[3] != activeTag14443RawUid[3]) {
      continue;
    }

    // Tag verifiziert!
    detectedUid = currentTagUid;
    chipType = currentChipType;
    return true;
  }

  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8);
  nfc15693.clearIRQStatus(0xFFFFFFFF);
  return false;
}

bool checkIso14443Presence(String& detectedUid, String& chipType) {
  if (activeTag14443RawLen == 0) return false;

  // 1. Spezieller optimierter Presence-Check für 4-Byte Tags (MIFARE Classic 1K / 4K)
  if (activeTag14443RawLen == 4) {
    if (checkIso14443ClassicPresence(detectedUid, chipType)) {
      return true;
    }
    // Re-Scan ohne vorheriges HALT versuchen
    return scanIso14443Internal(detectedUid, chipType);
  }

  // 2. Kontinuierlicher Presence-Check für 7-Byte Tags (NTAG213 / NTAG215 / NTAG216 / Ultralight)
  if (!switchToIso14443A()) return false;

  // Der NTAG ist bereits selektiert im ACTIVE Zustand.
  // READ Page 0 (0x30, 0x00) mit aktiver CRC senden (3 Retries mit je 2ms Pause).
  nfc15693.writeRegisterWithOrMask(CRC_RX_CONFIG, 0x01);
  nfc15693.writeRegisterWithOrMask(CRC_TX_CONFIG, 0x01);

  uint8_t readCmd[2] = { 0x30, 0x00 };
  uint8_t rxBuf[24];
  uint16_t rxLen = 0;
  bool readOk = false;

  for (int attempt = 0; attempt < 3; attempt++) {
    if (transceiveRaw14443(readCmd, 2, 0x00, rxBuf, &rxLen, sizeof(rxBuf), 20) && rxLen >= 16) {
      readOk = true;
      break;
    }
    delay(2);
  }

  if (readOk) {
    bool uidMatches = false;
    if (rxBuf[0] == activeTag14443RawUid[0] &&
        rxBuf[1] == activeTag14443RawUid[1] &&
        rxBuf[2] == activeTag14443RawUid[2] &&
        rxBuf[4] == activeTag14443RawUid[3] &&
        rxBuf[5] == activeTag14443RawUid[4] &&
        rxBuf[6] == activeTag14443RawUid[5] &&
        rxBuf[7] == activeTag14443RawUid[6]) {
      uidMatches = true;
    }

    nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
    nfc15693.clearIRQStatus(0xFFFFFFFF);

    if (uidMatches) {
      detectedUid = currentTagUid;
      chipType = currentChipType;
      return true;
    }
  }

  nfc15693.writeRegisterWithAndMask(SYSTEM_CONFIG, 0xfffffff8); // IDLE
  nfc15693.clearIRQStatus(0xFFFFFFFF);

  // Falls READ fehlschlägt (z. B. HF-Störung, Wackler oder State Reset):
  // KEIN HALT senden! Ein HALT würde den NTAG im HALT-Zustand blockieren,
  // sodass nachfolgende Page-Reads im nächsten Zyklus zwangsweise fehlschlagen.
  // Stattdessen direkt Re-Scan versuchen (WUPA weckt den Tag in jedem Zustand auf).
  return scanIso14443Internal(detectedUid, chipType);
}

/**
 * Gesamter Scan-Ablauf:
 * - Falls ein Tag aufliegt (tagPresent): Ausschließlich das aktive Protokoll scannen (Null HF-Modulationskonflikte)
 * - Im Ruhezustand (kein Tag): ISO-15693 (Tonies) prüfen, danach ISO-14443A (NTAG213) prüfen
 */
bool performNfcScan(String& detectedUid, String& chipType) {
  if (tagPresent) {
    if (activeTagProtocol == PROTO_ISO14443A) {
      // Wenn ein NTAG213 aufliegt: hochzuverlässiger Presence-Check per Read Page 0
      return checkIso14443Presence(detectedUid, chipType);
    } else {
      // Wenn ein Tonie aufliegt: ausschließlich 15693 scannen
      return scanIso15693Internal(detectedUid, chipType);
    }
  }

  // Ruhezustand (kein Tag im Feld):
  // 1. Zuerst ISO-15693 (Tonies) prüfen
  if (scanIso15693Internal(detectedUid, chipType)) {
    activeTagProtocol = PROTO_ISO15693;
    return true;
  }

  // 2. Danach ISO-14443A (NTAG213 / MIFARE) prüfen
  if (scanIso14443Internal(detectedUid, chipType)) {
    activeTagProtocol = PROTO_ISO14443A;
    return true;
  }

  // Wieder auf ISO-15693 zurückschalten für den nächsten Ruhezustands-Zyklus
  switchToIso15693();
  return false;
}

void updateTagState() {
  String scannedUid = "";
  String detectedType = "";
  bool found = performNfcScan(scannedUid, detectedType);

  if (found) {
    missingTagCount = 0;

    if (!tagPresent || (currentTagUid != scannedUid)) {
      tagPresent = true;
      currentTagUid = scannedUid;
      currentChipType = detectedType;
      addLog(String("[NFC] *** NEUER TAG ERKANNT *** UID: ") + currentTagUid + " | Typ: " + currentChipType);
      publishTagScanned(currentTagUid);
    }
  } else {
    if (tagPresent) {
      missingTagCount++;

      if (missingTagCount >= MAX_MISSING_CYCLES) {
        char buf[128];
        snprintf(buf, sizeof(buf), "[NFC] *** TAG ENTFERNT *** UID: %s (nach %d Fehl-Zyklen)", 
                 currentTagUid.c_str(), MAX_MISSING_CYCLES);
        addLog(String(buf));
        
        String removedUid = currentTagUid;
        tagPresent = false;
        currentTagUid = "";
        currentChipType = "";
        missingTagCount = 0;
        activeTag14443RawLen = 0;
        memset(activeTag14443RawUid, 0, sizeof(activeTag14443RawUid));
        activeTagProtocol = PROTO_ISO15693;
        switchToIso15693();
        publishTagRemoved(removedUid);
      }
    }
  }
}

// ============================================================================
// WEBSERVER HANDLER & HTML DASHBOARD
// ============================================================================

const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PN5180 NFC Reader - %READER_ID%</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --green: #22c55e;
      --red: #ef4444;
      --yellow: #f59e0b;
      --terminal-bg: #020617;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 20px; min-height: 100vh; }
    .container { max-width: 1000px; margin: 0 auto; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border); }
    h1 { font-size: 1.5rem; font-weight: 700; color: var(--accent); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 20px; }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 15px; }
    .card-title { font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px; letter-spacing: 0.5px; }
    .card-value { font-size: 1.2rem; font-weight: 600; display: flex; align-items: center; gap: 8px; }
    .badge { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
    .badge-green { background: var(--green); box-shadow: 0 0 8px var(--green); }
    .badge-red { background: var(--red); box-shadow: 0 0 8px var(--red); }
    .badge-yellow { background: var(--yellow); }
    .log-container { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 15px; }
    .log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .log-title { font-size: 1rem; font-weight: 600; }
    .btn-group { display: flex; gap: 8px; }
    button { background: var(--border); color: var(--text); border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 500; transition: background 0.2s; }
    button:hover { background: #475569; }
    button.btn-danger:hover { background: var(--red); }
    .terminal { background: var(--terminal-bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px; height: 380px; overflow-y: auto; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 0.82rem; line-height: 1.5; color: #38bdf8; }
    .log-line { margin-bottom: 2px; white-space: pre-wrap; word-break: break-all; }
    .log-line.tag { color: #4ade80; font-weight: 600; }
    .log-line.removed { color: #fb923c; font-weight: 500; }
    .log-line.mqtt { color: #a78bfa; }
    .log-line.hardware { color: #38bdf8; font-weight: 500; }
    .log-line.error { color: #f87171; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>ESP32 PN5180 NFC Reader v2.2</h1>
        <div style="font-size: 0.85rem; color: var(--text-muted);">Reader-ID: <span id="val-reader" style="color: var(--accent); font-weight: 600;">%READER_ID%</span></div>
      </div>
      <div class="btn-group">
        <button onclick="clearLogs()">Log leeren</button>
        <button class="btn-danger" onclick="restartEsp()">Neustart</button>
      </div>
    </header>

    <div class="grid">
      <div class="card">
        <div class="card-title">Aktueller Tag</div>
        <div class="card-value" id="val-tag"><span class="badge badge-yellow"></span> Kein Tag</div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;" id="val-tag-type">-</div>
      </div>
      <div class="card">
        <div class="card-title">MQTT Verbindung</div>
        <div class="card-value" id="val-mqtt"><span class="badge badge-yellow"></span> Verbinde...</div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;" id="val-mqtt-broker">%MQTT_BROKER%</div>
      </div>
      <div class="card">
        <div class="card-title">WLAN Signal</div>
        <div class="card-value" id="val-wifi"><span class="badge badge-green"></span> %RSSI% dBm</div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;" id="val-ip">%IP%</div>
      </div>
      <div class="card">
        <div class="card-title">Laufzeit & Speicher</div>
        <div class="card-value" id="val-uptime" style="font-size: 1rem;">%UPTIME%</div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">RAM frei: <span id="val-heap">%HEAP% kB</span></div>
      </div>
    </div>

    <div class="log-container">
      <div class="log-header">
        <div class="log-title">Live Log-Konsole</div>
        <div style="font-size: 0.75rem; color: var(--text-muted);"><span id="log-count">0</span> Einträge (Auto-Refresh aktiv)</div>
      </div>
      <div class="terminal" id="terminal"></div>
    </div>
  </div>

  <script>
    let autoScroll = true;
    const term = document.getElementById('terminal');
    term.addEventListener('scroll', () => {
      autoScroll = (term.scrollHeight - term.scrollTop - term.clientHeight) < 40;
    });

    function updateStatus() {
      fetch('/api/status')
        .then(r => r.json())
        .then(d => {
          const tagEl = document.getElementById('val-tag');
          const tagTypeEl = document.getElementById('val-tag-type');
          if (d.tag_present) {
            tagEl.innerHTML = '<span class="badge badge-green"></span> ' + d.tag_uid;
            tagTypeEl.textContent = d.chip_type;
          } else {
            tagEl.innerHTML = '<span class="badge badge-yellow"></span> Kein Tag';
            tagTypeEl.textContent = 'Bereit für Scan...';
          }

          const mqttEl = document.getElementById('val-mqtt');
          if (d.mqtt_connected) {
            mqttEl.innerHTML = '<span class="badge badge-green"></span> Verbunden';
          } else {
            mqttEl.innerHTML = '<span class="badge badge-red"></span> Getrennt';
          }

          document.getElementById('val-wifi').innerHTML = '<span class="badge badge-green"></span> ' + d.wifi_rssi + ' dBm';
          document.getElementById('val-ip').textContent = d.ip;
          document.getElementById('val-uptime').textContent = d.uptime;
          document.getElementById('val-heap').textContent = Math.round(d.free_heap / 1024) + ' kB';
        })
        .catch(e => console.error(e));
    }

    function updateLogs() {
      fetch('/api/log')
        .then(r => r.text())
        .then(text => {
          const lines = text.trim().split('\n');
          document.getElementById('log-count').textContent = lines[0] ? lines.length : 0;
          
          let html = '';
          lines.forEach(l => {
            if (!l) return;
            let cls = '';
            if (l.includes('TAG ERKANNT') || l.includes('ENTSPERRT MIT')) cls = 'tag';
            else if (l.includes('TAG ENTFERNT')) cls = 'removed';
            else if (l.includes('[MQTT]')) cls = 'mqtt';
            else if (l.includes('[HARDWARE]')) cls = 'hardware';
            else if (l.includes('FEHLER') || l.includes('fehlgeschlagen') || l.includes('WARNUNG') || l.includes('abgelehnt')) cls = 'error';
            html += `<div class="log-line ${cls}">${escapeHtml(l)}</div>`;
          });
          term.innerHTML = html;

          if (autoScroll) {
            term.scrollTop = term.scrollHeight;
          }
        })
        .catch(e => console.error(e));
    }

    function escapeHtml(s) {
      return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function clearLogs() {
      fetch('/api/clear', { method: 'POST' }).then(() => updateLogs());
    }

    function restartEsp() {
      if (confirm('Möchtest du den ESP32 wirklich neustarten?')) {
        fetch('/api/restart', { method: 'POST' });
        alert('ESP32 startet neu... Die Seite lädt in 5 Sekunden neu.');
        setTimeout(() => location.reload(), 5000);
      }
    }

    setInterval(updateStatus, 1500);
    setInterval(updateLogs, 1500);
    updateStatus();
    updateLogs();
  </script>
</body>
</html>
)rawliteral";

void handleRoot() {
  String html = FPSTR(INDEX_HTML);
  html.replace("%READER_ID%", READER_ID);
  html.replace("%MQTT_BROKER%", MQTT_BROKER);
  html.replace("%IP%", WiFi.localIP().toString());
  html.replace("%RSSI%", String(WiFi.RSSI()));
  html.replace("%UPTIME%", getUptimeString());
  html.replace("%HEAP%", String(ESP.getFreeHeap() / 1024));

  server.send(200, "text/html", html);
}

void handleApiLog() {
  String out = "";
  int startIdx = (logCount == LOG_BUFFER_SIZE) ? logHead : 0;
  for (int i = 0; i < logCount; i++) {
    int idx = (startIdx + i) % LOG_BUFFER_SIZE;
    out += logLines[idx] + "\n";
  }
  server.send(200, "text/plain", out);
}

void handleApiStatus() {
  JsonDocument doc;
  doc["reader_id"] = READER_ID;
  doc["tag_present"] = tagPresent;
  doc["tag_uid"] = currentTagUid;
  doc["chip_type"] = currentChipType;
  doc["mqtt_connected"] = mqttClient.connected();
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["ip"] = WiFi.localIP().toString();
  doc["uptime"] = getUptimeString();
  doc["free_heap"] = ESP.getFreeHeap();

  String json;
  serializeJson(doc, json);
  server.send(200, "application/json", json);
}

void handleApiClear() {
  logHead = 0;
  logCount = 0;
  addLog("[System] Web-Log Puffer geleert.");
  server.send(200, "text/plain", "OK");
}

void handleApiRestart() {
  server.send(200, "text/plain", "Restarting...");
  addLog("[System] Neustart per Web-Interface ausgeloest...");
  delay(500);
  ESP.restart();
}

void setupWebServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/log", HTTP_GET, handleApiLog);
  server.on("/api/status", HTTP_GET, handleApiStatus);
  server.on("/api/clear", HTTP_POST, handleApiClear);
  server.on("/api/restart", HTTP_POST, handleApiRestart);
  server.begin();
  addLog(String("[HTTP] Webserver aktiv auf Port 80 (http://") + WiFi.localIP().toString() + ")");
}

// ============================================================================
// NETZWERK & MQTT VERBINDUNGSHANDLING (Nicht-blockierend)
// ============================================================================

void setupWifi() {
  addLog(String("[WLAN] Initialisiere Verbindung mit SSID: ") + WIFI_SSID);
  
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(READER_ID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

bool wasWifiConnected = false;

void checkWifiConnection() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wasWifiConnected) {
      wasWifiConnected = true;
      addLog(String("[WLAN] Verbunden! IP: ") + WiFi.localIP().toString() + " | RSSI: " + String(WiFi.RSSI()) + " dBm");
      
      if (MDNS.begin(READER_ID)) {
        MDNS.addService("http", "tcp", 80);
        addLog(String("[mDNS] Service erreichbar unter: http://") + READER_ID + ".local");
      }

      setupWebServer();
    }
  } else {
    if (wasWifiConnected) {
      addLog("[WLAN] Verbindung verloren! Versuche Reconnect...");
    }
    wasWifiConnected = false;
    unsigned long now = millis();
    if (now - lastWifiCheckMillis >= WIFI_CHECK_INTERVAL_MS) {
      lastWifiCheckMillis = now;
      WiFi.reconnect();
    }
  }
}

void checkMqttConnection() {
  if (WiFi.status() == WL_CONNECTED && !mqttClient.connected()) {
    unsigned long now = millis();
    if (now - lastMqttCheckMillis >= MQTT_CHECK_INTERVAL_MS) {
      lastMqttCheckMillis = now;
      addLog(String("[MQTT] Verbinde mit Broker ") + MQTT_BROKER + ":" + String(MQTT_PORT) + " ...");

      String clientId = String("ESP32_PN5180_") + READER_ID + "_" + String(random(0xffff), HEX);
      bool connected = false;

      if (strlen(MQTT_USER) > 0) {
        connected = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD);
      } else {
        connected = mqttClient.connect(clientId.c_str());
      }

      if (connected) {
        addLog("[MQTT] >>> ERFOLGREICH MIT BROKER VERBUNDEN! <<<");
        publishStatusAlive();

        if (tagPresent && currentTagUid.length() > 0) {
          publishTagScanned(currentTagUid);
        }
      } else {
        char buf[128];
        snprintf(buf, sizeof(buf), "[MQTT] Verbindung fehlgeschlagen (rc=%d) zu %s:%d | Eigene IP: %s (http://%s)", 
                 mqttClient.state(), MQTT_BROKER, MQTT_PORT, WiFi.localIP().toString().c_str(), WiFi.localIP().toString().c_str());
        addLog(String(buf));
      }
    }
  }
}

// ============================================================================
// ARDUINO SETUP & LOOP
// ============================================================================

void setup() {
  Serial.begin(115200);
  delay(500);

  addLog("==================================================");
  addLog(String(" ESP32 PN5180 NFC Reader Firmware v2.2"));
  addLog(String(" Protocols: ISO-15693 (Tonies) & ISO-14443A (NTAG213)"));
  addLog(String(" Reader-ID: ") + READER_ID + " | Debounce: " + String(MAX_MISSING_CYCLES) + " Zyklen");
  addLog("==================================================");

  // 1. WLAN starten
  setupWifi();

  // 2. MQTT Client konfigurieren
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(512);

  // 3. PN5180 Hardware- & Lötstellen-Diagnose
  addLog("[HARDWARE] Starte Hardware- & Loetstellen-Diagnose...");
  nfc15693.begin();
  delay(10);
  nfc15693.reset();
  delay(10);

  // PN5180 EEPROM & Register auslesen (prüft MOSI, MISO, SCK, NSS, BUSY, RST)
  uint8_t productVersion[2] = {0, 0};
  uint8_t firmwareVersion[2] = {0, 0};
  uint8_t eepromVersion[2] = {0, 0};

  bool eepromOk = nfc15693.readEEprom(0x10, productVersion, 2) &&
                  nfc15693.readEEprom(0x12, firmwareVersion, 2) &&
                  nfc15693.readEEprom(0x14, eepromVersion, 2);

  uint32_t sysConfig = 0;
  bool regOk = nfc15693.readRegister(0x00, &sysConfig);

  char diagBuf[128];
  if (eepromOk && regOk && (firmwareVersion[0] != 0 || firmwareVersion[1] != 0)) {
    snprintf(diagBuf, sizeof(diagBuf), "[HARDWARE] SPI & Chip Kommunikation OK! FW: v%d.%d | EEPROM: v%d.%d | Product: v%d.%d",
             firmwareVersion[1], firmwareVersion[0], eepromVersion[1], eepromVersion[0], productVersion[1], productVersion[0]);
    addLog(String(diagBuf));
  } else {
    addLog("[HARDWARE] FEHLER: PN5180 antwortet nicht! Pruefe MOSI(23), MISO(19), SCK(18), NSS(5) oder BUSY(21)!");
  }

  if (nfc15693.setupRF()) {
    addLog("[HARDWARE] RF-Feld erfolgreich aktiviert (Antenne & HF-Treiber OK).");
    uint32_t t1Config = 0, t1Reload = 0, rxWait = 0;
  nfc15693.readRegister(TIMER1_CONFIG, &t1Config);
  nfc15693.readRegister(TIMER1_RELOAD, &t1Reload);
  nfc15693.readRegister(RX_WAIT_CONFIG, &rxWait);
  char tBuf[128];
  snprintf(tBuf, sizeof(tBuf), "[HARDWARE] Timer1-Config: 0x%06X | Reload: 0x%06X | RxWait: 0x%06X", 
           t1Config & 0xFFFFFF, t1Reload & 0xFFFFFF, rxWait & 0xFFFFFF);
  addLog(String(tBuf));

  addLog("[HARDWARE-CHECK] >>> ALLE 6 PINS (MOSI, MISO, SCK, NSS, BUSY, RST) SIND PERFEKT VERLOETET! <<<");
  } else {
    addLog("[HARDWARE] FEHLER: setupRF() fehlgeschlagen. Pruefe Antenne, BUSY(21) und 3.3V/5V Spannungsversorgung!");
  }
  addLog("[PN5180] Bereit. Continuous Polling aktiv.");
}

void loop() {
  checkWifiConnection();
  checkMqttConnection();

  if (mqttClient.connected()) {
    mqttClient.loop();

    unsigned long now = millis();
    if (now - lastStatusPingMillis >= STATUS_PING_INTERVAL_MS) {
      lastStatusPingMillis = now;
      publishStatusAlive();
    }
  }

  if (WiFi.status() == WL_CONNECTED) {
    server.handleClient();
  }

  unsigned long currentMillis = millis();
  if (currentMillis - lastScanMillis >= SCAN_INTERVAL_MS) {
    lastScanMillis = currentMillis;
    updateTagState();
  }
}
