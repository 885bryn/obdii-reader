# Supra Telemetry

An experimental, standard-library-first, strictly read-only telemetry platform for the 2023 Toyota GR Supra and its wired ENET connection. The initial release includes a simulated dashboard and a fail-closed HSFZ polling path for explicitly verified profiles. **No real 2023 Supra has been tested.**

## Start the demo

Python 3.12 or newer, no install required:

```powershell
python -m supra_telemetry --help
python -m supra_telemetry demo --db session.sqlite
```

Open the printed loopback URL in a browser. Press Ctrl+C to stop. The demo values are synthetic. `export session.sqlite samples.csv` exports recorded samples.

`discover --interface <local-IPv4>` sends the HSFZ vehicle-identification datagram to the ENET link-local broadcast on UDP 6811 and a DoIP vehicle-identification broadcast. It does not establish diagnostic sessions or send ECU diagnostic requests. Results are candidates, not proof that live telemetry works. The broadcast can be overridden for a known interface subnet; the program does not scan addresses.

`run --profile <verified.json> --host <discovered-gateway-ip> --db <session.sqlite>` supports explicitly profiled HSFZ reads through a single serialized persistent connection per ECU target. A live profile must be marked verified and specify tester address, target address, request, service, and response decoder for every enabled measured signal. The supplied Supra template remains unverified with no vehicle addresses or enabled signals; it cannot be used for live polling until those facts are established safely.

Live acquisition halts on its first transport, protocol, negative-response, or decoder error. It closes connections, records explicit halted/unavailable samples without requesting remaining signals, and requires a fresh process after the cause has been inspected. Dashboard and CSV rates are measured from monotonic timestamps; first readings have no observed rate.

HSFZ framing and discovery are based on public Scapy and community `rawenet` protocol documentation and fixtures. Those sources do not verify the 2023 Supra's actual ECU addresses, data identifiers, network setup, or supported signals. The transport path is therefore a framework for explicit verified configuration, not confirmation that a 2023 Supra will respond.

## Project notes

See [architecture](docs/architecture.md), [research](docs/research.md), [safety](docs/safety.md), [signals](docs/signals.md), and [roadmap](docs/roadmap.md). Run offline checks with `python -m unittest discover -s tests`.
