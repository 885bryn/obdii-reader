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
  "updated_at": "2026-09-28T21:12:00-07:00",
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
      "id": "T009-10",
      "title": "Review a graduated moving-vehicle telemetry validation",
      "status": "in_progress",
      "path": "docs/roadmap.md"
    }
  },
  "latest_accomplishment": {
    "summary": "The one authorized 60-second stationary drive-session recording gate completed with exit code 0 and 288 requests. Its private local SQLite review passed every required gate: finalized session, exactly zero vehicle speed, coherent samples for all six signals, no recorded errors, privacy-safe signal definitions, and no raw exchanges. This establishes only that stationary session and does not authorize moving use or a longer run.",
    "at": "2026-09-28T21:01:12-07:00",
    "evidence": [
      "docs/research.md",
      "docs/safety.md",
      "tests/test_drive_session.py"
    ]
  },
  "next_action": {
    "summary": "Run only the independently approved one-time 60-second, at-or-below-30-km/h moving procedure with a dedicated passenger operator, secured cable/equipment, stop/no-retry rules, and a fresh database. Then park and perform its private post-run review before any further vehicle command.",
    "owner": "user",
    "reference": "docs/safety.md"
  },
  "attention": [
    "The one-time stationary recording authorization has been consumed and passed; do not repeat it.",
    "Only the exact one-time 60-second low-speed moving command in docs/safety.md is authorized.",
    "A 30-minute run remains blocked pending successful 60-second and separately reviewed 300-second moving stages, longer-session power/session guidance, and separate review of an exact 1,800-second procedure."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The telemetry and safety architecture is unchanged. A compiled React frontend is served by the existing loopback-only Python server, and the privacy-safe /api/state contract remains the sole browser data source. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "passed",
    "summary": "All 134 offline Python tests passed immediately before the vehicle gate. The exact 60-second stationary command then completed with exit code 0, and the private SQLite review passed every required recording, speed, error, metadata, and raw-exchange gate.",
    "verified_at": "2026-09-28T21:01:12-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium re-review approved the exact one-time 60-second low-speed moving procedure after verifying the driver/passenger separation, at-or-below-30-km/h bound, secured cable/equipment gate, exact command, stop/no-retry process, and private database acceptance checks. This approval does not extend to 300 seconds or 30 minutes."
  },
  "integration": {
    "status": "pending",
    "summary": "The verified stationary result and proposed next-stage procedure are being reconciled locally and have not yet been committed or pushed."
  },
  "handoff": {
    "summary": "The stationary gate and its private database review passed. One exact 60-second low-speed moving gate is now independently approved for a single run under docs/safety.md; no retry or longer moving run is authorized. The 30-minute run remains blocked by the required 300-second stage and longer-session guidance."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
