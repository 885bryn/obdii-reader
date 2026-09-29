# Project Status Contract v1

This repository adopts Codex Project Status Contract v1. This document is the
on-demand schema guidance for the operational records; it is not necessary to
read it for every trivial task. `docs/STATUS.md` is the canonical semantic
operational status, and `docs/PROJECT_HISTORY.md` is the concise, append-only
human-readable record of meaningful verified milestones. Reviewed
Git/GitHub remains authoritative for implemented history. Live Git supplies
branch, commit, upstream, and worktree state.

## Ownership and update cadence

- Only the Lead/coordinating agent edits `docs/STATUS.md` and
  `docs/PROJECT_HISTORY.md`. Workers and reviewers return verified findings to
  the Lead and do not edit those files.
- Record only verified accomplishments; planned work belongs in
  `next_action`.
- Check status at meaningful work start, after a status update, and before
  durable handoff, rather than on every command or tool call.
- Update status at task start, meaningful milestones, blockers, architecture
  drift, completed verification, before durable handoff/final response, and
  after review, merge, or synchronization when applicable.
- History is not a second live status tracker. Do not duplicate current
  task/status, next action, blockers/attention, workflow stage, or handoff
  there.

## Project history

Keep `docs/PROJECT_HISTORY.md` as an oldest-to-newest table with exactly these
columns: `Completed | ID | Milestone | Verified outcome | Evidence`. Add an
entry only for a meaningful verified milestone or completed task, not for every
commit or session. Link to repository-relative evidence or commit references.
Do not include secrets or private raw data. If an entry needs correction or is
superseded, make that explicit rather than silently rewriting history.

Keep detailed implementation history in Git/reviewed GitHub, and requirements,
reasoning, and evidence in their F###/T###, decision, and evidence documents.

## Exact vocabulary

Contract v1 uses a closed vocabulary in structured fields. Never invent aliases,
compound owners, or prose values; put nuance in adjacent summary text instead.

| Field | Allowed values |
| --- | --- |
| `project_state` | `planning`, `active`, `blocked`, `paused`, `dormant`, `completed` |
| `workflow_stage` | `discovery`, `planning`, `implementation`, `verification`, `review`, `merge`, `synchronization`, `handoff`, `idle`, `complete` |
| `health` | `healthy`, `attention`, `blocked`, `unknown` |
| task `status` | `planned`, `in_progress`, `implemented`, `verified`, `reviewed`, `merged`, `closed`, `blocked`, `paused` |
| action/attention `owner` | `lead`, `user`, `external` |
| attention `kind` | `blocker`, `decision` |
| architecture `status` | `aligned`, `drift_detected`, `unknown` |
| verification `status` | `not_run`, `in_progress`, `passed`, `partial`, `failed`, `not_applicable` |
| review `status` | `not_required`, `not_started`, `in_progress`, `changes_requested`, `approved` |
| integration `status` | `not_applicable`, `unmerged`, `merged`, `synchronized` |

Every verification object includes `verified_at`: an RFC3339 timestamp when
verification is complete, or `null` while there is no completed verification
timestamp.

## Coupled states

- A blocked project state and blocked health travel together and require an
  attention record.
- A completed project requires workflow stage `complete`, no next action, and
  no attention.
- Every non-completed project requires a next action.
- `review_after` is used only for paused or dormant work.
- Task status `verified`, `reviewed`, or `merged` requires the corresponding
  passed verification, approved review, or merged integration evidence.
- Keep all coupled fields coherent when updating status; do not record a
  milestone as complete before its evidence exists.

Routine Lead-authored edits using this vocabulary do not need a separate
schema-validation pass. Validate during initial adoption or schema migration,
after manual/external edits, or when a Contract reader reports an error. Never
claim validity merely from the contract name and schema version.

## Explicit migration

Migration is explicit and one-time. A repository must opt in locally; missing
or legacy status is reported and is not rewritten automatically. For a migrated
repository, split any legacy mixed progress document into current state in
`docs/STATUS.md`, verified milestones in `docs/PROJECT_HISTORY.md`, and durable
procedures or decisions in their canonical documents. After checking that
information has been preserved, retire the legacy mixed tracker.

Do not impose this contract on an inherited repository that already has a
stronger authoritative system. Adopt it explicitly, generate it from the native
system, or leave the repository unsupported rather than maintaining two
competing sources.
