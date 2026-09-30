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
  "updated_at": "2026-09-29T17:50:22-07:00",
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
    "summary": "The stakeholder dashboard now has an immediate local-only simulated mode and a fail-closed live startup preflight. Simulated mode presents six values until Ctrl+C with no capture, network source, DTC read, storage, or logging. Live remains capture-bound: it reserves loopback first, bind-checks the exact captured interface without sending packets, and passes the same immutable, address-hidden route snapshot into the existing fixed six-PID source without rereading or substituting the capture. All 172 portable offline tests pass; GPT-5.6 Sol Medium independently approved the final diff with no actionable findings. A brief exact-command validation unexpectedly passed preflight and was stopped manually; it may have sent only the existing read-only PID requests, persisted nothing, and produced no accepted empirical value evidence. No further vehicle retry is authorized.",
    "at": "2026-09-29T17:50:22-07:00",
    "evidence": [
      "supra_telemetry/client_dashboard.py",
      "supra_telemetry/__main__.py",
      "tests/test_client_dashboard.py",
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
    "One brief exact-command validation unexpectedly passed the local preflight and was manually stopped; it may have sent only the existing read-only PID requests, logged nothing, and does not authorize a retry or establish plausible live values.",
    "The source-host log audit found no relevant recorded event near the timeout, but disabled low-level channels prevent treating that absence as proof that no transient occurred.",
    "The capture harness is approved only for offline continuation on the actual capture laptop; it does not authorize a vehicle command or raw vehicle-capture run.",
    "Desktop-native probes cannot establish laptop Packet Monitor compatibility, driver/provider behavior, timing, storage, retention, or coverage.",
    "The native coverage parser remains intentionally fail-closed until the laptop smoke establishes defensible fields and an independent review approves them.",
    "Any ETL, PCAPNG, database, event export, console log, manifest, or analysis working file from the proposed procedure is private and must remain in a Git-ignored directory.",
    "The private moving-recording-30min.sqlite file is present in this repository root, remains Git-ignored, and must stay outside Git/GitHub."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The compiled React frontend remains loopback-only with the privacy-safe /api/state contract as its sole browser data source. Stakeholder simulated mode is local-only and unbounded until manual stop. Live startup reserves loopback, validates the exact capture once, bind-checks that source locally without packets, and reuses the same immutable hidden route snapshot for the fixed six-PID source. It adds no persistence or DTC acquisition and does not alter existing finite commands. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "partial",
    "summary": "All 172 portable offline tests pass. New coverage verifies simulated mode has no capture, vehicle source, DTC, store, or log; live reserves loopback first; preflight performs bind/close only on the exact captured interface; failure prevents source construction; and the validated immutable route snapshot is reused without a second capture read or substitution. Python compilation, CLI help, diff checks, and direct simulated HTTP/API inspection pass. The laptop capture smoke, native coverage parser, 35-minute retention and overhead, and final evidence audit remain unverified; the original vehicle timeout cause remains unknown.",
    "verified_at": "2026-09-29T17:50:22-07:00"
  },
  "review": {
    "status": "approved",
    "summary": "GPT-5.6 Sol Medium independently approved the final recovery diff with no actionable findings after verifying simulated/live CLI behavior, zero-I/O simulated mode, bind-only preflight, immutable route snapshot reuse without reread or substitution, lifecycle, compatibility, privacy, tests, and documentation. Approval remains offline-only and does not cover vehicle execution."
  },
  "integration": {
    "status": "synchronized",
    "summary": "The reviewed stakeholder demo recovery, live preflight hardening, tests, documentation, and operational records are committed and synchronized to origin/main. All raw captures, host evidence, private databases, and helper scripts remain ignored and outside Git/GitHub."
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
