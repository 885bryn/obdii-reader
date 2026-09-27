# Project progress

Last updated: 2026-09-26

## Source of truth

This file is the cross-computer summary of verified project milestones and the next safe checkpoint. Update it from evidence in the current checkout and the user's reported vehicle results. `docs/roadmap.md` remains the implementation roadmap; `docs/research.md`, `docs/safety.md`, and `docs/testing-handoff.md` retain technical evidence and procedures. When records disagree, preserve the narrower claim and resolve it against the underlying evidence before marking a milestone complete.

## Status legend

- **DONE** — supported by recorded test results or an explicitly identified user-reported vehicle result.
- **PARTIAL** — some evidence exists, but an important part remains unverified.
- **NEXT** — planned checkpoint; not yet performed.
- **BLOCKED** — cannot proceed safely until the stated evidence or decision is available.

## Major milestones

| Status | Milestone | Evidence / boundary | Completed |
| --- | --- | --- | --- |
| DONE | Offline protocol and safety tests | 19 offline unit tests passed; software fixtures only, no car traffic. | 2026-09-24 |
| DONE | Link and HSFZ discovery | On 2026-09-26, after a clean five-minute power-down, user confirmed parked, engine off, charger connected, ENET attached, and PAD/Diagnostics Mode active. Host preflight showed adapter Up at 100 Mbps, one link-local address, and AC USB selective suspend disabled. Fresh redacted discovery found one HSFZ gateway and no DoIP. | 2026-09-26 |
| DONE | Gateway identity routing | `verify-gateway` succeeded in the clean session with one read-only UDS 22 F190 identity request. | 2026-09-26 |
| DONE | Engine ECU (DME) identity routing | `verify-dme` succeeded in the clean session with one read-only UDS 22 F190 identity request to candidate target 0x12. That address was community-derived before this vehicle result; this exact successful identity match now verifies the route for this vehicle. | 2026-09-26 |
| NEXT | Supported standard PID bitmap | Implement and offline-review a bounded standard Mode 01 supported-PID bitmap check before requesting coolant PID 05 or oil PID 5C values. | — |
| NEXT | Coolant and oil-temperature reads | Coolant PID 05 and oil PID 5C remain candidates; ECU support and plausible returned temperature values have not been verified. | — |
| NEXT | Conservative live-read behavior and update rate | No live polling or vehicle update-rate measurement has been validated. | — |

## Current safe checkpoint

On 2026-09-26, following a clean five-minute power-down, the user confirmed the vehicle was parked with engine off, charger connected, ENET attached, and PAD/Diagnostics Mode active. Host preflight confirmed the Ethernet adapter Up at 100 Mbps, exactly one link-local address, and AC USB selective suspend disabled. Fresh redacted discovery found one HSFZ gateway and no DoIP. The source-bound TCP connection-only check to the captured peer on port 6801 succeeded without diagnostic payload. `verify-gateway` succeeded with one read-only UDS 22 F190 identity request, and `verify-dme` succeeded with one read-only UDS 22 F190 request to candidate target 0x12. The 0x12 address had been community-derived before this exact successful vehicle result, which verifies DME identity routing on this car. No writes, session changes, tester-present messages, fault clears, routines, polling, or temperature requests were sent. Earlier failed connection and DME attempts remain historical evidence only; the clean-session results establish the route. Supported standard PIDs, actual coolant/oil values, and a safe polling interval remain unknown. The oil-temperature decoder is implemented and its profile entry remains disabled/unverified.

## Next action

Implement and offline-review a bounded standard Mode 01 supported-PID bitmap check. Only after review should it be run as the next read-only checkpoint. Use the verified DME route; do not request PID 05 or PID 5C values until the bitmap check establishes support. No live polling or temperature request has yet been validated.

## Blockers and unknowns

- Toyota has not published the Supra's HSFZ addressing in the tracked evidence. Candidate DME target 0x12 was community-derived before the successful clean-session identity result; `verify-dme` success now establishes identity routing to that target on this vehicle.
- Support and actual values for coolant PID 05 and oil-temperature PID 5C are unknown on this vehicle.
- Session requirements beyond the tested PAD state, battery-support duration, supported PID bitmap, request limits, and live update rate remain unverified.
- No DoIP announcement was seen in the fresh discovery; DoIP routing is not implemented.

The successful identity checks each sent one read-only 22 F190 request. No writes, session changes, tester-present, clears, routines, polling, or temperature requests were sent.

## Privacy rule

Never put VIN, MAC, EID, GID, IP/interface addresses, raw packet bytes, or unredacted capture contents in this tracker, any tracked documentation, commit message, or public report. Keep full captures local and ignored by Git. Record only redacted outcomes and the evidence category.

## Two-computer sync routine

1. Before work on either computer, pull the shared branch and read this tracker plus the relevant roadmap, research, safety, and handoff notes. Resolve tracker conflicts against evidence; do not overwrite the other computer's progress.
2. After a major step, record its status, date, and concise evidence here. Distinguish code/test results from user-reported vehicle results; code written alone is not completion evidence.
3. Verify the change or result, inspect the final diff for private identifiers, then commit and push the tracker with related work. On the other computer, pull before continuing.
