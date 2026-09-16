// Guard alert panel — ambient light + sound indicator for the guard post.
//
// STATUS: inactive. This is source code only, not flashed to any device —
// see README.md. No hardware has been bought yet; this file changes
// nothing about the running system until someone builds and flashes it.
//
// Behavior (see chat/README for the UX reasoning behind this design):
//   - RED, pulsing, repeats a two-tone chime every ~45s   -> a TARGET_ALERT
//     is pending (GET /alerts/pending non-empty)
//   - AMBER, pulsing, single soft chime once on arrival   -> an unknown
//     person is pending guard review (GET /guard/pending, no target alert)
//   - OFF, silent                                         -> nothing pending
//   - Button press while RED acknowledges the oldest pending target alert
//     (PATCH /alerts/{id}/acknowledge) — mirrors the web dashboard's own
//     "Acknowledge" button, same underlying alert_acknowledged flag.
//
// Target board: any ESP32 dev board (Arduino core). Needs the ArduinoJson
// library (for parsing /alerts/pending and /guard/pending responses).

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ---- Fill these in when hardware exists — do not commit real values. ----
const char *WIFI_SSID = "CHANGEME";
const char *WIFI_PASSWORD = "CHANGEME";
const char *API_BASE_URL = "https://alternative-identifier.onrender.com";

// A dedicated SECURITY-tier admin account for this device — not a human's
// personal login. /alerts/pending and its acknowledge endpoint require
// admin_tier SECURITY or ORIGINAL; /guard/pending only needs role=ADMIN or
// GUARD, which a SECURITY-tier admin account already satisfies too, so one
// account covers both endpoints.
const char *DEVICE_USERNAME = "CHANGEME";
const char *DEVICE_PASSWORD = "CHANGEME";

// ---- Pins — adjust to whatever the actual wiring ends up being. ----
const int PIN_LED_RED = 25;
const int PIN_LED_AMBER = 26;
const int PIN_BUZZER = 27;
const int PIN_BUTTON = 14; // to GND, uses internal pull-up

const unsigned long POLL_INTERVAL_MS = 7000;
const unsigned long RED_CHIME_REPEAT_MS = 45000;

enum PanelState { STATE_OFF, STATE_AMBER, STATE_RED };

String accessToken = "";
PanelState currentState = STATE_OFF;
unsigned long lastPollAt = 0;
unsigned long lastRedChimeAt = 0;
int oldestPendingAlertId = -1;

void login() {

    HTTPClient http;
    http.begin(String(API_BASE_URL) + "/login");
    http.addHeader("Content-Type", "application/json");

    StaticJsonDocument<128> body;
    body["username"] = DEVICE_USERNAME;
    body["password"] = DEVICE_PASSWORD;
    String payload;
    serializeJson(body, payload);

    int status = http.POST(payload);

    if (status == 200) {

        StaticJsonDocument<1024> response;
        deserializeJson(response, http.getString());
        accessToken = response["access_token"].as<String>();
    }

    http.end();
}

// Returns true on success; re-logs in once on a 401 (expired token) and
// retries, since these devices are meant to sit powered on indefinitely.
bool authedGet(const String &path, JsonDocument &out) {

    for (int attempt = 0; attempt < 2; attempt++) {

        HTTPClient http;
        http.begin(String(API_BASE_URL) + path);
        http.addHeader("Authorization", "Bearer " + accessToken);

        int status = http.GET();

        if (status == 200) {

            deserializeJson(out, http.getString());
            http.end();
            return true;
        }

        http.end();

        if (status == 401) {

            login();
            continue;
        }

        return false;
    }

    return false;
}

void acknowledgeAlert(int alertId) {

    HTTPClient http;
    http.begin(String(API_BASE_URL) + "/alerts/" + alertId + "/acknowledge");
    http.addHeader("Authorization", "Bearer " + accessToken);
    http.PATCH("");
    http.end();
}

void pollAlertState() {

    StaticJsonDocument<4096> alerts;

    if (authedGet("/alerts/pending", alerts) && alerts.size() > 0) {

        currentState = STATE_RED;
        oldestPendingAlertId = alerts[alerts.size() - 1]["id"].as<int>();
        return;
    }

    StaticJsonDocument<4096> guardPending;

    if (authedGet("/guard/pending", guardPending) &&
        guardPending["total_pending"].as<int>() > 0) {

        currentState = STATE_AMBER;
        return;
    }

    currentState = STATE_OFF;
}

// A slow fade in/out over ~2s — the "breathing" pulse from the UX design,
// deliberately not a hard blink.
void breathe(int pin) {

    for (int level = 0; level <= 255; level += 5) {

        analogWrite(pin, level);
        delay(20);
    }

    for (int level = 255; level >= 0; level -= 5) {

        analogWrite(pin, level);
        delay(20);
    }
}

void chimeSoft() {

    tone(PIN_BUZZER, 880, 150);
    delay(200);
    noTone(PIN_BUZZER);
}

void chimeUrgent() {

    tone(PIN_BUZZER, 880, 120);
    delay(160);
    tone(PIN_BUZZER, 1175, 120);
    delay(160);
    noTone(PIN_BUZZER);
}

void setup() {

    pinMode(PIN_LED_RED, OUTPUT);
    pinMode(PIN_LED_AMBER, OUTPUT);
    pinMode(PIN_BUZZER, OUTPUT);
    pinMode(PIN_BUTTON, INPUT_PULLUP);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    while (WiFi.status() != WL_CONNECTED) {

        delay(500);
    }

    login();
}

void loop() {

    unsigned long now = millis();

    if (now - lastPollAt >= POLL_INTERVAL_MS) {

        PanelState previousState = currentState;

        pollAlertState();

        if (currentState == STATE_AMBER && previousState == STATE_OFF) {

            chimeSoft();
        }

        if (currentState == STATE_RED && previousState != STATE_RED) {

            chimeUrgent();
            lastRedChimeAt = now;
        }

        lastPollAt = now;
    }

    if (currentState == STATE_RED &&
        now - lastRedChimeAt >= RED_CHIME_REPEAT_MS) {

        chimeUrgent();
        lastRedChimeAt = now;
    }

    if (currentState == STATE_RED && digitalRead(PIN_BUTTON) == LOW) {

        if (oldestPendingAlertId != -1) {

            acknowledgeAlert(oldestPendingAlertId);
            currentState = STATE_OFF;
        }

        delay(300); // crude debounce
    }

    switch (currentState) {

        case STATE_RED:
            analogWrite(PIN_LED_AMBER, 0);
            breathe(PIN_LED_RED);
            break;

        case STATE_AMBER:
            analogWrite(PIN_LED_RED, 0);
            breathe(PIN_LED_AMBER);
            break;

        case STATE_OFF:
            analogWrite(PIN_LED_RED, 0);
            analogWrite(PIN_LED_AMBER, 0);
            delay(200);
            break;
    }
}
