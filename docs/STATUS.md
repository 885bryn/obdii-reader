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
  "updated_at": "2026-09-28T15:40:12-07:00",
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
    "summary": "Run the single authorized 30-second stationary normal-mode faster-cadence validation exactly as documented, then report only the privacy-safe outcome. Do not retry or run another vehicle command in the same session.",
    "owner": "user",
    "reference": "docs/safety.md"
  },
  "attention": [
    "Exactly one 30-second faster-cadence validation is authorized after synchronization; no retry or other vehicle command is approved.",
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
    "summary": "Independent medium review approved the faster scheduler after repair, and a separate independent review approved the exact 30-second one-run vehicle-validation procedure after correcting its DTC and browser-failure wording."
  },
  "integration": {
    "status": "local_changes",
    "summary": "The faster implementation is synchronized. The newly approved 30-second procedure and authorization are local changes pending final commit and push."
  },
  "handoff": {
    "summary": "The original live rehearsal is complete and must not be repeated. Exactly one stationary, PAD-off, 30-second faster-cadence validation is approved after synchronization, with at most three paced DTC reads followed by 150 monitoring attempts. Stop on any error or warning and do not retry."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
