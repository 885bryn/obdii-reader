---
{
  "contract": "codex-project-status",
  "schema_version": 1,
  "project": {
    "name": "Supra OBD2 Telemetry",
    "goal": "Build a reliable, extensible, strictly read-only telemetry platform for a 2023 Toyota GR Supra over wired ENET"
  },
  "project_state": "active",
  "workflow_stage": "implementation",
  "health": "attention",
  "updated_at": "2026-09-29T02:04:33-07:00",
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
      "id": "T009-15",
      "title": "Prepare a capture-enhanced 30-minute repeat",
      "status": "in_progress",
      "path": "docs/roadmap.md"
    }
  },
  "latest_accomplishment": {
    "summary": "A bounded plan for a capture-enhanced repeat of the 30-minute candidate was independently reviewed and approved for offline harness implementation. The proposed run keeps the existing six-signal vehicle traffic, route, cadence, two-second deadline, and fail-closed behavior unchanged while adding a private, bounded Packet Monitor and ETW evidence bundle. The approval covers offline implementation only and does not authorize a vehicle command or raw-capture run.",
    "at": "2026-09-29T02:00:19-07:00",
    "evidence": [
      "docs/safety.md",
      "docs/roadmap.md"
    ]
  },
  "next_action": {
    "summary": "Implement the bounded passive-capture harness without changing vehicle-facing traffic, add the specified offline fault-injection coverage, complete a 35-minute offline rehearsal, and independently review the harness, artifacts, exact command, and evidence gates. Only then may the user make a final one-time vehicle go/no-go decision.",
    "owner": "lead",
    "reference": "docs/safety.md"
  },
  "attention": [
    "The one-time stationary recording authorization has been consumed and passed; do not repeat it.",
    "The one-time 60-second moving authorization has been consumed and passed; do not repeat it.",
    "The one-time 300-second authorization was consumed and failed its then-current artificial speed-ceiling audit; do not repeat it.",
    "The one-time 30-minute normal-driving authorization was consumed and stopped on a vehicle-speed timeout after 568.64 seconds; do not repeat it.",
    "No vehicle command or raw-capture run is currently authorized.",
    "The source-host log audit found no relevant recorded event near the timeout, but disabled low-level channels prevent treating that absence as proof that no transient occurred.",
    "The capture-enhanced repeat is a reviewed draft for offline harness implementation only; it does not authorize a vehicle command or raw-capture run.",
    "Any ETL, PCAPNG, database, event export, console log, manifest, or analysis working file from the proposed procedure is private and must remain in a Git-ignored directory.",
    "The private moving-recording-30min.sqlite file is present in this repository root, remains Git-ignored, and must stay outside Git/GitHub."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The telemetry and safety architecture is unchanged. A compiled React frontend is served by the existing loopback-only Python server, and the privacy-safe /api/state contract remains the sole browser data source. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "partial",
    "summary": "The documentation plan passed diff checks and independent safety review for offline implementation. The capture harness, fault-injection tests, 35-minute rehearsal, retention and coverage gates, artifact finalization, and exact invocation do not exist yet and remain unverified. The original timeout cause remains unknown.",
    "verified_at": "2026-09-29T02:00:19-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium review approved the documentation draft for offline harness implementation after retention, filter ownership, provider coverage, privacy, fresh-path, and observation-limit repairs. This approval does not cover unimplemented code, an exact vehicle command, or vehicle execution."
  },
  "integration": {
    "status": "synchronized",
    "summary": "The reviewed capture-enhanced repeat plan and operational status are committed and synchronized to origin/main. Existing private data remains ignored and outside Git/GitHub."
  },
  "handoff": {
    "summary": "T009-15 is in progress. The reviewed draft preserves identical six-signal vehicle traffic and proposes bounded private Packet Monitor/ETW evidence, but only offline harness implementation is approved. Build and rehearse the harness, independently review it and the exact command, and obtain the user's final one-time go/no-go before any vehicle use."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
