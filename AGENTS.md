# CEML_RA Codex Operating Instructions

These instructions are for Codex while developing this repository. They are not
runtime prompts for the application's internal agents.

## Current Direction

CEML_RA has been reset from `main` for a clean rebuild.

The ground product goal is now defined by:

```text
docs/ceml-ra-ground-goal-and-phases.md
```

CEML_RA is a PhD-level integrated research colleague with long-term memory,
not an automatic report tool or status dashboard. Automatic weekly work,
on-demand research discussion, KG/RAG memory, artifacts, proposal writing, and
project management must share one accumulated research context.

Treat old autonomy-pulse branches, old mission IDs, Sprint Executor history,
proposal backlog pressure, generated/ops artifacts, old schedule plans, and
old audit documents as sealed historical material. Do not inspect, restore,
reuse, cherry-pick, or summarize them unless the user explicitly asks for a
specific artifact.

The live direction is:

1. GitHub is the source of truth for source code.
2. Durable artifacts and portable knowledge snapshots live under:

   ```text
   /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
   ```

3. Live databases, logs, caches, command queues, Docker volumes, service state,
   and local `.env` files stay host-local and out of git.
4. Product validation follows the ground goal. Do not use old standalone
   planning, API, Slack, deployment, architecture, or runtime-operation docs as
   current direction.

The Phase 1 core memory spine now exists as durable `research_thread` JSON and
Markdown artifacts, and the Scout evidence adapter can convert read-only Scout
paper metadata into `research_thread` source signals and evidence previews.
The Coordinator dry-run loop can now update research_thread artifacts through
Scout, evidence synthesis, idea candidate, critique, and next-action stages
using local artifacts only, and the read-only review API can expose those
artifacts.

Test Chunk 1 generated Research Question Factory artifacts, and Test Chunk 2
generated evidence briefs and idea matrices for `materials_ontology_kg` and
`rare_earth_magnets`. The next product step is Goal 3: a local Slack-style
research partner transcript that challenges one selected idea without sending
Slack messages. KG ingest preview work is deferred until these research-value
artifacts prove what should be remembered. Do not begin with internal autonomy
machinery, old mission flows, status-reporting slices, Slack, or live KG/RAG
writes.

## Read First

1. `.agents/context/HANDOFF.md`
2. `.agents/context/TASK_LOG.md`
3. `docs/ceml-ra-ground-goal-and-phases.md`
4. `git status --short --branch`

## Source, Artifact, And Runtime Boundaries

- Use `CEML_RA_ARTIFACTS_DIR` for the artifact root when running code that
  should write durable artifacts.
- Keep the in-repo `generated/` fallback for local development and tests.
- Snapshot/export operations must be explicit, reviewable, and non-destructive.
- Do not move live SQLite, Neo4j, Qdrant, Scout DBs, logs, caches, queues, or
  service state into Dropbox.

## Git Guardrails

- Canonical source branch: `main`.
- Do not push without explicit approval.
- Do not delete local branches or stashes without explicit approval.
- Do not use old branches or stashes as development context unless the user
  explicitly asks.
- Never commit secrets, local environment files, databases, logs, generated
  runtime artifacts, caches, command queues, or conflict copies.

## Runtime And Operations Guardrails

- Do not restart services during planning or repository cleanup.
- Do not mutate live DB/KG/RAG/Scout state during planning or baseline setup.
- Do not run Sprint Executor, active mission next-actions, or backlog mutation
  commands by default.
- Do not block API or Slack handlers with long-running work; prefer queues,
  workers, bounded memory, and artifact references.

## Development Contract

- Optimize for research value, not observation volume.
- Preserve the integrated research colleague spirit before adding features.
- Prefer research-thread memory progress over isolated reports, dashboards, or
  agent outputs.
- Prefer one useful research artifact over many status reports.
- Do not count read-only observation as product progress.
- Add a new report surface only if it clearly advances a research thread or
  reuses accumulated memory.
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

- For backend changes, run focused Python compile checks and relevant unit
  tests when available.
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
