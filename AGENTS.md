# Repository workflow and safety boundaries

This repository adopts Codex Project Status Contract v1.
This repository uses Workflow 2.3.

## Workflow

- The Lead owns intent, architecture, scope, safety, planning, operational tracker records, delegation, verification, and final acceptance.
- Delegate meaningful bounded work to a GPT-6 Luna implementer with a concise execution contract. Luna returns evidence and never edits `docs/STATUS.md` or `docs/PROJECT_HISTORY.md`. After two evidence-based failed attempts at the same bounded issue, escalate to GPT-6 Sol Medium; escalate earlier for architecture or scope uncertainty.
- Use independent review when risk or uncertainty warrants it, or when requested. Ask the user about outcomes and consequential choices, not routine implementation details.
- This workflow instruction change authorizes offline file work only; no vehicle execution or vehicle-facing commands of any kind are authorized. Active status remains offline-only.
- See `docs/PROJECT_STATUS_CONTRACT.md` on demand for the Project Status Contract v1 schema and migration guidance; it need not be read for every trivial task.

## Project records

- `docs/STATUS.md` is the current project snapshot: active task, latest verified accomplishment, next action, blockers, and current verification/review state.
- `docs/PROJECT_HISTORY.md` is an append-only record of meaningful, verified milestones. It is not a second status tracker.
- Git history and detailed task, decision, research, and test documents are the technical evidence and detailed history.
- Only the Lead/coordinating agent edits `docs/STATUS.md` and `docs/PROJECT_HISTORY.md`. Subagents return verified findings to the Lead.
- Do not record an accomplishment until its evidence is verified. Keep history concise, dated, and free of vehicle identifiers or raw data.
- Before continuing on either computer, pull the shared branch and read both operational records plus the relevant safety and test documents. After a verified milestone, reconcile the records, inspect for private identifiers, and commit and push the related changes before work continues on the other computer.

## Vehicle and privacy boundaries

- Vehicle communication must remain strictly read-only. Never write, code, flash, change configuration, clear faults, run routines or actuators, use security access, reset modules, or use upload/download services.
- Do not guess or infer vehicle, ECU, network, or interface addresses. Use only routing supported by evidence verified on this vehicle and documented in the project; do not copy community examples as vehicle facts.
- Empirical vehicle results must be distinguished from software tests, protocol references, and inference. State the exact bounded test and its limits; do not generalize a single run.
- Stop on an unexpected response, acquisition error, or vehicle warning. Do not retry, scan, reconnect, or expand a test unless a separately reviewed, bounded procedure permits it.
- Never put VIN, MAC, EID, GID, IP/interface addresses, raw packet bytes, or unredacted capture contents in tracked documentation, commits, or public reports. Keep private captures local and ignored by Git; report only redacted outcomes.
