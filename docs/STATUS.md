---
{
  "contract": "codex-project-status",
  "schema_version": 1,
  "project": {
    "name": "Supra OBD2 Telemetry",
    "goal": "Build a reliable, extensible, strictly read-only telemetry platform for a 2023 Toyota GR Supra over wired ENET"
  },
  "project_state": "active",
  "workflow_stage": "verification",
  "health": "attention",
  "updated_at": "2026-09-28T21:43:36-07:00",
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
    "summary": "The one authorized 300-second moving command completed at the application level with exit code 0 and 1,443 requests, but its private audit failed the reviewed speed ceiling because at least one sample exceeded 30 km/h. All other summary, error, chronology, privacy, and raw-exchange gates passed. The no-retry rule ended the candidate; no 30-minute run is authorized.",
    "at": "2026-09-28T21:43:36-07:00",
    "evidence": [
      "docs/research.md",
      "docs/safety.md",
      "tests/test_drive_session.py"
    ]
  },
  "next_action": {
    "summary": "Stop vehicle testing and reassess the moving-validation design offline. Do not retry the 300-second command or start the 30-minute run.",
    "owner": "lead",
    "reference": "docs/safety.md"
  },
  "attention": [
    "The one-time stationary recording authorization has been consumed and passed; do not repeat it.",
    "The one-time 60-second moving authorization has been consumed and passed; do not repeat it.",
    "The one-time 300-second authorization was consumed and failed its speed-ceiling audit; do not repeat it.",
    "No vehicle command is currently authorized.",
    "A 30-minute run is blocked."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The telemetry and safety architecture is unchanged. A compiled React frontend is served by the existing loopback-only Python server, and the privacy-safe /api/state contract remains the sole browser data source. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "failed",
    "summary": "The 300-second command exited 0 and its recording/privacy checks passed, but private read-only inspection found that at least one vehicle-speed sample exceeded the reviewed 30 km/h ceiling. The procedural gate therefore failed.",
    "verified_at": "2026-09-28T21:43:36-07:00"
  },
  "review": {
    "status": "changes_requested",
    "summary": "The independently approved 300-second procedure was consumed and failed its speed-ceiling acceptance gate. Its no-retry rule applies; a new offline plan is required before any vehicle command can be reviewed."
  },
  "integration": {
    "status": "pending",
    "summary": "The stationary result and reviewed 60-second procedure were committed locally at 16c3dd9, but remote publication was not authorized. The completed 60-second moving result and failed 300-second acceptance gate are reconciled in the current local documentation changes."
  },
  "handoff": {
    "summary": "The stationary and 60-second moving gates passed. The 300-second candidate completed without application error but failed its reviewed speed ceiling and cannot be retried. Stop vehicle testing; no 30-minute run is authorized."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
