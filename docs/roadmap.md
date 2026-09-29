# Future roadmap and risks

Current project state is in [STATUS.md](STATUS.md); completed verified milestones are in [PROJECT_HISTORY.md](PROJECT_HISTORY.md). This file contains future work only.

## Major goal: read-only BimmerLink parity

Reproduce the useful diagnostic and monitoring capabilities of BimmerLink for this Supra while permanently excluding every operation that clears, resets, registers, codes, actuates, or otherwise changes vehicle or ECU state. Read-only still creates diagnostic traffic, so every new route and request must remain evidence-backed, bounded, reviewed, and fail-closed. Manually entered Diagnostic/PAD Mode may be used for bounded read-only research and discovery when the vehicle procedure requires it, but it is not product acceptance evidence. Every finished capability must also work and be verified in the intended normal vehicle mode with Diagnostic/PAD Mode off.

### Ordered delivery

1. **M009 — Common DME live sensors.** The DME has advertised support for engine RPM, vehicle speed, intake-air temperature, and throttle position, and one stationary engine-idling suite run accepted all four one-shot responses. A client dashboard combines those four values with the previously verified coolant and oil temperatures, a one-shot emissions-DTC snapshot, and a matching no-I/O simulated mode. One stationary 300-second normal-mode run of the original one-request-per-second dashboard completed without an application-reported acquisition error. The faster cadence targets 0.5-second RPM, one-second throttle, and two-second supporting values with a serialized 100 ms slot scheduler, a rolling five-starts-per-second limit, and stop-on-first-error behavior; one separately reviewed 30-second stationary run completed. The 60-second stationary and low-speed moving recording gates passed. A reviewed 300-second moving run completed at the application level but failed its private post-run 30-km/h speed ceiling, ending the candidate under its no-retry rule. Boost and further DME values follow only when their request, formula, support, and safe cadence are established.
2. **M010 — Read-only fault diagnostics.** A bounded normal-mode phase verified strict count-prefixed parsing for stored and pending reads: stored was empty and pending returned `P0420`; the permanent Mode 0A read was rejected before sanitized subtypes existed. The one approved PAD-on comparison later returned `P0420` for both stored and pending and rejected the permanent read as `service-not-supported`. That single comparison did not make Mode 0A available and cannot attribute the changed stored status to PAD rather than time or vehicle state. Continue offline by defining product behavior for supported stored/pending results and explicit permanent-service unavailability. Reading and presenting faults is in scope; clearing faults is permanently out of scope. No further vehicle command is approved.
3. **M011 — Vehicle information.** Begin with the offline-tested privacy-safe Mode 09 availability check for VIN match, calibration ID, CVN, and ECU name on the verified DME route. Vehicle behavior remains unverified; raw identifiers are not returned or persisted. Add other individually documented requests only with equivalent privacy handling. Keep VINs, network identifiers, raw exchanges, and other private identifiers out of tracked output and public reports.

### Recorded backlog

- Reassess the moving-validation design offline after the 300-second candidate exceeded its reviewed speed ceiling. The completed run cannot be retried under its procedure, and no new road command is authorized.
- Extend the dashboard with user-selectable layouts and useful session minimum/maximum presentation.
- Add live data from additional control units only after their routes, identifiers, formulas, and limits are established on this vehicle.
- Investigate read-only ZF 8HP adaptation values only if the vehicle has the applicable transmission and authoritative or empirical evidence establishes the exact route and decoding.
- The 30-minute `drive-session` run remains blocked after the 300-second candidate failed its speed-ceiling audit. Toyota PDS battery guidance covers stationary PAD/ISTA service work and does not establish safe battery or telemetry duration while driving. Native CarPlay or Android Auto integration is a separate future architecture decision.
- Consider DoIP routing only if future evidence establishes a need and a safe, bounded procedure.
- DPF status is not applicable to this gasoline vehicle.

### Permanently excluded

Do not implement clearing diagnostic faults, battery registration, service resets, adaptation resets, parking-brake service mode, short-circuit-lock resets, DPF regeneration requests, exhaust-flap or Active Sound Design control, sound tuning, actuator tests, routines, security access, coding, programming, or any other state-changing operation.

Safety risks include intermittent adapter/link behavior, gateway routing variability, bus load and ECU rate limits, ambiguous responses, and possible vehicle-state consequences from undocumented diagnostic interactions. Keep communication read-only and fail closed; do not infer safe limits from the existing bounded run.
