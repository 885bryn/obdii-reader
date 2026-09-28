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
  "updated_at": "2026-09-28T12:39:27-07:00",
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
      "id": "T009-4",
      "title": "Build client live/simulated dashboard",
      "status": "reviewed",
      "path": "docs/roadmap.md"
    }
  },
  "latest_accomplishment": {
    "summary": "A client-ready loopback dashboard now has explicit simulated and live modes, six verified-signal displays, faster RPM presentation, and a privacy-safe DTC snapshot. All 116 offline tests pass, browser visual inspection passed, and independent medium re-review approved the implementation and exact one-run procedure. No vehicle traffic was sent.",
    "at": "2026-09-28T12:39:27-07:00",
    "evidence": [
      "supra_telemetry/client_dashboard.py",
      "tests/test_client_dashboard.py",
      "docs/safety.md",
      "README.md"
    ]
  },
  "next_action": {
    "summary": "Run the single authorized stationary normal-mode client-dashboard rehearsal exactly as documented, then report only the privacy-safe outcome. Do not retry or run a second live demonstration without review; simulated mode is ready as the presentation fallback.",
    "owner": "user",
    "reference": "docs/safety.md"
  },
  "attention": [],
  "architecture": {
    "status": "aligned",
    "summary": "The client dashboard reserves its loopback listener before vehicle I/O, paces the fixed DTC snapshot and six-PID live schedule at a one-second request-start floor, prioritizes RPM, caps monitoring at 300 attempts and 300 seconds, and stops without retry. Simulated mode has no vehicle client or transport surface.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "passed",
    "summary": "All 116 offline tests pass, including request pacing, listener prebinding, DTC-to-monitor gating, cleanup/redaction, concurrent API snapshots, and simulated no-I/O behavior. Browser inspection verified the responsive dashboard, six readings, faster simulated RPM, DTC groups, and explicit simulated labeling. No dashboard vehicle run has occurred.",
    "verified_at": "2026-09-28T12:39:27-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium re-review reproduced the focused dashboard tests and all 116 offline tests, approved the repaired implementation, and found the exact single-run procedure coherent. Live vehicle behavior remains unverified."
  },
  "integration": {
    "status": "synchronized",
    "summary": "The reviewed client-dashboard implementation, tests, procedure, and operational records are synchronized to origin/main."
  },
  "handoff": {
    "summary": "Simulated mode is presentation-ready. Exactly one stationary, PAD-off live rehearsal is approved under docs/safety.md; it may attempt at most three paced DTC reads followed by 300 paced sensor requests. Stop on any error or warning, do not retry, and use simulated mode for the client if the live rehearsal is not clean."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
