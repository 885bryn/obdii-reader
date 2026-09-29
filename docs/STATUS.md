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
  "updated_at": "2026-09-29T10:56:19-07:00",
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
    "summary": "The bounded private capture harness, cleanup and failure tests, decoded-database integrity gate, five-second health monitoring, and laptop handoff procedure are implemented and independently approved for offline laptop continuation. All 160 portable tests pass. Short loopback-only desktop probes established this desktop's native Packet Monitor filter, start, status, stop, conversion, and cleanup formats; they did not contact the vehicle, complete the loopback application interval, verify the laptop, or satisfy the 35-minute gate.",
    "at": "2026-09-29T10:52:56-07:00",
    "evidence": [
      "supra_telemetry/capture_harness.py",
      "tests/test_capture_harness.py",
      "docs/safety.md",
      "README.md"
    ]
  },
  "next_action": {
    "summary": "On the actual capture laptop, pull the reviewed commit, keep the vehicle physically disconnected, and run the exact three-second elevated loopback smoke in docs/safety.md. Use its private native output to implement and independently review the fail-closed coverage parser, then complete and independently audit the exact 2,100-second laptop rehearsal. Until every laptop gate passes, the decision remains no-go and no vehicle run is authorized.",
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
    "The capture harness is approved only for offline continuation on the actual capture laptop; it does not authorize a vehicle command or raw vehicle-capture run.",
    "Desktop-native probes cannot establish laptop Packet Monitor compatibility, driver/provider behavior, timing, storage, retention, or coverage.",
    "The native coverage parser remains intentionally fail-closed until the laptop smoke establishes defensible fields and an independent review approves them.",
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
    "summary": "All 160 portable offline tests pass, including 26 capture-harness tests for exact child arguments, private/fresh paths, filter ownership races, capture and disk health loss, bounded shutdown, false-success stop, artifact completeness, SQLite integrity, cleanup failures, operator interruption, hard deadline, and fail-closed coverage. Compilation, CLI help, and diff checks pass. Desktop-native probes verified only desktop command/output shapes and cleanup. The actual laptop smoke, native coverage parser, 35-minute retention and overhead, and final evidence audit remain unverified; the original vehicle timeout cause remains unknown.",
    "verified_at": "2026-09-29T10:52:56-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium re-review approved the final desktop implementation and exact laptop handoff for offline continuation after repairs to runtime health bounds, hard-stop budgeting, stop verification, database integrity, artifact gates, native filter parsing, and active-status proof. This approval does not cover the laptop-native coverage parser, 35-minute rehearsal, final vehicle command, or vehicle execution."
  },
  "integration": {
    "status": "synchronized",
    "summary": "The reviewed desktop capture-harness implementation, tests, laptop-only procedure, and operational status are committed at 9d54abc and synchronized to origin/main. All raw captures, host evidence, private databases, and helper scripts remain ignored and outside Git/GitHub."
  },
  "handoff": {
    "summary": "T009-15 remains in progress and is now at a laptop-only boundary. Pull the synchronized commit on the actual capture laptop; with the vehicle physically disconnected, run the exact three-second elevated smoke in docs/safety.md. Repair and independently review only evidence-based laptop parser differences, then run and audit the exact 2,100-second rehearsal. The current final decision is no-go; no vehicle or raw vehicle-capture run is authorized."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
