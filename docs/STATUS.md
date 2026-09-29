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
  "updated_at": "2026-09-28T22:21:48-07:00",
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
      "id": "T009-13",
      "title": "Review a normal-driving 30-minute telemetry validation",
      "status": "in_progress",
      "path": "docs/roadmap.md"
    }
  },
  "latest_accomplishment": {
    "summary": "The one authorized 300-second moving command completed at the application level with exit code 0 and 1,443 requests, but its private audit failed the reviewed speed ceiling because at least one sample exceeded 30 km/h. All other summary, error, chronology, privacy, and raw-exchange gates passed. The no-retry rule ended that candidate; at that point no 30-minute run had been authorized.",
    "at": "2026-09-28T21:43:36-07:00",
    "evidence": [
      "docs/research.md",
      "docs/safety.md",
      "tests/test_drive_session.py"
    ]
  },
  "next_action": {
    "summary": "Run only the independently approved one-time 30-minute normal-driving procedure using lawful posted speeds and ordinary road conditions, a passenger operator, secured equipment, stop/no-retry behavior, and a fresh database. Then park and complete the private audit.",
    "owner": "user",
    "reference": "docs/safety.md"
  },
  "attention": [
    "The one-time stationary recording authorization has been consumed and passed; do not repeat it.",
    "The one-time 60-second moving authorization has been consumed and passed; do not repeat it.",
    "The one-time 300-second authorization was consumed and failed its then-current artificial speed-ceiling audit; do not repeat it.",
    "The user has specified normal lawful driving as the intended product condition, with no artificial test speed cap.",
    "Only the exact one-time 30-minute normal-driving command in docs/safety.md is authorized; no retry is authorized."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The telemetry and safety architecture is unchanged. A compiled React frontend is served by the existing loopback-only Python server, and the privacy-safe /api/state contract remains the sole browser data source. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "partial",
    "summary": "The 300-second command exited 0 and passed all application, recording, chronology, privacy, and raw-exchange checks. It failed only the former 30 km/h procedural ceiling, which the user has since rejected as unrepresentative of ordinary lawful driving. This does not itself authorize a longer run.",
    "verified_at": "2026-09-28T21:43:36-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium review approved exactly one 30-minute normal-driving procedure after checking the fixed six-signal capture-bound path, 1,800-second/9,000-attempt caps, serialized request rate, stop-on-error behavior, decoded-only storage, passenger operation, physical preflight, and private audit. No retry is approved."
  },
  "integration": {
    "status": "pending",
    "summary": "The stationary, 60-second moving, and 300-second results are committed locally through a53ad9b, but remote publication was not authorized. The reviewed normal-driving acceptance decision and one-time 30-minute procedure are reconciled in current local changes."
  },
  "handoff": {
    "summary": "The stationary and 60-second moving gates passed. The 300-second application/recording result was clean but failed its former artificial 30 km/h procedure and cannot be retried. The user specified ordinary lawful driving as the intended condition, and exactly one 30-minute command is now independently approved under docs/safety.md."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
