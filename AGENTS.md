# CEML_RA Codex Operating Instructions

These instructions are for Codex while developing this repository. They are not
runtime prompts for the application's internal agents.

## Current Operating Direction

CEML_RA is being reset for a cleaner, main-derived rebuild.

Do not treat the old autonomy-pulse branch, old mission IDs, Sprint Executor
next actions, proposal backlog pressure, or generated/ops report artifacts as
the default development direction. They are historical reference only.

The near-term goal is not the two-week research-value feature cycle itself. The
near-term goal is to make that cycle possible by first completing repository and
storage cleanup:

1. Separate source code from Dropbox sync and use GitHub as code source of
   truth.
2. Keep durable artifacts and portable knowledge snapshots under a Dropbox
   artifact root.
3. Keep live runtime state host-local.
4. Continue from this `main`-derived Stage 0 branch.
5. Audit old read-only writer/report/probe surfaces before reusing them.

Read first:

1. `.agents/context/HANDOFF.md`
2. `.agents/context/TASK_LOG.md`
3. `docs/ceml-ra-main-rebuild-development-goal-2026-06-10.md`
4. `git status --short --branch`

## Agent Harness

Use the lightweight agent harness when it helps, but do not let old harness
history override the reset direction.

- Non-trivial work: use `.agents/harness/quick-check.md` internally when it is
  present and relevant.
- Large, risky, multi-component, KG/RAG, Scout, Slack, API, worker, deployment,
  or research-evidence work: use a change-plan pass before implementation.
- Operational, launchd, DB, Docker, `.env`, Slack, or deployment work: perform
  narrow guard checks first.
- Handoff updates should stay short. Long runtime narratives should not be
  reintroduced into live context files.

## Source, Artifact, And Runtime Boundaries

GitHub should be the source of truth for code.

Dropbox should sync durable artifacts and portable knowledge snapshots only.
The planned artifact root is:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts
```

Live databases, logs, caches, command queues, Docker volumes, service state,
and local `.env` files must stay out of Dropbox sync and out of git.

The rebuild should reintroduce only minimal artifact-root support first:

- external env var: `CEML_RA_ARTIFACTS_DIR`
- internal constant: `ARTIFACTS_DIR`
- fallback to in-repo `generated/` when the env var is unset
- focused tests for path resolution and fallback behavior
- documentation that distinguishes source, artifacts, live runtime data, and
  exported snapshots

Do not migrate every old read-only writer into the artifact root. Old writers
must be audited before reuse.

## Git And Worktree Guardrails

- This branch is intended to be the same-folder, main-derived Stage 0 branch.
- Treat old branches as reference archives unless explicitly told otherwise.
- Do not push without explicit approval.
- Do not run destructive git commands unless explicitly requested.
- Do not revert user or previous-session changes unless explicitly requested.
- Keep commits small and intentional.
- Never commit secrets, local environment files, DBs, logs, caches, generated
  runtime artifacts, command queues, or conflict copies.

## Runtime And Operations Guardrails

- Do not restart services during planning or repository cleanup.
- Do not mutate live DB/KG/RAG/Scout state during planning or baseline setup.
- Do not run Sprint Executor, active mission next-actions, or backlog mutation
  commands by default.
- Do not place live SQLite, Neo4j, Qdrant, or Scout databases in Dropbox.
- Snapshot/export commands must be explicit, reviewable, and non-destructive.

## Development Contract

- Optimize for research value, not observation volume.
- Prefer one useful artifact over many status reports.
- Do not count read-only observation as product progress.
- Add a new report surface only if it replaces or consolidates an older one.
- Keep API, workers, UI, Scout/RAG/KG, docs, and artifact contracts aligned.
- Inspect nearby code and docs before editing.
- Keep changes scoped to the owner area being modified.
- Update docs when changing architecture, APIs, deployment commands, runtime
  data paths, job behavior, memory behavior, or artifact contracts.

## Subproject Boundaries

- `lab-orchestrator/` owns orchestration, API, Slack integration, background
  jobs, workers, memory, model routing, application agents, and UI backend
  contracts.
- `lab-paper-scout/` owns paper collection, analysis, ranking, Scout DB usage,
  and research brief generation.
- `lab-research-agents/` is legacy/reference RAG code. Do not refactor it
  unless the task explicitly targets it.
- `lab-orchestrator/ui/` owns the internal research operations UI.
- `docs/` should describe real operational state and decisions.
- `data/`, `logs/`, `generated/`, and command queues are runtime areas and
  should remain untracked unless a fixture is intentionally added.

## Verification

- For backend changes, run focused Python compile checks and relevant unit tests
  when available.
- For path/storage changes, verify env-var path resolution and fallback
  behavior.
- For plist changes, run `plutil -lint`.
- For frontend changes, run focused lint/build checks where practical.
- If verification cannot be run, state why and provide the best narrower check
  that was run instead.

Report work with:

- files changed
- verification performed
- remaining risks
- next small action
