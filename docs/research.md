# Research status

## Verified in this software

- The UDS/OBD response service mappings and SAE Mode 01 formulas implemented for RPM, speed, coolant temperature, intake-air temperature, and throttle position are protocol-level definitions, not evidence that a specific Supra ECU serves them.
- DoIP discovery framing follows ISO 13400's generic header structure; DoIP discovery does not establish a diagnostic route.
- HSFZ framing/control words and UDP 6811 identification request are implemented from community protocol research; packet fixtures test the software's encoding/parsing. These are not Toyota/OEM specifications and do not validate behavior on a Supra.
- DoIP discovery announcement parsing accepts protocol versions 0x02/0x03 with matching inverse byte, validates the ISO 13400 field structure/payload length, and uses one absolute deadline. It does not establish a diagnostic route.
- The repository has not connected to or tested a 2023 GR Supra. Discovery announcements remain candidate evidence only.

## Inferred

- The A90/A91 Supra uses BMW-derived electronics, and an ENET-style Ethernet diagnostic route is plausible. Exact ECU topology, selected diagnostic protocol, gateway behavior, and supported data remain vehicle/version dependent.
- Standard SAE PIDs are worth trying only after connection and ECU support are confirmed.

## Unknown / empirical

- Whether the supplied adapter presents Ethernet to the host, link configuration, vehicle-side gateway address, Supra-specific HSFZ route semantics, session needs, module addresses, supported PIDs/DIDs, polling limits, and keep-alive requirements.
- Actual update rate and any transmission/chassis-specific data exposure.
- No real 2023 Supra has been tested here.

## References

- **Primary / manufacturer and standards context:** Toyota 2023 Supra PDS bulletin T-SB-0062-22 (diagnostic cable/software requirements; not telemetry/protocol details): https://static.nhtsa.gov/odi/tsbs/2022/MC-10217797-9999.pdf
- **Primary / standards body:** ISO 13400 overview: https://www.iso.org/standard/74751.html
- **Community implementation evidence:** rawenet HSFZ protocol notes and reported capture-derived format/discovery markers: https://github.com/rawmind0/rawenet/blob/master/docs/hsfz-protocol.md
- **Community implementation evidence:** Scapy BMW HSFZ parser and control constants: https://scapy.readthedocs.io/en/stable/api/scapy.contrib.automotive.bmw.hsfz.html
- **Community implementation evidence:** EdiabasLib configuration (conventional HSFZ diagnostic/control ports): https://github.com/uholeschak/ediabaslib/blob/master/docs/EdiabasLib.config_file.md
- **Community implementation:** udsoncan UDS implementation/docs: https://github.com/pylessard/python-udsoncan
- **Community implementation:** doipclient docs: https://python-doipclient.readthedocs.io/en/latest/
- **Standards implementer overview:** UDS background, Vector: https://www.vector.com/int/en/know-how/protocols/diagnostic-protocols/uds/
- Python socket documentation: https://docs.python.org/3/library/socket.html
- Python sqlite3 documentation: https://docs.python.org/3/library/sqlite3.html
- SAE J1979 standards landing page: https://www.sae.org/standards/content/j1979_202202/

These references provide protocol background only. Community HSFZ reports should be treated as provisional until independently corroborated. Toyota documentation confirms a Supra-specific diagnostic cable and Toyota ISTA requirement, not raw ENET host configuration, HSFZ addressing, ECU DIDs, or signal availability. No real 2023 Supra has been tested here.

The Scapy parser specifically documents HSFZ control `0x12` with source/target for a two-byte body and an identification string when the body is longer. This implementation audits and skips these frames during reads; it does not infer a gateway response. Actual Supra gateway keep-alive behavior remains unknown.
