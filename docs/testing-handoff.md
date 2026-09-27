# Laptop and initial vehicle-test handoff

This handoff is for continuing the project in Codex on the laptop that will be physically connected to the car. The current application is laptop-hosted Python software; it is not an Android application.

## 1. Clone and open the project

Install Git and Python 3.12 or newer, then run:

```powershell
git clone https://github.com/885bryn/obdii-reader.git
cd obdii-reader
python --version
python -m unittest discover -s tests -v
```

All offline tests must pass before connecting the vehicle. Open Codex, choose this cloned folder as the local project, and start a task with:

> Read docs/STATUS.md, docs/PROJECT_HISTORY.md, README.md, docs/research.md, docs/safety.md, and docs/testing-handoff.md. Continue only the bounded, strictly read-only Supra ENET work described in the current status. Do not invent addresses, DIDs, scalers, or supported signals; do not expand vehicle testing beyond an explicitly reviewed procedure.

Official Codex documentation is available at https://developers.openai.com/learn/codex.

## 2. Prove the software offline

Start the simulated dashboard and recorder:

```powershell
python -m supra_telemetry demo --db demo-session.sqlite
```

Open the printed loopback URL, confirm five cards appear, then press `Ctrl+C`. Export the recording:

```powershell
python -m supra_telemetry export demo-session.sqlite demo-session.csv
```

The SQLite and CSV files are ignored by Git.

## 3. Prepare the stationary vehicle

1. Park outdoors in a safe, ventilated location.
2. Apply the parking brake. Use Park for an automatic or neutral with wheels chocked for a manual.
3. Keep the engine off and do not test while driving.
4. Connect the ENET cable to the vehicle's diagnostic port, then connect its Ethernet side to the laptop through the USB-C/Ethernet adapter.
5. Close ISTA, BimmerLink, coding tools, and anything else that could use the diagnostic connection.
6. Stop immediately if the vehicle shows an unexpected warning or changes state.

The initial bounded discovery succeeded with the engine off and did not require PAD/Diagnostics Mode. Do not infer from that result that a later diagnostic session uses the same state. Toyota bulletin T-SB-0062-22 documents three Start-Stop presses within 0.8 seconds to enter PAD/Diagnostics Mode for its specific 2023 Supra ISTA service procedure, together with a supported battery charger and voltage limits. Follow the exact applicable Toyota service procedure rather than generalizing that sequence or letting this project automate vehicle state.

## 4. Find the laptop's ENET address

In PowerShell:

```powershell
ipconfig
```

Locate the USB/Ethernet adapter connected to the car. A direct ENET connection commonly uses an IPv4 link-local address in `169.254.0.0/16`. Record the laptop-side address; do not assume the vehicle gateway address.

If no adapter appears or no link-local address is assigned, stop and inspect the cable, adapter, link state, and documented vehicle power state. Do not scan the network or add guessed static addresses.

## 5. Run discovery only

Create a private capture directory and substitute the laptop adapter's real address:

```powershell
New-Item -ItemType Directory -Force captures
python -m supra_telemetry discover --interface 169.254.x.x --json captures/discovery.json --redact-console
```

This sends bounded HSFZ and DoIP vehicle-identification discovery. It does not send an ECU diagnostic request or establish a diagnostic session. The complete capture remains in the private file while the console shows a redacted copy that is safer to share.

Optional gateway identity check:

```powershell
python -m supra_telemetry verify-gateway --capture captures/discovery.json
```

This validates one HSFZ response in the capture and binds the connection to its exact IPv4 link-local interface address; it uses only that interface, the captured peer, and parsed diagnostic address. If the captured interface address is no longer assigned, setup fails before a diagnostic request is sent. It sends one read-only UDS VIN request (22 F190) to TCP 6801, using tester address F4. The F4 convention is corroborated by community protocol evidence, not published by Toyota for this Supra. The tool prints only a small pass/fail result, stores no exchange, and fails on errors or any VIN mismatch. Success verifies gateway HSFZ identity routing only; it says nothing about the DME address or oil/coolant temperature and other signal/PID support. It does not scan, retry, start a diagnostic session, or send tester-present. Use a stable adapter and follow the stationary vehicle and battery-support guidance above.

After gateway identity routing has been verified, the optional DME identity check is:

```powershell
python -m supra_telemetry verify-dme --capture captures/discovery.json
```

It binds to the capture's exact local IPv4 link-local address and sends exactly one UDS VIN request (22 F190) to candidate DME target 0x12 at the captured peer on TCP 6801, using tester address F4. Target 0x12 and tester F4 are community-corroborated conventions; Toyota has not published them for this vehicle. Failure output includes only a fixed generic reason category; no exchange is saved. Success verifies only DME identity routing. It does not establish supported PIDs or coolant/oil temperature availability. It does not scan, retry, start a diagnostic session, send tester-present, or read live signals.

After the DME identity route has been verified, the bounded standard PID-support check is:

```powershell
python -m supra_telemetry verify-temperature-support --capture captures/discovery.json
```

It binds TCP to the capture's exact local interface address and uses the fixed candidate DME target 0x12 and tester F4. It reads SAE J1979 Mode 01 support bitmaps: PID 00 always, PID 20 only if PID 00 advertises continuation, and PID 40 only if PID 20 advertises continuation. It sends at most three requests on one client and stops on any error. It never requests PID 05 or PID 5C values. Output contains support booleans for coolant PID 05 and oil-temperature PID 5C plus request count, or a fixed generic failure reason. A support bit advertises ECU support according to the standard bitmap; it does not prove that a future value response is plausible, correctly scaled, or safe to poll.

The separately bounded common-DME support check is:

```powershell
python -m supra_telemetry verify-common-dme-support --capture captures/discovery.json
```

It uses the same source-bound, previously verified DME route and sends exactly one `01 00` bitmap request. It reports whether the DME advertises RPM PID 0C, vehicle speed PID 0D, intake-air-temperature PID 0F, and throttle-position PID 11, plus a conservative request count. It never requests those values, retries, scans, polls, changes session, sends tester-present, writes, actuates, or persists the exchange. The implementation passed 42 offline tests and independent review, but this check has not yet been run on the vehicle. A properly prepared Diagnostic/PAD Mode session may be used for this bounded information-gathering step, provided the vehicle state is recorded. That result does not establish normal-mode product behavior; every finished signal path must later pass a separate reviewed test with Diagnostic/PAD Mode off. Use the command only as a separately reviewed one-command action and stop after the result or on any warning or error.

Only if that check verifies both PIDs on this vehicle, the separate optional value check may be run:

```powershell
python -m supra_telemetry read-temperature-values --capture captures/discovery.json
```

This is a one-shot read, not polling. On one connection it attempts at most two application requests total: Mode 01 PID 05 exactly once, then Mode 01 PID 5C exactly once. If the first request fails, the second is not sent. It performs no bitmap repeats, retries, scans, tester-present traffic, session changes, fault clearing, routines, actuator/security requests, writes, or raw persistence. Only exact positive replies `41 05 xx` and `41 5C xx` are accepted, with each value decoded as raw byte minus 40 °C. Output omits vehicle identifiers and raw responses. `requests_sent` counts attempts conservatively and is an upper bound on possibly transmitted requests when a failure leaves transmission uncertain. Both values have since been read successfully with the engine running in normal mode without PAD/Diagnostic Mode.

The repeated monitor is available as `python -m supra_telemetry monitor-temperatures --capture captures/discovery.json`. It binds to the exact captured interface and uses the one-shot-verified route (tester F4, DME target 0x12, TCP 6801). Each cycle sends exactly `01 05`, then `01 5C`, with at least 2 seconds idle after the prior completed cycle. At the 300-second default duration it starts no more requests and closes the dashboard; an already-started request may finish or reach its bounded timeout before process cleanup finishes. A request failure halts traffic, closes the dashboard, and returns a failed command status; it does not retry or reconnect. The dashboard binds to loopback. Add `--db <path>` only to opt into sample logging; no raw exchanges or vehicle/network identifiers are stored. One 300-second run completed on 2026-09-26 in normal engine-running mode without PAD/Diagnostic Mode, logging off, clean exit, with no observed acquisition or recording error, at approximately 0.49–0.50 completed pairs per second. Five chronological coolant/oil checkpoint pairs were 77/78, 79/84, 82/88, 81/90, and 83/90 °C; these are samples at observed checkpoints, not run-wide extrema. This confirms only that bounded run. Longer duration and recording remain untested.

The capture may contain the VIN, MAC, EID, GID, IP address, or other vehicle identifiers. `captures/` is ignored by Git. Do not commit, publish, paste publicly, or attach an unredacted capture.

## 6. Continue in Codex

With the local capture still on the laptop, ask Codex:

> Inspect captures/discovery.json locally. Redact the VIN and network identifiers in anything shown to me. Determine whether HSFZ, DoIP, both, or neither responded. Do not initiate additional vehicle traffic unless the current status/task calls for it and the procedure has been reviewed. Update verified/inferred/unknown documentation using only available evidence.

Expected outcomes:

- An HSFZ response identifies a candidate gateway and preserves the raw discovery datagram for offline inspection.
- A DoIP announcement identifies a candidate DoIP gateway, but live DoIP routing is not implemented.
- No response is also useful evidence; inspect link state and vehicle preparation rather than scanning or guessing.

### Initial observed checkpoint

On 2026-09-24, a stationary, engine-off 2023 GR Supra returned one valid HSFZ identification response over an IPv4 link-local ENET connection. The same bounded attempt returned no DoIP announcement. Subsequent user-confirmed checks established gateway and DME identity routing, temperature PID support, and successful one-shot temperature reads. A single 300-second monitor run then completed on 2026-09-26 in normal engine-running mode without PAD/Diagnostic Mode. It ran with logging off, exited cleanly, showed no observed acquisition or recording error, and recorded approximate throughput of 0.49–0.50 completed pairs per second. Its five chronological coolant/oil checkpoint pairs were 77/78, 79/84, 82/88, 81/90, and 83/90 °C (checkpoint observations, not run-wide extrema). This does not establish longer-duration or recording behavior. Unique vehicle and network identifiers remain in the ignored local capture and must not be copied into tracked documentation.

## 7. Live polling gate

Do not run `python -m supra_telemetry run` with the supplied template. It is intentionally unverified and contains no enabled vehicle signals or ECU target addresses.

The generic profile-driven `run` path remains gated on the following:

- the observed transport and gateway address;
- a physically addressed ECU target from trustworthy evidence;
- one read-only request with known response length, formula, and units;
- independent plausibility checks for the returned value;
- a conservative initial request interval;
- a battery-support plan appropriate to the documented vehicle state and expected session duration;
- a rollback/stop procedure for unexpected responses or vehicle warnings.

The application then enforces one request at a time and halts the entire live acquisition after its first transport, protocol, negative-response, decoder, or recording error.
