# Research status

## Verified in this software

- The UDS/OBD response service mappings and SAE Mode 01 formulas implemented for RPM, speed, coolant temperature, intake-air temperature, and throttle position are protocol-level definitions, not evidence that a specific Supra ECU serves them.
- DoIP discovery framing follows ISO 13400's generic header structure; DoIP discovery does not establish a diagnostic route.
- HSFZ framing/control words and UDP 6811 identification request are implemented from community protocol research; packet fixtures test the software's encoding/parsing. These are not Toyota/OEM specifications and do not validate behavior on a Supra.
- DoIP discovery announcement parsing accepts protocol versions 0x02/0x03 with matching inverse byte, validates the ISO 13400 field structure/payload length, and uses one absolute deadline. It does not establish a diagnostic route.

## Verified by vehicle testing

- On 2026-09-24, with a stationary 2023 GR Supra, engine off, the USB Ethernet adapter established an IPv4 link-local connection and the application received one syntactically valid HSFZ vehicle-identification response to its bounded UDP 6811 request.
- The response contained the expected HSFZ identification marker and vehicle-specific identity fields. The peer address, VIN, MAC, and raw datagram remain only in the ignored local capture and are intentionally excluded from tracked documentation.
- The same bounded discovery attempt received no DoIP vehicle announcement. This records that attempt's result; it does not prove that the vehicle never supports DoIP in other states or configurations.
- On 2026-09-26, after a clean five-minute power-down, the user confirmed a charger-connected, PAD-active stationary setup. Host preflight showed the Ethernet adapter up at 100 Mbps with exactly one link-local address and AC USB selective suspend disabled. Fresh redacted discovery again found one HSFZ gateway and no DoIP announcement.
- A subsequent connection-only check to the discovered peer's conventional HSFZ TCP port 6801 succeeded and then closed without sending an application payload. This verifies TCP reachability only.
- `verify-gateway` and `verify-dme` each succeeded with one read-only VIN identity request in the clean session. The latter verifies DME identity routing through candidate target 0x12 on this vehicle; the address was community-derived before the vehicle result, not guessed from that result. Earlier failed connection and DME attempts remain historical evidence only and did not establish the route.
- `verify-temperature-support` reported coolant PID 05 and engine-oil-temperature PID 5C supported. A separate `read-temperature-values` one-shot read returned both values, including in normal engine-running mode without PAD/Diagnostic Mode.
- One `monitor-temperatures` run completed for 300 seconds on 2026-09-26 in normal engine-running mode without PAD/Diagnostic Mode. Logging was off; it exited cleanly with no observed acquisition or recording error. Approximate completed-pair rate was 0.49–0.50 per second. This verifies only that bounded run.
- Staged USB isolation left the Ethernet adapter healthy alone and with ENET, and the link remained up during the successful normal-mode read. The earlier Windows Code 43 / Port Reset Failed event is therefore classified as a laptop USB enumeration/reset incident, not evidence that PAD or a different vehicle protocol is required.

## Inferred

- The observed HSFZ identification response confirms an ENET/HSFZ discovery path on the tested vehicle. It does not establish that the responding peer accepts the application's TCP diagnostic framing or reveal ECU topology, target addresses, session needs, or supported data.
- Standard SAE PIDs are worth trying only after connection and ECU support are confirmed.

## Unknown / empirical

- Behavior beyond the single 300-second monitor run and monitor behavior with recording enabled.
- DME session requirements, battery-support limits, vehicle request limits beyond the observed bounded cadence, and HSFZ keep-alive requirements.
- Support and safe interpretation of signals beyond coolant PID 05 and engine-oil-temperature PID 5C; transmission/chassis signals remain unverified.
- DoIP routing and support. The bounded discovery attempt saw no DoIP announcement, and live DoIP routing is not implemented.

## References

- **Primary / manufacturer and standards context:** Toyota 2023 Supra PDS bulletin T-SB-0062-22 (Supra diagnostic cable and ISTA requirements; for its documented service procedure it specifies a supported battery charger and three Start-Stop presses within 0.8 seconds for PAD/Diagnostics Mode; it does not publish raw HSFZ tester/ECU addresses, telemetry requests, or signal support): https://static.nhtsa.gov/odi/tsbs/2022/MC-10217797-9999.pdf
- **Primary / standards body:** ISO 13400 overview: https://www.iso.org/standard/74751.html
- **Community implementation evidence:** rawenet HSFZ protocol notes and reported capture-derived format/discovery markers: https://github.com/rawmind0/rawenet/blob/master/docs/hsfz-protocol.md
- **Community implementation evidence:** klartext's BMW HSFZ tooling uses target 0x12 for DME access and reports testing on other BMW platforms, not this Supra: https://github.com/HadiCherkaoui/klartext
- **Independent community address mapping:** obd-gauge-cluster records BMW DME diagnostic address 0x12 from its cited implementation and vehicle evidence; this is not Toyota documentation or proof for this Supra: https://github.com/cheeseprince/obd-gauge-cluster/blob/main/docs/BMW-STATUS.md

The optional `verify-gateway` check binds its TCP socket to the exact local IPv4 address in the capture, uses tester address 0xF4 (a community-corroborated convention rather than Toyota-published Supra routing data), and sends one UDS VIN read (22 F190) to the single link-local peer and diagnostic address parsed from the user's private discovery capture. It requires an exact VIN match; a stale/unassigned local source causes connection setup to fail before request bytes are sent. This can confirm gateway HSFZ identity routing only. It does not reveal or verify the DME target address or any signal/PID support, including oil or coolant temperature.

The optional `verify-dme` check makes a distinct single VIN read through candidate target 0x12 with tester 0xF4, using the captured HSFZ peer and exact captured local source address. These routing values are community-corroborated and are not Toyota-published proof for this Supra. A match verifies DME identity routing only; it does not show which standard PIDs are supported or whether coolant/oil temperatures can be read.
- **Community implementation evidence:** Scapy BMW HSFZ parser and control constants: https://scapy.readthedocs.io/en/stable/api/scapy.contrib.automotive.bmw.hsfz.html
- **Community implementation evidence:** EdiabasLib configuration (conventional HSFZ diagnostic/control ports): https://github.com/uholeschak/ediabaslib/blob/master/docs/EdiabasLib.config_file.md
- **Community implementation:** udsoncan UDS implementation/docs: https://github.com/pylessard/python-udsoncan
- **Community implementation:** doipclient docs: https://python-doipclient.readthedocs.io/en/latest/
- **Standards implementer overview:** UDS background, Vector: https://www.vector.com/int/en/know-how/protocols/diagnostic-protocols/uds/
- Python socket documentation: https://docs.python.org/3/library/socket.html
- Python sqlite3 documentation: https://docs.python.org/3/library/sqlite3.html
- SAE J1979 standards landing page: https://www.sae.org/standards/content/j1979_202202/

These references provide protocol background only. Community HSFZ reports should be treated as provisional until independently corroborated. Toyota documentation confirms a Supra-specific diagnostic cable and Toyota ISTA requirement, not raw ENET host configuration, HSFZ addressing, ECU DIDs, or signal availability. The initial vehicle capture confirms only the bounded HSFZ identification exchange described above.

The Scapy parser specifically documents HSFZ control `0x12` with source/target for a two-byte body and an identification string when the body is longer. This implementation audits and skips these frames during reads; it does not infer a gateway response. Actual Supra gateway keep-alive behavior remains unknown.
