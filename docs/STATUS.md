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
  "updated_at": "2026-09-29T00:51:16-07:00",
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
    "summary": "The private 30-minute-candidate database was transferred to this workstation outside Git and copied into the ignored repository root with byte-for-byte verification. A read-only audit reconfirmed one finalized 568.64-second session with 2,716 rows, 2,715 good rows, one terminal vehicle-speed timeout, no foreign-key or chronology violations, valid pre-error decoded domains, no route or request metadata, and no raw exchanges. The timeout row followed a 2.094-second inter-row gap versus a 0.344-second largest earlier gap, consistent with the configured two-second HSFZ response deadline; the decoded-only database cannot identify why the response deadline expired.",
    "at": "2026-09-29T00:51:16-07:00",
    "evidence": [
      "docs/research.md",
      "docs/safety.md",
      "supra_telemetry/client_dashboard.py",
      "supra_telemetry/hsfz.py",
      "tests/test_drive_session.py"
    ]
  },
  "next_action": {
    "summary": "Keep the private database local and preserve the no-retry boundary. The offline audit has isolated a two-second HSFZ response-deadline expiration but cannot distinguish ECU delay, missing or partial response, control-only traffic, or a cable, adapter, or network interruption. Any proposed vehicle retry or narrowly filtered private capture requires a new bounded procedure and independent review before vehicle use.",
    "owner": "lead",
    "reference": "docs/safety.md"
  },
  "attention": [
    "The one-time stationary recording authorization has been consumed and passed; do not repeat it.",
    "The one-time 60-second moving authorization has been consumed and passed; do not repeat it.",
    "The one-time 300-second authorization was consumed and failed its then-current artificial speed-ceiling audit; do not repeat it.",
    "The one-time 30-minute normal-driving authorization was consumed and stopped on a vehicle-speed timeout after 568.64 seconds; do not repeat it.",
    "No vehicle command or raw-capture run is currently authorized.",
    "The private moving-recording-30min.sqlite file is present in this repository root, remains Git-ignored, and must stay outside Git/GitHub."
  ],
  "architecture": {
    "status": "aligned",
    "summary": "The telemetry and safety architecture is unchanged. A compiled React frontend is served by the existing loopback-only Python server, and the privacy-safe /api/state contract remains the sole browser data source. The installed Python runtime remains standard-library-only.",
    "reference": "docs/architecture.md"
  },
  "verification": {
    "status": "partial",
    "summary": "The copied artifact matches its private transfer source, SQLite integrity and foreign-key checks pass, the session is finalized, all 2,716 rows are chronological, decoded-domain and privacy checks pass, and the single timeout is the terminal row. The 2.094-second terminal gap is consistent with the configured two-second response deadline. Root cause below the allowlisted timeout category remains unverified because no raw exchange or packet capture exists.",
    "verified_at": "2026-09-29T00:51:16-07:00"
  },
  "review": {
    "status": "not_started",
    "summary": "The approved one-time procedure was consumed. No new procedure exists to review. A retry with private packet capture would be a new procedure and is not authorized until its capture scope, privacy handling, bounds, and stop conditions are independently reviewed."
  },
  "integration": {
    "status": "unmerged",
    "summary": "The offline audit documentation is a local tracked change not yet committed or synchronized. The private SQLite database remains ignored and must stay outside Git/GitHub."
  },
  "handoff": {
    "summary": "The one-time 30-minute candidate stopped fail-closed after 568.64 seconds on a vehicle-speed timeout; no retry is authorized. Its private database is now present locally and ignored by Git. Offline evidence isolates expiration of the configured two-second HSFZ response deadline but cannot identify the underlying ECU, response, link, adapter, cable, or network cause without new evidence."
  }
}
---

# Project handoff

Vehicle communication must remain strictly read-only and limited to reviewed,
explicitly verified requests. Private captures and vehicle or network identifiers
remain local and ignored. See `docs/PROJECT_HISTORY.md` for verified milestones,
`docs/safety.md` for vehicle-test boundaries, and `docs/roadmap.md` for future work.
