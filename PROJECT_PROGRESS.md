# Project progress

Last updated: 2026-09-24

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
| DONE | Link and HSFZ discovery | One HSFZ vehicle-identification response observed while stationary with engine off; no DoIP announcement in that attempt. | 2026-09-24 |
| DONE | Gateway identity routing | User reported `verify-gateway` succeeded. The check performs one read-only VIN identity request and verifies a match; no signals were queried. | 2026-09-24 |
| PARTIAL | Engine ECU (DME) identity routing | The privacy-safe categorized command passed 19 offline tests and independent review, clearing the review blocker. Next checkpoint: one deliberate single-request vehicle attempt. Two earlier attempts remain indeterminate: the adapter/interface was absent when checked after each command, so neither establishes DME acceptance or rejection. AC-only USB selective-suspend mitigation was followed by a 45-second stable-Up monitor and successful fresh redacted discovery/current-interface match. | — |
| NEXT | Supported coolant and oil-temperature reads | Coolant PID 05 and oil-temperature PID 5C are candidates only. No ECU support, returned value, or plausibility has been verified on this car. | — |
| NEXT | Conservative live-read behavior and update rate | No live polling or vehicle update-rate measurement has been validated. | — |

## Current safe checkpoint

Gateway HSFZ identity routing has been reported successful. The privacy-safe categorized DME command passed 19 offline tests and independent review, clearing the review blocker. Two earlier `verify-dme` attempts returned generic failures; the adapter/interface was checked only afterward and found absent, so whether either request sent diagnostic bytes before disconnect is indeterminate. Neither result establishes DME acceptance or rejection. As a reversible mitigation, USB selective suspend was disabled for AC power. Afterward, the adapter stayed Up during a 45-second monitor, and a fresh redacted discovery succeeded with the current capture/interface matching on an elevated read-only check. The next checkpoint is one deliberate single-request DME attempt using the reviewed categorized command. A `connection-or-transport` result cannot distinguish a pre-send failure from a disconnect after sending; record transmission as indeterminate unless separate evidence proves otherwise. Supported PIDs, temperature readings, and a safe polling interval remain unverified. The oil-temperature decoder is implemented and its profile entry remains disabled/unverified.

## Next action

With the privacy-safe categorized command's 19 offline tests and independent review passed, make one deliberate single-request vehicle attempt under the documented stationary setup. Record only its categorized outcome and whether transmission is known or indeterminate; `connection-or-transport` alone cannot tell whether the request was sent before a disconnect. The target address remains unverified on this vehicle, so do not copy it into a live profile unless routing is established. After routing is established, query standard PID support before requesting coolant or oil temperature, then validate returned values while stationary.

## Blockers and unknowns

- Toyota-published HSFZ tester/target addressing and the Supra engine ECU address are not available in the tracked evidence.
- Two earlier DME CLI attempts returned generic failures; adapter/interface absence was observed only after each command, leaving request-byte transmission indeterminate for both. Neither establishes acceptance or rejection. AC USB selective-suspend mitigation improved observed stability (Up for 45 seconds) and fresh discovery/current-interface matching succeeded. The categorized command's review blocker is cleared; the remaining checkpoint is one deliberate single-request vehicle attempt. A `connection-or-transport` result is transmission-indeterminate unless separate evidence proves pre-send failure or successful transmission.
- Support and actual values for coolant PID 05 and oil-temperature PID 5C are unknown on this vehicle.
- Session requirements, battery-support duration, request limits, and live update rate remain unverified.
- The observed discovery had no DoIP announcement; DoIP routing is not implemented.

## Privacy rule

Never put VIN, MAC, EID, GID, IP/interface addresses, raw packet bytes, or unredacted capture contents in this tracker, any tracked documentation, commit message, or public report. Keep full captures local and ignored by Git. Record only redacted outcomes and the evidence category.

## Two-computer sync routine

1. Before work on either computer, pull the shared branch and read this tracker plus the relevant roadmap, research, safety, and handoff notes. Resolve tracker conflicts against evidence; do not overwrite the other computer's progress.
2. After a major step, record its status, date, and concise evidence here. Distinguish code/test results from user-reported vehicle results; code written alone is not completion evidence.
3. Verify the change or result, inspect the final diff for private identifiers, then commit and push the tracker with related work. On the other computer, pull before continuing.
