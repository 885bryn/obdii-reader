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
  "updated_at": "2026-09-28T23:01:47-07:00",
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
      "id": "T009-14",
      "title": "Investigate the interrupted 30-minute drive session",
      "status": "in_progress",
      "path": "docs/roadmap.md"
    }
  },
  "latest_accomplishment": {
    "summary": "The one-time 30-minute normal-driving candidate stopped fail-closed after 568.64 seconds when a vehicle-speed request timed out. The private SQLite database is integral and finalized with 2,716 rows, one allowlisted timeout row, no other sample errors, valid chronology and decoded domains before the failure, privacy-safe signal definitions, and no raw exchanges.",
    "at": "2026-09-28T23:01:47-07:00",
    "evidence": [
      "docs/research.md",
      "docs/safety.md",
      "tests/test_drive_session.py"
    ]
  },
  "next_action": {
    "summary": "Investigate the timeout offline and design and independently review any new bounded read-only diagnostic run before vehicle use. Any raw capture must remain private, narrowly filtered, and excluded from Git and GitHub.",
    "owner": "lead",
    "reference": "docs/safety.md"
  },
  "attention": [
    "The one-time stationary recording authorization has been consumed and passed; do not repeat it.",
    "The one-time 60-second moving authorization has been consumed and passed; do not repeat it.",
    "The one-time 300-second authorization was consumed and failed its then-current artificial speed-ceiling audit; do not repeat it.",
    "The one-time 30-minute normal-driving authorization was consumed and stopped on a vehicle-speed timeout after 568.64 seconds; do not repeat it.",
    "No vehicle command or raw-capture run is currently authorized.",
    "The private moving-recording-30min.sqlite file remains Git-ignored. Before continuing on another computer, the user will transfer it privately outside Git/GitHub and place it in the repository root for local inspection."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The telemetry and safety architecture is unchanged. A compiled React frontend is served by the existing loopback-only Python server, and the privacy-safe /api/state contract remains the sole browser data source. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "failed",
    "summary": "The 30-minute candidate stopped after 568.64 seconds on one allowlisted vehicle-speed timeout. The dashboard became unavailable because the application correctly halted acquisition and shut down its loopback server. The partial database passed integrity, finalization, privacy, chronology, and pre-error decoded-domain checks.",
    "verified_at": "2026-09-28T23:01:47-07:00"
  },
  "review": {
    "status": "pending",
    "summary": "The approved one-time procedure was consumed. A retry with private packet capture would be a new procedure and is not authorized until its capture scope, privacy handling, bounds, and stop conditions are independently reviewed."
  },
  "integration": {
    "status": "pending",
    "summary": "Tracked code and documentation are ready for remote publication. Private SQLite databases and captures remain ignored and must be transferred between computers outside Git/GitHub."
  },
  "handoff": {
    "summary": "The one-time 30-minute candidate stopped fail-closed after 568.64 seconds on a vehicle-speed timeout; no retry is authorized. The private moving-recording-30min.sqlite file is not in Git. The user must transfer it privately to any other development computer before resuming this investigation."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
