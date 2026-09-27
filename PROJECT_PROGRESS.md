# Project progress

Last updated: 2026-09-26

## Source of truth

This file is the cross-computer summary of verified project milestones and the next safe checkpoint. Update it from evidence in the current checkout and the user's reported vehicle results. `docs/roadmap.md` remains the implementation roadmap; `docs/research.md`, `docs/safety.md`, and `docs/testing-handoff.md` retain technical evidence and procedures. When records disagree, preserve the narrower claim and resolve it against the underlying evidence before marking a milestone complete.

## Status legend

- **DONE** — supported by recorded test results or an explicitly identified user-reported vehicle result.
- **PARTIAL** — some evidence exists, but an important part remains unverified.
- **READY FOR CONTROLLED VEHICLE TEST** — implementation, offline checks, and review are complete; the bounded vehicle test has not yet been run.
- **NEXT** — planned checkpoint; not yet performed.
- **BLOCKED** — cannot proceed safely until the stated evidence or decision is available.

## Major milestones

| Status | Milestone | Evidence / boundary | Completed |
| --- | --- | --- | --- |
| DONE | Offline protocol and safety tests | 19 offline unit tests passed; software fixtures only, no car traffic. | 2026-09-24 |
| DONE | Link and HSFZ discovery | On 2026-09-26, after a clean five-minute power-down, user confirmed parked, engine off, charger connected, ENET attached, and PAD/Diagnostics Mode active. Host preflight showed adapter Up at 100 Mbps, one link-local address, and AC USB selective suspend disabled. Fresh redacted discovery found one HSFZ gateway and no DoIP. | 2026-09-26 |
| DONE | Gateway identity routing | `verify-gateway` succeeded in the clean session with one read-only UDS 22 F190 identity request. | 2026-09-26 |
| DONE | Engine ECU (DME) identity routing | `verify-dme` succeeded in the clean session with one read-only UDS 22 F190 identity request to candidate target 0x12. That address was community-derived before this vehicle result; this exact successful identity match now verifies the route for this vehicle. | 2026-09-26 |
| DONE / VERIFIED | DME temperature support bitmap | On 2026-09-26, one fresh redacted discovery found one HSFZ gateway. Exactly one `verify-temperature-support` run returned verified: coolant PID 05 supported true and engine-oil PID 5C supported true; `requests_sent: 3`. Communication stopped afterward. | 2026-09-26 |
| DONE / VERIFIED | One-shot coolant and oil-temperature values | On 2026-09-26, one fresh redacted discovery found one HSFZ gateway. Exactly one `read-temperature-values` run returned verified: coolant 26 °C, engine oil 25 °C, `requests_sent: 2`. Values were mutually plausible for a parked, engine-off vehicle near ambient. Communication stopped immediately afterward. | 2026-09-26 |
| DONE / VERIFIED | Normal-mode telemetry without Diagnostics/PAD | On 2026-09-26, staged USB isolation showed the Realtek adapter OK alone and with ENET. With OBD connected/car off, link was Up at 100 Mbps with one link-local IPv4. After normal engine start with PAD off, USB remained OK/link Up; fresh redacted discovery found one HSFZ gateway, and exactly one `read-temperature-values` run returned verified: coolant 65 °C, engine oil 64 °C, `requests_sent: 2`. Values rose plausibly from the prior engine-off 26 °C/25 °C. Communication stopped immediately. | 2026-09-26 |
| READY FOR CONTROLLED VEHICLE TEST | Conservative periodic temperature monitoring | On 2026-09-26, `monitor-temperatures` implemented and independently reviewed through final request-gate repair; 39 offline tests pass, and diff/privacy checks pass. Not yet run on the car. | 2026-09-26 |

## Current safe checkpoint

On 2026-09-26, following a clean five-minute power-down, the user confirmed the vehicle was parked with engine off, charger connected, ENET attached, and PAD/Diagnostics Mode active. Host preflight confirmed the Ethernet adapter Up at 100 Mbps, exactly one link-local address, and AC USB selective suspend disabled. Fresh redacted discovery found one HSFZ gateway and no DoIP. The source-bound TCP connection-only check to the captured peer on port 6801 succeeded without diagnostic payload. `verify-gateway` succeeded with one read-only UDS 22 F190 identity request, and `verify-dme` succeeded with one read-only UDS 22 F190 request to candidate target 0x12. The 0x12 address had been community-derived before this exact successful vehicle result, which verifies DME identity routing on this car. The bounded DME temperature support bitmap checker was implemented, independently reviewed, privacy-scanned, and passed 20 offline tests. In its controlled vehicle test, one fresh redacted discovery found one HSFZ gateway, then exactly one `verify-temperature-support` run returned verified with coolant PID 05 supported true and engine-oil PID 5C supported true (`requests_sent: 3`). Communication stopped immediately afterward. The bounded one-shot temperature value reader was implemented and independently re-reviewed after a conservative audit-count repair; all 22 offline tests pass, and privacy and diff checks pass. In its engine-off PAD test, one fresh redacted discovery found one HSFZ gateway, then exactly one `read-temperature-values` run returned verified with coolant 26 °C and engine oil 25 °C (`requests_sent: 2`), plausible near ambient. After staged USB isolation (adapter OK alone, OK with ENET, and link Up at 100 Mbps with one link-local IPv4 when OBD was connected/car off), a normal engine-running test with PAD off kept USB OK/link Up. Fresh redacted discovery found one HSFZ gateway; exactly one `read-temperature-values` run returned verified with coolant 65 °C and engine oil 64 °C (`requests_sent: 2`). These values rose plausibly from the prior engine-off readings. Communication stopped immediately. Thus normal-mode read-only temperature telemetry without PAD is verified for this one-shot test. The earlier Code 43 event is classified as a laptop USB enumeration/reset issue, not evidence of a PAD or vehicle-protocol requirement. The reader uses one DME connection, requests `01 05` at most once followed by `01 5C` at most once, stops on first failure, counts requests conservatively, and closes the socket. It does not retry, poll, scan, write, change sessions, send tester-present/security/fault-clear/routine/actuator commands, or persist raw exchanges. No writes or vehicle-state changes were commanded, and no retries, polling, support rechecks, session changes, tester-present, security, fault clears, routines, actuator commands, or raw persistence occurred during either value test. Earlier failed connection and DME attempts remain historical evidence only; clean-session results establish the route. The `monitor-temperatures` command has since been implemented and reviewed but has not yet been vehicle-tested. The oil-temperature decoder is implemented and its profile entry remains disabled/unverified.

The `monitor-temperatures` command is implemented and independently reviewed through its final request-gate repair. Its 39 offline tests pass; diff and privacy checks pass. It is ready for a controlled vehicle test but has not been run on the car. It operates in normal engine-running mode without PAD, validates the capture strictly, and binds to the exact captured interface. It uses captured peer TCP 6801, tester F4, and DME target 0x12; it requests only PID 05 followed by PID 5C, with at least two seconds idle after a completed pair and a maximum 300-second request window. A stop intent/request gate prevents new requests if stop wins; an already authorized active request may complete. The first independent error halts the run. It has no retry, reconnect, scan, support recheck, tester-present, session/security request, fault clear, routine, actuator command, or write. It serves a loopback dashboard; optional SQLite stores decoded samples only. Raw exchanges and identifiers are never stored.

## Next action

Reconnect ENET and, with the vehicle stationary in normal engine-running mode and PAD off, run `monitor-temperatures` for five minutes with logging off initially. Observe the dashboard and whether both readings remain plausible; stop immediately on any vehicle warning or command error, then review the outcome. This is the first vehicle test of the periodic monitor. Normal runtime must not require PAD, which remains reserved for coding or engine-off service/testing.

## Blockers and unknowns

- Toyota has not published the Supra's HSFZ addressing in the tracked evidence. Candidate DME target 0x12 was community-derived before the successful clean-session identity result; `verify-dme` success now establishes identity routing to that target on this vehicle.
- Coolant PID 05 and engine-oil PID 5C are supported according to the bitmap check; the one-shot readings were 26 °C and 25 °C, plausible near ambient while parked and engine-off. This does not validate periodic behavior or a safe live update rate.
- Read-only coolant and engine-oil telemetry in normal engine-running mode without Diagnostics/PAD is verified for one one-shot read: 65 °C coolant and 64 °C engine oil, plausibly above the engine-off 26 °C/25 °C readings. PAD is reserved for coding or engine-off service/testing, not normal runtime. The earlier Code 43/Port Reset Failed event is a laptop USB enumeration/reset issue; the later staged isolation and successful normal-mode read resolved that validation gap.
- Session requirements beyond the tested PAD state, battery-support duration, periodic request limits, and live update rate remain unverified.
- No DoIP announcement was seen in the fresh discovery; DoIP routing is not implemented.
- `monitor-temperatures` is implemented, reviewed, and passes 39 offline tests, but has not been vehicle-tested. Its bounded five-minute normal-mode test with logging off is the next checkpoint; sustained rates/plausibility remain unverified.

The successful identity checks each sent one read-only 22 F190 request. The support checker completed with `requests_sent: 3`; each one-shot temperature value run completed with `requests_sent: 2`. Communication stopped immediately after each bounded check. Across the value tests there were no writes or commanded state changes, retries, polling, scans, support rechecks, session changes, tester-present, security requests, fault clears, routines, actuator commands, or raw persistence.

Vehicle safety constraint: never write to the vehicle or otherwise change vehicle state through this project. Keep all vehicle communication read-only.

## Privacy rule

Never put VIN, MAC, EID, GID, IP/interface addresses, raw packet bytes, or unredacted capture contents in this tracker, any tracked documentation, commit message, or public report. Keep full captures local and ignored by Git. Record only redacted outcomes and the evidence category.

## Two-computer sync routine

1. Before work on either computer, pull the shared branch and read this tracker plus the relevant roadmap, research, safety, and handoff notes. Resolve tracker conflicts against evidence; do not overwrite the other computer's progress.
2. After a major step, record its status, date, and concise evidence here. Distinguish code/test results from user-reported vehicle results; code written alone is not completion evidence.
3. Verify the change or result, inspect the final diff for private identifiers, then commit and push the tracker with related work. On the other computer, pull before continuing.
