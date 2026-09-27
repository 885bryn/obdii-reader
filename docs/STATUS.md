---
{
  "contract": "codex-project-status",
  "schema_version": 1,
  "project": {
    "name": "Supra OBD2 Telemetry",
    "goal": "Build a reliable, extensible, strictly read-only telemetry platform for a 2023 Toyota GR Supra over wired ENET"
  },
  "project_state": "active",
  "workflow_stage": "vehicle_validation",
  "health": "healthy",
  "updated_at": "2026-09-27T16:51:57-07:00",
  "current": {
    "feature": {
      "id": "F001",
      "title": "Read-only BimmerLink parity",
      "path": "docs/roadmap.md"
    },
    "milestone": {
      "id": "M009",
      "title": "Common DME live sensors",
      "status": "in_progress",
      "path": "docs/roadmap.md"
    },
    "task": {
      "id": "T009-3",
      "title": "Run bounded DME read-only discovery suite",
      "status": "ready",
      "path": "supra_telemetry/read_only_suite.py"
    }
  },
  "latest_accomplishment": {
    "summary": "One bounded common-DME support check completed on the stationary vehicle with the engine off and Diagnostic/PAD Mode off. Its single Mode 01 PID 00 request reported advertised support for engine RPM PID 0C, vehicle speed PID 0D, intake-air-temperature PID 0F, and throttle-position PID 11, then exited successfully.",
    "at": "2026-09-27T16:27:00-07:00",
    "evidence": [
      "docs/PROJECT_HISTORY.md",
      "supra_telemetry/common_dme_support.py",
      "tests/test_common_dme_signals.py"
    ]
  },
  "next_action": {
    "summary": "With the vehicle stationary outdoors, parking brake set, transmission in Park, engine idling without throttle input, PAD/Diagnostic Mode off, stable ENET, and no warnings, run the reviewed collect-read-only-suite command once. Stop immediately on any warning or failed phase and do not retry.",
    "owner": "user",
    "reference": "docs/safety.md"
  },
  "attention": [],
  "architecture": {
    "status": "aligned",
    "summary": "The reviewed suite remains strictly read-only, fail-closed, source-bound to the private discovery capture, and limited to the verified DME route and standardized requests. It rechecks support, applies stationary plausibility gates, stops later phases on first failure, and never exposes a raw request surface.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "passed",
    "summary": "All 71 offline tests pass. They cover exact request order and ceilings, source binding, response parsing, privacy redaction, prohibited clear/control services, fresh support and stationary plausibility gates, two-second warning windows, and stop-on-first-failure behavior. The new vehicle responses remain unverified.",
    "verified_at": "2026-09-27T16:50:00-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium review approved the final bounded suite for its first vehicle run after support-first and stationary plausibility gates were added. No remaining substantive blocker was found."
  },
  "integration": {
    "status": "synchronized",
    "summary": "The offline-verified discovery suite, reviewed safety procedure, and reconciled operational records are synchronized on main without private vehicle or network identifiers."
  },
  "handoff": {
    "summary": "The DME advertised all four first-batch common PIDs. A single reviewed suite now combines conditional standard PID inventory, four one-shot values, selective emissions-DTC reads, and privacy-redacted Mode 09 availability with a 20-request ceiling. It is offline-verified and approved but has not run on the vehicle. Repeated monitoring and recording remain gated on the suite result."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
