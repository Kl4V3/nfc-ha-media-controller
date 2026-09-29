/**
 * ============================================================================
 * Firmware: M5Stack ATOM Lite + RFID Unit (I2C) für nfc-ha-media-controller
 * ============================================================================
 *
 * Hardware:
 *   - M5Stack ATOM Lite (ESP32-PICO-D4)
 *   - M5Stack RFID / RFID 2 Unit (WS1850S / MFRC522 via Grove I2C)
 *
 * Pin-Belegung:
 *   - Grove SDA   -> GPIO 26
 *   - Grove SCL   -> GPIO 32
 *   - NeoPixel LED-> GPIO 27 (1x SK6812 / WS2812 RGB)
 *   - Front-Button-> GPIO 39 (Active LOW)
 * ============================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <MFRC522_I2C.h>

// Alias für MFRC522-Typen
using MFRC522 = MFRC522_I2C;

// Einbinden der Konfiguration
#include "config.h"

// ============================================================================
// GLOBALE OBJEKTE & STATUS-VARIABLEN
// ============================================================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);
WebServer server(80);

// MFRC522 über I2C initialisieren (RST = 255 / nicht verbunden bei Grove)
MFRC522_I2C mfrc522(MFRC522_I2C_ADDR, 255);

// ============================================================================
// STATUS-LED STEUERUNG (Natives ESP32 RMT neopixelWrite für SK6812/WS2812 auf GPIO 27)
// ============================================================================
unsigned long ledStateUntilMillis = 0;
bool ledTemporarilyOverridden = false;

void setLedColor(uint8_t r, uint8_t g, uint8_t b, unsigned long durationMs = 0) {
  neopixelWrite(ATOM_LED_PIN, r, g, b);
  if (durationMs > 0) {
    ledStateUntilMillis = millis() + durationMs;
    ledTemporarilyOverridden = true;
  } else {
    ledTemporarilyOverridden = false;
  }
}

void updateLedState() {
  if (ledTemporarilyOverridden) {
    if (millis() >= ledStateUntilMillis) {
      ledTemporarilyOverridden = false;
    } else {
      return;
    }
  }

  // Dauerhafter Basis-Status
  if (WiFi.status() != WL_CONNECTED) {
    // Rot: Kein WLAN
    neopixelWrite(ATOM_LED_PIN, 180, 0, 0);
  } else if (!mqttClient.connected()) {
    // Orange: WLAN da, aber MQTT noch nicht verbunden
    neopixelWrite(ATOM_LED_PIN, 180, 70, 0);
  } else {
    // Gedimmtes Grün: Bereit und verbunden
    neopixelWrite(ATOM_LED_PIN, 0, 30, 0);
  }
}

// Tag-Status & Entprellung
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

// Button-Entprellung (GPIO 39)
unsigned long buttonDownMillis = 0;
bool buttonWasPressed = false;

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

String formatUid(const uint8_t* uid, size_t length) {
  String result = "";
  for (size_t i = 0; i < length; i++) {
    if (i > 0) {
      result += "-";
    }
    if (uid[i] < 0x10) {
      result += "0";
    }
    result += String(uid[i], HEX);
  }
  result.toUpperCase();
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
    mqttClient.publish(MQTT_TOPIC_STATUS, jsonBuffer);
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
    addLog(String("[MQTT] >>> Tag erkannt gesendet (Play): ") + jsonBuffer);
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
    addLog(String("[MQTT] <<< Tag entfernt gesendet (Stop): ") + jsonBuffer);
  } else {
    addLog("[MQTT] FEHLER: Nicht verbunden! Konnte removed nicht senden.");
  }
}

// ============================================================================
// RFID KARTENERKENNUNG & KONTINUIERLICHE PRÄSENZPRÜFUNG
// ============================================================================

/**
 * Kontinuierliche Präsenz-Prüfung:
 * Ein Tag im Feld wechselt nach dem ersten Auslesen in den HALT-Zustand.
 * Standard-REQA (PICC_IsNewCardPresent) ignoriert angehaltene Tags!
 * Daher testen wir erst REQA (neue Tags) und dann WUPA (bereits aufliegende Tags).
 */
bool isCardPresent(byte* bufferATQA, byte* bufferSize) {
  // 1. Suche nach neuen Karten im IDLE-Zustand (REQA 0x26)
  byte status = mfrc522.PICC_RequestA(bufferATQA, bufferSize);
  if (status == MFRC522::STATUS_OK) {
    return true;
  }

  // 2. Wecke bereits gelesene / angehaltene Karten im HALT-Zustand auf (WUPA 0x52)
  status = mfrc522.PICC_WakeupA(bufferATQA, bufferSize);
  return (status == MFRC522::STATUS_OK);
}

bool performRfidScan(String& detectedUid, String& chipType) {
  byte atqa[2];
  byte atqaSize = sizeof(atqa);

  if (!isCardPresent(atqa, &atqaSize)) {
    return false;
  }

  // Versuche die UID auszulesen (Antikollision / Select)
  if (!mfrc522.PICC_ReadCardSerial()) {
    return false;
  }

  detectedUid = formatUid(mfrc522.uid.uidByte, mfrc522.uid.size);

  // Chiptyp ermitteln (Mifare Classic, Ultralight, NTAG etc.)
  byte piccType = mfrc522.PICC_GetType(mfrc522.uid.sak);
  chipType = String(mfrc522.PICC_GetTypeName(piccType));

  // Karte wieder in den Halt-Zustand versetzen, damit der Bus frei bleibt
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();

  return true;
}

void updateTagState() {
  String scannedUid = "";
  String detectedType = "";
  bool found = performRfidScan(scannedUid, detectedType);

  if (found) {
    missingTagCount = 0;

    if (!tagPresent || (currentTagUid != scannedUid)) {
      tagPresent = true;
      currentTagUid = scannedUid;
      currentChipType = detectedType;
      addLog(String("[NFC] *** NEUER TAG ERKANNT *** UID: ") + currentTagUid + " | Typ: " + currentChipType);
      
      // Visuelles Feedback: LED blinkt kurz Cyan/Grün auf
      setLedColor(0, 255, 180, 350);
      publishTagScanned(currentTagUid);
    }
  } else {
    if (tagPresent) {
      missingTagCount++;

      // Erst wenn MAX_MISSING_CYCLES aufeinanderfolgend kein Tag gesehen wurde,
      // gilt der Tag als sicher entfernt (Entprellung gegen HF-Aussetzer).
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

        // Visuelles Feedback: LED blinkt kurz Orange auf
        setLedColor(255, 100, 0, 350);
        publishTagRemoved(removedUid);
      }
    }
  }
}

// ============================================================================
// HARDWARE BUTTON HANDLING (GPIO 39)
// ============================================================================

void handleButton() {
  // GPIO 39 ist Active LOW (gedrückt = LOW)
  bool isPressed = (digitalRead(ATOM_BTN_PIN) == LOW);

  if (isPressed && !buttonWasPressed) {
    buttonWasPressed = true;
    buttonDownMillis = millis();
  } else if (!isPressed && buttonWasPressed) {
    unsigned long duration = millis() - buttonDownMillis;
    buttonWasPressed = false;

    if (duration >= 3000) {
      addLog("[BUTTON] Langer Tastendruck erkannt (>3s) -> Starte Neustart...");
      setLedColor(255, 0, 0, 1000);
      delay(500);
      ESP.restart();
    } else if (duration >= 50) {
      addLog("[BUTTON] Kurzer Tastendruck erkannt -> Sende Status-Ping...");
      setLedColor(255, 255, 0, 300);
      publishStatusAlive();
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
  <title>M5Stack Atom Lite RFID - %READER_ID%</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #06b6d4;
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
        <h1>M5Stack ATOM Lite RFID v2.2</h1>
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
            if (l.includes('TAG ERKANNT')) cls = 'tag';
            else if (l.includes('TAG ENTFERNT')) cls = 'removed';
            else if (l.includes('[MQTT]')) cls = 'mqtt';
            else if (l.includes('[HARDWARE]') || l.includes('[BUTTON]')) cls = 'hardware';
            else if (l.includes('FEHLER') || l.includes('fehlgeschlagen') || l.includes('WARNUNG')) cls = 'error';
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
  setLedColor(0, 50, 200); // Blau beim Verbindungsaufbau

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

      String clientId = String("M5Atom_RFID_") + READER_ID + "_" + String(random(0xffff), HEX);
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
        snprintf(buf, sizeof(buf), "[MQTT] Verbindung fehlgeschlagen (rc=%d) zu %s:%d", 
                 mqttClient.state(), MQTT_BROKER, MQTT_PORT);
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

  // 1. Status NeoPixel initialisieren (Blau beim Start)
  setLedColor(0, 0, 255);

  // 2. Button GPIO 39
  pinMode(ATOM_BTN_PIN, INPUT);

  addLog("==================================================");
  addLog(String(" M5Stack ATOM Lite RFID Custom Firmware v2.2"));
  addLog(String(" Reader-ID: ") + READER_ID + " | Debounce: " + String(MAX_MISSING_CYCLES) + " Zyklen");
  addLog("==================================================");

  // 3. I2C Bus für M5Stack Grove Port starten (SDA=26, SCL=32)
  addLog(String("[HARDWARE] Starte Grove I2C Bus auf SDA=") + String(GROVE_SDA) + ", SCL=" + String(GROVE_SCL) + " ...");
  Wire.begin(GROVE_SDA, GROVE_SCL, 100000);

  // 4. MFRC522 initialisieren
  mfrc522.PCD_Init();
  byte version = mfrc522.PCD_ReadRegister(mfrc522.VersionReg);
  char verBuf[128];
  snprintf(verBuf, sizeof(verBuf), "[HARDWARE] MFRC522/WS1850S Chip-Version: 0x%02X", version);
  addLog(String(verBuf));

  if (version == 0x00 || version == 0xFF) {
    addLog("[HARDWARE] WARNUNG: Kein MFRC522/WS1850S Chip auf I2C 0x28 erkannt! Pruefe Grove-Kabel!");
  } else {
    addLog("[HARDWARE] >>> GROVE I2C RFID UNIT ERFOLGREICH INITIALISIERT! <<<");
  }

  // Antennenverstärkung auf Maximum setzen (48dB) für beste Erkennungsreichweite
  mfrc522.PCD_SetAntennaGain(mfrc522.RxGain_max);

  // 5. WLAN & MQTT starten
  setupWifi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(512);

  addLog("[RFID] Bereit. Kontinuierliches Polling mit Debounce aktiv.");
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

  // Button abfragen
  handleButton();

  // LED-Status aktualisieren
  updateLedState();

  // RFID kontinuierlich scannen
  unsigned long currentMillis = millis();
  if (currentMillis - lastScanMillis >= SCAN_INTERVAL_MS) {
    lastScanMillis = currentMillis;
    updateTagState();
  }
}
