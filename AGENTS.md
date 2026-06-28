# CEML_RA Codex Operating Instructions

These instructions are for Codex while developing this repository. They are not
runtime prompts for the application's internal agents. Keep this file as the
canonical repo-local instruction surface; do not keep a separate `GEMINI.md`
agent surface unless the user explicitly asks for one.

## Ground Direction

- CEML_RA is being rebuilt as a PhD-level integrated research colleague with
  long-term memory, not as an automatic report tool or status dashboard.
- The product ground contract is `docs/ceml-ra-ground-goal-and-phases.md`.
- The loop-level operating contract is
  `docs/ceml-ra-research-loop-contract-v1.md`.
- Current source of truth for source code is GitHub.
- Durable artifacts and portable knowledge snapshots live under:

  ```text
  /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
  ```

- The Phase 1 memory spine, Scout evidence adapter, Coordinator dry-run loop,
  read-only review API, rare-earth route-ranking sheet, and rare-earth
  proposal-seed readiness pass, reviewable research-thread patch CLI, and
  rare-earth proposal-seed artifact now exist.
- Recent proposal and work-package planning artifacts are available tools and
  historical context, not an implied roadmap. Do not infer the next product step
  from them unless the user explicitly selects that direction.
- Research Loop Packet v1 and Subagent Output Envelope v1 are the current
  dry-run-first code boundaries for planning one loop and returning selected
  role outputs without mutating research_thread or live stores.
- KG ingest preview remains deferred until research-value artifacts prove what
  should be remembered.
- Treat old autonomy-pulse branches, old mission IDs, Sprint Executor history,
  old generated/ops artifacts, old schedules, old local runtime surfaces, and
  old audit documents as sealed historical material unless the user explicitly
  asks for a specific artifact.

## Memory And Context Precedence

- Repo-local truth wins over Codex global memory for this project.
- Do not use Codex memory to choose the next CEML_RA roadmap item.
- If Codex memory mentions old 2-week/RQF plans, old autonomy/runtime work,
  rare-earth proposal follow-ons, HRE tables, descriptor tables, or Work Package
  Planner output as a next step, treat those memories as stale.
- Start each CEML_RA planning or implementation task from this repo's current
  files, current branch graph, and the user's latest instruction.
- If repo-local docs and memory disagree, clean the repo-local docs and context
  before feature work.

## Read First

1. `.agents/context/HANDOFF.md`
2. `.agents/context/TASK_LOG.md`
3. `.agents/context/REMOTE_ENVIRONMENT.md`
4. `docs/ceml-ra-ground-goal-and-phases.md`
5. `docs/ceml-ra-research-loop-contract-v1.md`
6. `git status --short --branch`

## Storage And Runtime Boundaries

- Use `CEML_RA_ARTIFACTS_DIR` when code should write durable artifacts.
- Keep the in-repo `generated/` fallback for local development and tests.
- Live databases, logs, caches, command queues, Docker volumes, service state,
  and local `.env` files stay host-local and out of git.
- Do not move live SQLite, Neo4j, Qdrant, Scout DBs, logs, caches, queues, or
  service state into Dropbox.
- Remote host details live in `.agents/context/REMOTE_ENVIRONMENT.md`; that file
  is reference material, not permission to restart services or mutate live
  stores.

## Artifact Language Policy

- Strong default: anything the user is expected to read as a research/product
  artifact must be written in Korean unless the user explicitly asks for
  English or the artifact is intentionally prepared for an external
  English-language audience.
- This especially applies to Markdown files, evidence briefs, idea matrices,
  proposal seeds, review summaries, local Slack-style transcripts, decisions,
  failure modes, next actions, tables, and explanatory prose.
- For Markdown/JSON artifact pairs, Markdown must be Korean-first. JSON schema
  keys, stable IDs, route IDs, source IDs, file paths, URLs, DOI titles, CLI
  flags, API names, code, tests, logs, and runtime/operations files may remain
  English.
- JSON values that are user-facing narrative, such as `text`, `decision`,
  `claim_boundary`, `current_support`, `main_gap`, `proposal_role`,
  `next_actions`, or summary fields, should also be Korean-first.
- Technical terms may remain in English when they are standard in the research
  context, but the surrounding sentence should be Korean. Before finishing any
  user-readable Markdown artifact, reread headings, tables, decisions, failure
  modes, and next actions to confirm they follow this policy.

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
- Do not count Codex manually authoring another research artifact as product
  progress once a repeated artifact shape is known; turn the shape into a
  reusable planner, runner, or reviewable preview first.
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

## Verification And Reporting

- For backend changes, run focused Python compile checks and relevant unit tests
  when available.
- For path/storage changes, verify env-var path resolution and fallback
  behavior.
- For plist changes, run `plutil -lint`.
- For frontend changes, run focused lint/build checks where practical.
- If verification cannot be run, state why and provide the best narrower check
  that was run instead.
- Report files changed, verification performed, remaining risks, and the next
  small action.
