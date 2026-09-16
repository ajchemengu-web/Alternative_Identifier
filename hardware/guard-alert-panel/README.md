# Guard alert panel (inactive)

An optional ambient light + sound indicator for the guard post — lets a
guard notice a pending alert without staring at a screen, without the
harshness of a strobe or a siren. Not required for anything else in this
system to work; safe to ignore until there's budget for the hardware.

## Status

**Not built, not flashed, not deployed.** `firmware.ino` is source code
only. No device exists yet.

## Behavior

- **Red, slow pulse** + a two-tone chime repeating every ~45s while
  unacknowledged — a `TARGET_ALERT` is pending (`GET /alerts/pending`
  non-empty).
- **Amber, slow pulse** + one soft chime when it first appears, otherwise
  silent — an unknown person is waiting on guard review (`GET
  /guard/pending`).
- **Off, silent** — nothing pending.
- **Button press while red** acknowledges the oldest pending alert
  (`PATCH /alerts/{id}/acknowledge`) — the same action and the same
  `alert_acknowledged` flag the web dashboard's own Acknowledge button
  uses.

Deliberately no strobing and no continuous alarm — see the design
reasoning in chat: urgency is conveyed by which color is lit and how
often the chime repeats, not by volume or harshness.

## Parts (rough, ~$10-15 total)

- Any ESP32 dev board (built-in WiFi)
- 2x LED (red, amber) + resistors, or one addressable RGB LED
- 1x small piezo buzzer
- 1x momentary push button
- Breadboard/wires, or a small enclosure once wiring is finalized

## Setup, whenever hardware exists

1. Install the Arduino ESP32 board package + the `ArduinoJson` library.
2. Fill in `WIFI_SSID`, `WIFI_PASSWORD`, `API_BASE_URL` in
   `firmware.ino`.
3. Create a **dedicated SECURITY-tier admin account** for this device
   (not a real person's login) — `/alerts/pending` and its acknowledge
   endpoint require `admin_tier` `SECURITY` or `ORIGINAL`; a
   SECURITY-tier account also satisfies `/guard/pending`'s
   `role=ADMIN`/`GUARD` check, so one account covers both endpoints.
   Set `DEVICE_USERNAME`/`DEVICE_PASSWORD` to that account.
4. Wire per the pin constants at the top of `firmware.ino` (adjust if
   the actual build differs).
5. Flash, power on.

Never commit real WiFi or device credentials into this file — those
four `CHANGEME` placeholders stay placeholders in git; fill them in
only on the physical device itself.
