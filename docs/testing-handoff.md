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

> Read README.md, docs/research.md, docs/safety.md, and docs/testing-handoff.md. Continue the strictly read-only Supra ENET validation. Do not invent addresses, DIDs, scalers, or supported signals. Do not enable live polling until the captured transport and every configured request have been reviewed.

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

Follow Toyota service information for the correct ignition/PAD state for the exact market and model year. The project must not guess or automate that state.

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
python -m supra_telemetry discover --interface 169.254.x.x --json captures/discovery.json
```

This sends bounded HSFZ and DoIP vehicle-identification discovery. It does not send an ECU diagnostic request or establish a diagnostic session.

The capture may contain the VIN, MAC, EID, GID, IP address, or other vehicle identifiers. `captures/` is ignored by Git. Do not commit, publish, paste publicly, or attach an unredacted capture.

## 6. Continue in Codex

With the local capture still on the laptop, ask Codex:

> Inspect captures/discovery.json locally. Redact the VIN and network identifiers in anything shown to me. Determine whether HSFZ, DoIP, both, or neither responded. Do not send new vehicle traffic and do not enable live polling. Update the verified/inferred/unknown documentation using only the captured evidence.

Expected outcomes:

- An HSFZ response identifies a candidate gateway and preserves the raw discovery datagram for offline inspection.
- A DoIP announcement identifies a candidate DoIP gateway, but live DoIP routing is not implemented.
- No response is also useful evidence; inspect link state and vehicle preparation rather than scanning or guessing.

## 7. Live polling gate

Do not run `python -m supra_telemetry run` with the supplied template. It is intentionally unverified and contains no enabled vehicle signals or ECU target addresses.

Live polling can begin only after all of the following are documented:

- the observed transport and gateway address;
- a physically addressed ECU target from trustworthy evidence;
- one read-only request with known response length, formula, and units;
- independent plausibility checks for the returned value;
- a conservative initial request interval;
- a rollback/stop procedure for unexpected responses or vehicle warnings.

The application then enforces one request at a time and halts the entire live acquisition after its first transport, protocol, negative-response, decoder, or recording error.
