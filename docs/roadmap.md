# Future roadmap and risks

Current project state is in [STATUS.md](STATUS.md); completed verified milestones are in [PROJECT_HISTORY.md](PROJECT_HISTORY.md). This file contains future work only.

## Major goal: read-only BimmerLink parity

Reproduce the useful diagnostic and monitoring capabilities of BimmerLink for this Supra while permanently excluding every operation that clears, resets, registers, codes, actuates, or otherwise changes vehicle or ECU state. Read-only still creates diagnostic traffic, so every new route and request must remain evidence-backed, bounded, reviewed, and fail-closed. Manually entered Diagnostic/PAD Mode may be used for bounded read-only research and discovery when the vehicle procedure requires it, but it is not product acceptance evidence. Every finished capability must also work and be verified in the intended normal vehicle mode with Diagnostic/PAD Mode off.

### Ordered delivery

1. **M009 — Common DME live sensors.** Expand the already-verified DME telemetry path in small batches. The DME has advertised support for engine RPM, vehicle speed, intake-air temperature, and throttle position. One stationary engine-idling suite run accepted all four one-shot responses and passed its plausibility gate, but its privacy-safe failure summary did not retain the exact measurements. Establish useful observed ranges and a conservative rate before repeated monitoring. Boost and further DME values follow only when their request, formula, support, and safe cadence are established.
2. **M010 — Read-only fault diagnostics.** The first bounded Mode 03/07/0A vehicle phase stopped on `response-invalid`; its exact failed response was intentionally not retained. Investigate the protocol assumptions offline and require a new review before any vehicle retry. If offline evidence does not explain the mismatch, plan one manually entered Diagnostic/PAD Mode read-only comparison inside the next consolidated vehicle session. Treat PAD-on success as research evidence only; normal PAD-off behavior remains the product acceptance target. Expand toward a full-vehicle fault scan only after an evidence-backed control-unit inventory and explicit routes exist; do not scan or guess addresses. Reading and presenting faults is in scope. Clearing faults is permanently out of scope.
3. **M011 — Vehicle information.** Begin with the offline-tested privacy-safe Mode 09 availability check for VIN match, calibration ID, CVN, and ECU name on the verified DME route. Vehicle behavior remains unverified; raw identifiers are not returned or persisted. Add other individually documented requests only with equivalent privacy handling. Keep VINs, network identifiers, raw exchanges, and other private identifiers out of tracked output and public reports.

### Recorded backlog

- Validate decoded-sample recording and CSV export in a bounded vehicle run; recording remains unverified on the vehicle.
- Add dashboard personalization, gauges, layouts, and useful minimum/maximum presentation.
- Add live data from additional control units only after their routes, identifiers, formulas, and limits are established on this vehicle.
- Investigate read-only ZF 8HP adaptation values only if the vehicle has the applicable transmission and authoritative or empirical evidence establishes the exact route and decoding.
- Consider a simplified driving display after the diagnostic foundation. Native CarPlay or Android Auto integration is a separate future architecture decision.
- Establish authoritative guidance for session and battery-support limits before proposing any vehicle session longer than the verified 300-second window.
- Consider DoIP routing only if future evidence establishes a need and a safe, bounded procedure.
- DPF status is not applicable to this gasoline vehicle.

### Permanently excluded

Do not implement clearing diagnostic faults, battery registration, service resets, adaptation resets, parking-brake service mode, short-circuit-lock resets, DPF regeneration requests, exhaust-flap or Active Sound Design control, sound tuning, actuator tests, routines, security access, coding, programming, or any other state-changing operation.

Safety risks include intermittent adapter/link behavior, gateway routing variability, bus load and ECU rate limits, ambiguous responses, and possible vehicle-state consequences from undocumented diagnostic interactions. Keep communication read-only and fail closed; do not infer safe limits from the existing bounded run.
