---
{
  "contract": "codex-project-status",
  "schema_version": 1,
  "project": {
    "name": "Supra OBD2 Telemetry",
    "goal": "Build a reliable, extensible, strictly read-only telemetry platform for a 2023 Toyota GR Supra over wired ENET"
  },
  "project_state": "active",
  "workflow_stage": "handoff",
  "health": "healthy",
  "updated_at": "2026-09-28T15:35:35-07:00",
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
      "id": "T009-6",
      "title": "Bounded faster client-dashboard cadence",
      "status": "reviewed",
      "path": "docs/roadmap.md"
    }
  },
  "latest_accomplishment": {
    "summary": "The faster client-dashboard scheduler now targets RPM every 0.5 seconds, throttle every second, and the other four values every two seconds while enforcing a rolling five-starts-per-second limit, a 300-second deadline, and a 1,500-attempt maximum. All 117 offline tests pass, independent medium review approved the repaired scheduler, and a fresh independent verification passed. No vehicle traffic was sent by this change.",
    "at": "2026-09-28T15:35:35-07:00",
    "evidence": [
      "supra_telemetry/client_dashboard.py",
      "tests/test_client_dashboard.py",
      "docs/safety.md",
      "docs/architecture.md"
    ]
  },
  "next_action": {
    "summary": "Prepare and independently review a separately bounded normal-mode vehicle-validation procedure for the faster cadence before authorizing any live run. No vehicle command is currently authorized.",
    "owner": "lead",
    "reference": "docs/safety.md"
  },
  "attention": [
    "No vehicle command is currently authorized.",
    "The faster 100 ms-slot scheduler is offline-only and has not been vehicle-tested."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The candidate uses a 20-slot, two-second serialized scheduler targeting RPM every 0.5 seconds, throttle every second, and four supporting values every two seconds. It retains a 300-second wall limit, a rolling five-starts-per-second ceiling, a 1,500-attempt total ceiling, skipped overdue slots, stationary gates, and stop-on-first-error behavior. Simulated mode has no vehicle client or transport surface.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "passed",
    "summary": "All 117 offline tests pass. Sixteen focused dashboard tests cover cadence, idle slots, rolling-rate enforcement, jitter without catch-up bursts, wall deadline, 1,500-attempt maximum, stop behavior, DTC gating, cleanup/redaction, and simulated no-I/O behavior. Fresh independent verification reproduced the 16 focused passes and a clean diff check. No faster-cadence vehicle run occurred.",
    "verified_at": "2026-09-28T15:35:35-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium re-review found and drove repair of catch-up bursts and rolling-rate jitter, then approved the final skipped-slot scheduler, strict five-starts-per-second limiter, tests, UI wording, and no-authorization safety boundary."
  },
  "integration": {
    "status": "synchronized",
    "summary": "The completed live result, independently reviewed faster offline candidate, tests, and operational records are synchronized to origin/main in commit 73ce854."
  },
  "handoff": {
    "summary": "The original live rehearsal is complete and must not be repeated. The faster candidate remains finite at 300 seconds and at most 1,500 sensor attempts, but is offline-only until verification and review finish. No vehicle command is currently authorized; simulated mode remains the presentation fallback."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
