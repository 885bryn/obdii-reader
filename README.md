# Supra Telemetry

An experimental, standard-library-first, strictly read-only telemetry platform for the 2023 Toyota GR Supra and its wired ENET connection. The initial release includes a simulated dashboard and a fail-closed HSFZ polling path for explicitly verified profiles. A stationary, engine-off 2023 Supra has answered bounded HSFZ discovery and a single gateway VIN identity read; no DME route or live signal read has been vehicle-validated.

## Start the demo

Python 3.12 or newer, no install required:

```powershell
python -m supra_telemetry --help
python -m supra_telemetry demo --db session.sqlite
```

Open the printed loopback URL in a browser. Press Ctrl+C to stop. The demo values are synthetic. `export session.sqlite samples.csv` exports recorded samples.

`discover --interface <local-IPv4>` sends the HSFZ vehicle-identification datagram to the ENET link-local broadcast on UDP 6811 and a DoIP vehicle-identification broadcast. It does not establish diagnostic sessions or send ECU diagnostic requests. Results are candidates, not proof that live telemetry works. The broadcast can be overridden for a known interface subnet; the program does not scan addresses. Use `--redact-console` when saving a private JSON capture so terminal output can be shared without exposing vehicle or network identifiers.

`verify-gateway --capture captures/discovery.json` validates one unambiguous HSFZ discovery response and sends exactly one UDS ReadDataByIdentifier request for VIN (22 F190) to its captured diagnostic address over TCP 6801, binding the client socket to the capture's exact local interface address. If that address is no longer assigned, connection setup fails before a diagnostic request is sent. It uses tester address F4, a community-corroborated convention that Toyota has not published for this vehicle. Output contains only pass/fail status. Success verifies gateway HSFZ identity routing only; it does not establish DME addressing or support for oil temperature, coolant temperature, or any other signal. The check does not save raw exchanges.

`verify-dme --capture captures/discovery.json` performs a separate single VIN read (22 F190) to candidate DME target 0x12, using the capture's peer and exact local interface binding, with tester address F4. Both routing values are community-corroborated and are not Toyota-published proof for this vehicle. Failure output uses only fixed generic reason categories; no exchange is saved. Success verifies DME identity routing only; it does not establish support for coolant/oil temperature or any other PID.

`verify-temperature-support --capture captures/discovery.json` sends at most three conditional SAE J1979 Mode 01 supported-PID bitmap reads (01 00, then 01 20 and 01 40 only when each preceding bitmap advertises continuation) through the already-verified candidate DME route. It never requests PID 05 or 5C values. The result reports whether the bitmaps advertise coolant PID 05 and engine-oil-temperature PID 5C. SAE PID definitions establish what these requests mean; they do not prove this Supra's ECU support or a plausible temperature value. The check source-binds to the exact interface in the private capture, stores no raw exchange, and returns generic failure categories.

`run --profile <verified.json> --host <discovered-gateway-ip> --db <session.sqlite>` supports explicitly profiled HSFZ reads through a single serialized persistent connection per ECU target. A live profile must be marked verified and specify tester address, target address, request, service, and response decoder for every enabled measured signal. The supplied Supra template remains unverified with no vehicle addresses or enabled signals; it cannot be used for live polling until those facts are established safely.

Live acquisition halts on its first transport, protocol, negative-response, or decoder error. It closes connections, records explicit halted/unavailable samples without requesting remaining signals, and requires a fresh process after the cause has been inspected. Dashboard and CSV rates are measured from monotonic timestamps; first readings have no observed rate.

HSFZ framing and discovery are based on public Scapy and community `rawenet` protocol documentation and fixtures. Those sources do not verify the 2023 Supra's actual ECU addresses, data identifiers, network setup, or supported signals. The transport path is therefore a framework for explicit verified configuration, not confirmation that a 2023 Supra will respond.

## Project notes

Before moving to the laptop or connecting the vehicle, follow the [initial testing handoff](docs/testing-handoff.md). See [architecture](docs/architecture.md), [research](docs/research.md), [safety](docs/safety.md), [signals](docs/signals.md), and [roadmap](docs/roadmap.md). Run offline checks with `python -m unittest discover -s tests`.
