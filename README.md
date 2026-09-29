# Supra Telemetry

An experimental, standard-library-first, strictly read-only telemetry platform for the 2023 Toyota GR Supra and its wired ENET connection. A stationary 2023 Supra has answered bounded HSFZ discovery, gateway and DME identity checks, temperature and common-signal PID support checks, and one-shot temperature and common-DME value reads in normal engine-running mode without PAD/Diagnostic Mode. A single bounded 300-second normal-mode temperature monitor run completed successfully with logging off. Separate 60-second stationary and moving decoded-only recording sessions passed private database review. A 300-second moving recording run completed with application, database, privacy, error, and other audit checks passing; it exceeded the former procedure's test-specific 30 km/h ceiling. The user selected ordinary lawful driving as the target condition and accepted skipping another staged duration. Independent review approved exactly one 30-minute normal-driving procedure; current authorization is defined in `docs/safety.md`.

## Start the demo

Python 3.12 or newer, no install required:

```powershell
python -m supra_telemetry --help
python -m supra_telemetry demo --db session.sqlite
```

Open the printed loopback URL in a browser. Press Ctrl+C to stop. The demo values are synthetic. `export session.sqlite samples.csv` exports recorded samples.

`discover --interface <local-IPv4>` sends the HSFZ vehicle-identification datagram to the ENET link-local broadcast on UDP 6811 and a DoIP vehicle-identification broadcast. It does not establish diagnostic sessions or send ECU diagnostic requests. Results are candidates, not proof that live telemetry works. The broadcast can be overridden for a known interface subnet; the program does not scan addresses. Use `--redact-console` when saving a private JSON capture so terminal output can be shared without exposing vehicle or network identifiers.

## Client dashboard

The client dashboard has matching simulated and live presentation modes. Simulated
mode opens no vehicle connection and is the safe presentation fallback:

```powershell
python -m supra_telemetry client-dashboard --mode simulated --duration 300
```

It gives coolant and engine-oil temperature the two largest displays, with RPM,
vehicle speed, intake-air temperature, and throttle position as supporting
telemetry. The outstanding-fault-code snapshot keeps each code visible and adds
an allowlisted plain-English description when one has been source-verified;
unknown or manufacturer-specific codes are never guessed. RPM updates about five
times per second in simulated mode while the supporting values update about once
per second.

The presentation is a Vite-built React application under `frontend/`. Its built
assets are checked into `supra_telemetry/dashboard_static` so the installed
Python runtime remains dependency-free. Rebuild after frontend changes with
`npm ci` and `npm run build` from `frontend/`.

Live mode first takes one fixed Mode 03/07/0A fault snapshot, then uses only the
six already verified Mode 01 PIDs on the capture-bound DME route. One bounded
normal-mode run of the original one-request-per-second schedule completed on the
vehicle. The current faster candidate is offline-only: a 100 ms scheduler targets
RPM every 0.5 seconds, throttle every second, and the other four values every two
seconds. It remains bounded to 300 seconds and at most five monitoring attempts
per selected second (1,500 at 300 seconds). The
dashboard is loopback-only, records no raw exchanges, exposes no fault-clear or
vehicle-control action, and stops on the first monitoring error. The faster
candidate has not run on the vehicle and is not currently authorized; see
[docs/safety.md](docs/safety.md).

`verify-gateway --capture captures/discovery.json` validates one unambiguous HSFZ discovery response and sends exactly one UDS ReadDataByIdentifier request for VIN (22 F190) to its captured diagnostic address over TCP 6801, binding the client socket to the capture's exact local interface address. If that address is no longer assigned, connection setup fails before a diagnostic request is sent. It uses tester address F4, a community-corroborated convention that Toyota has not published for this vehicle. Output contains only pass/fail status. Success verifies gateway HSFZ identity routing only; it does not establish DME addressing or support for oil temperature, coolant temperature, or any other signal. The check does not save raw exchanges.

`verify-dme --capture captures/discovery.json` performs a separate single VIN read (22 F190) to candidate DME target 0x12, using the capture's peer and exact local interface binding, with tester address F4. Both routing values are community-corroborated and are not Toyota-published proof for this vehicle. Failure output uses only fixed generic reason categories; no exchange is saved. Success verifies DME identity routing only; it does not establish support for coolant/oil temperature or any other PID.

`verify-temperature-support --capture captures/discovery.json` sends at most three conditional SAE J1979 Mode 01 supported-PID bitmap reads (01 00, then 01 20 and 01 40 only when each preceding bitmap advertises continuation) through the already-verified candidate DME route. It never requests PID 05 or 5C values. The result reports whether the bitmaps advertise coolant PID 05 and engine-oil-temperature PID 5C. SAE PID definitions establish what these requests mean; they do not prove this Supra's ECU support or a plausible temperature value. The check source-binds to the exact interface in the private capture, stores no raw exchange, and returns generic failure categories.

`verify-common-dme-support --capture captures/discovery.json` makes exactly one source-bound Mode 01 PID 00 support-bitmap request through the verified DME route. It reports whether the bitmap advertises engine RPM PID 0C, vehicle speed PID 0D, intake-air-temperature PID 0F, and throttle-position PID 11. It does not request any of those values, retry, scan, poll, persist an exchange, or change vehicle state. The implementation is offline-tested and independently reviewed. One stationary, engine-off, PAD-off run on 2026-09-27 completed successfully and reported all four candidate PIDs supported. A later bounded run accepted one value response for each PID and passed its stationary gate; repeated acquisition remains unverified.

`inventory-mode01-support`, `read-common-dme-values`, `read-emissions-dtcs`, and `verify-vehicle-info` are fixed, source-bound discovery commands for the verified DME route. The inventory conditionally reads at most eight standard support bitmaps; the value command reads PIDs 0C/0D/0F/11 once each; the fault command reads confirmed, pending, and permanent emissions DTCs with Modes 03/07/0A once each; and the Mode 09 command requests its support bitmap and only advertised VIN, calibration-ID, CVN, and ECU-name types. Vehicle-information output is redacted: VIN is comparison-only, other identifiers are summarized by response presence and payload length, and no raw exchange is persisted. The DTC reader requires an explicit count-prefixed response on this route, validates the count and trailing zero padding, and never guesses the framing from length. One bounded vehicle run verified that framing for stored and pending reads; its permanent read was rejected. Future failures expose only allowlisted rejection categories, never raw replies or numeric response codes.

`compare-pad-emissions-dtcs --capture captures/discovery.json --confirm-manual-pad` is the dedicated, manually gated PAD/Diagnostic Mode comparison. It reuses the same fixed three-read DTC path and adds no traffic, session change, retry, or vehicle-state automation. The confirmation flag records only that the operator followed the reviewed manual procedure; it does not place the vehicle in PAD mode. Its one authorized run returned `P0420` for stored and pending and rejected the permanent Mode 0A read as `service-not-supported`, then stopped after three reported attempts. The comparison must not be repeated; current authorization is defined only in [docs/safety.md](docs/safety.md).

`collect-read-only-suite --capture captures/discovery.json` runs those four phases in that order, with a two-second stop window between successful phases, a total ceiling of 20 requests, and no later phase after the first failure. It performs no retry, address scan, polling, session change, clear/reset, control, write, or raw persistence. Two bounded vehicle runs on 2026-09-27 stopped fail-closed during DTC reading; the second preserved safe stored/pending results and stopped when the permanent read was rejected after a conservative total of 13 requests. Failure output preserves strictly allowlisted summaries of completed phases and earlier decoded DTC reads without exposing raw responses or identifiers.

`read-temperature-values --capture captures/discovery.json` is a bounded one-shot read. It attempts exactly one coolant request (01 05), then exactly one engine-oil-temperature request (01 5C) on the same DME connection; failure of the first stops the sequence. Values are decoded as the SAE raw byte minus 40 °C. Both temperatures have been returned in normal engine-running mode without PAD/Diagnostic Mode. This one-shot result is distinct from the bounded repeated-monitor test below.

`monitor-temperatures --capture captures/discovery.json` opens the existing loopback dashboard and reads exactly PID 05 then PID 5C once per cycle, with at least a 2-second idle gap after each completed cycle. After at most 300 seconds by default, it starts no new requests and closes the dashboard; a request already in flight may finish or reach its bounded timeout before process cleanup completes. The first request/response failure also shuts down the dashboard and returns failure; there are no retries. The capture selects one validated peer and exact local interface binding; tester F4, DME target 0x12, and TCP 6801 are fixed. No raw request option is exposed. SQLite logging is off unless `--db` is supplied; even then only temperature samples and non-identifying signal metadata are stored, never raw exchanges or capture identifiers. One 300-second normal engine-running/PAD-off vehicle run completed on 2026-09-26 with logging off, clean exit, no observed acquisition or recording error, and an approximate completed-pair rate of 0.49–0.50 per second. This establishes only that bounded run; longer duration and recording remain untested.

`monitor-common-dme --capture captures/discovery.json` is the offline-reviewed stationary monitor for RPM, speed, intake-air temperature, and throttle. It sends the four fixed Mode 01 requests in order, spaces every request start by at least one second, caps attempts at the selected 1–300 second duration, applies the stationary bounds to every value, and halts without retry on the first error. Its dashboard is loopback-only. Optional SQLite recording and CSV export contain decoded samples and non-identifying definitions only. This command has not run on the vehicle and is limited to the reviewed consolidated procedure in [docs/safety.md](docs/safety.md).

`drive-session --capture <private-capture.json> --db <new-session.sqlite> --confirm-hands-off` runs a finite, offline-capable loopback dashboard and decoded-only SQLite recording for up to 30 minutes (default 1800 seconds; `--duration` may be 1–1800). It uses the fixed verified capture-bound DME route and the existing six Mode 01 reads; it makes no DTC request, retry, scan, or raw exchange recording. The database path must not already exist, and the tool works without internet or Codex once started. The one-time 60-second stationary and moving recording gates passed. The 300-second moving run completed with the application and non-speed audit gates passing, but exceeded that procedure's former 30 km/h speed ceiling. Independent review now authorizes exactly one 30-minute procedure for ordinary lawful driving without a test-specific speed ceiling; no retry is authorized. See [docs/safety.md](docs/safety.md).

`run --profile <verified.json> --host <discovered-gateway-ip> --db <session.sqlite>` supports explicitly profiled HSFZ reads through a single serialized persistent connection per ECU target. A live profile must be marked verified and specify tester address, target address, request, service, and response decoder for every enabled measured signal. The supplied Supra template remains unverified with no vehicle addresses or enabled signals; it cannot be used for live polling until those facts are established safely.

Live acquisition halts on its first transport, protocol, negative-response, or decoder error. It closes connections, records explicit halted/unavailable samples without requesting remaining signals, and requires a fresh process after the cause has been inspected. Dashboard and CSV rates are measured from monotonic timestamps; first readings have no observed rate.

HSFZ framing and discovery are based on public Scapy and community `rawenet` protocol documentation and fixtures. Those sources do not verify the 2023 Supra's actual ECU addresses, data identifiers, network setup, or supported signals. The transport path is therefore a framework for explicit verified configuration, not confirmation that a 2023 Supra will respond.

## Project notes

Before moving to the laptop or connecting the vehicle, read [current status](docs/STATUS.md), [project history](docs/PROJECT_HISTORY.md), and the [initial testing handoff](docs/testing-handoff.md). For task-specific detail, see [architecture](docs/architecture.md), [research](docs/research.md), [safety](docs/safety.md), [signals](docs/signals.md), and [roadmap](docs/roadmap.md). Run offline checks with `python -m unittest discover -s tests`.
