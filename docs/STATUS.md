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
  "updated_at": "2026-09-29T16:28:28-07:00",
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
    "summary": "A separate stakeholder-dashboard MVP now serves the six existing read-only Mode 01 values over loopback until manual stop, accepts the standard decoded speed and RPM domains without an artificial speed gate, and performs no DTC snapshot, SQLite recording, export, raw logging, retry, reconnect, discovery, or vehicle-control action. Listener reservation precedes source construction, request starts remain serialized and capped at five per second, the first acquisition error stops the source, the browser clears stale values after API loss, and the CLI reports only fixed failure categories. All 167 portable offline tests and the production frontend build pass, and independent medium re-review approved the repaired implementation. No vehicle traffic was sent and no vehicle run is authorized.",
    "at": "2026-09-29T16:28:28-07:00",
    "evidence": [
      "supra_telemetry/client_dashboard.py",
      "supra_telemetry/__main__.py",
      "tests/test_client_dashboard.py",
      "frontend/src/dashboard.tsx",
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
    "The stakeholder dashboard is approved and verified offline only; its command and confirmation flag do not authorize connection to or execution against the vehicle.",
    "The source-host log audit found no relevant recorded event near the timeout, but disabled low-level channels prevent treating that absence as proof that no transient occurred.",
    "The capture harness is approved only for offline continuation on the actual capture laptop; it does not authorize a vehicle command or raw vehicle-capture run.",
    "Desktop-native probes cannot establish laptop Packet Monitor compatibility, driver/provider behavior, timing, storage, retention, or coverage.",
    "The native coverage parser remains intentionally fail-closed until the laptop smoke establishes defensible fields and an independent review approves them.",
    "Any ETL, PCAPNG, database, event export, console log, manifest, or analysis working file from the proposed procedure is private and must remain in a Git-ignored directory.",
    "The private moving-recording-30min.sqlite file is present in this repository root, remains Git-ignored, and must stay outside Git/GitHub."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The compiled React frontend remains loopback-only with the privacy-safe /api/state contract as its sole browser data source. The new stakeholder command reuses only the existing capture-bound moving six-PID source and fixed scheduler, adds no persistence or DTC acquisition, and permits unbounded manual duration only on that moving source while all existing stationary and finite commands retain their limits. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "partial",
    "summary": "All 167 portable offline tests pass. New coverage verifies standard decoded moving speed/RPM values without an artificial speed gate, the exact fixed route/PID schedule and rolling request-start limit, no DTC or recording path, loopback reservation order, indefinite manual lifecycle only for the moving source, stationary-source duration preservation, fixed redacted halt reporting, stale-value clearing, and packaged asset serving. Frontend type checking and the Vite production build pass, CLI help is correct, and staged diff checks pass. No real capture was opened and no vehicle traffic was sent. The actual laptop capture smoke, native coverage parser, 35-minute retention and overhead, and final evidence audit remain unverified; the original vehicle timeout cause remains unknown.",
    "verified_at": "2026-09-29T16:28:28-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "Independent medium review found and then approved the repair for the stakeholder dashboard's terminal-error transition: browser API loss now clears stale samples and the CLI reports only allowlisted fixed reasons. Re-review also confirmed that indefinite duration is restricted to the moving source, existing commands remain bounded, the new packaged asset is present, and the MVP adds no DTC, persistence, retry, reconnect, or vehicle-control path. Approval is offline-only and does not cover vehicle execution."
  },
  "integration": {
    "status": "synchronized",
    "summary": "The reviewed stakeholder dashboard MVP, rebuilt frontend assets, tests, documentation, and operational records are committed and synchronized to origin/main. All raw captures, host evidence, private databases, and helper scripts remain ignored and outside Git/GitHub."
  },
  "handoff": {
    "summary": "The stakeholder dashboard MVP is complete and independently approved offline, but it has not run against the vehicle and provides no vehicle authorization. T009-15 remains in progress at a laptop-only boundary: pull the synchronized commit on the actual capture laptop, keep the vehicle physically disconnected, and run the exact three-second elevated smoke in docs/safety.md. Repair and independently review only evidence-based laptop parser differences, then run and audit the exact 2,100-second rehearsal. The current final decision remains no-go; no vehicle or raw vehicle-capture run is authorized."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
