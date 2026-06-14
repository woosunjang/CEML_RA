# Handoff

**Updated:** 2026-06-14 KST
**Current checkout:** `main`

## Start Here

Repo-local truth wins over Codex global memory for CEML_RA. Do not infer the
next development direction from old Codex memory, old runtime evidence, old
proposal artifacts, or planner output.

Read in this order:

1. `AGENTS.md`
2. `.agents/context/TASK_LOG.md`
3. `.agents/context/REMOTE_ENVIRONMENT.md`
4. `docs/ceml-ra-ground-goal-and-phases.md`
5. `docs/ceml-ra-research-loop-contract-v1.md`
6. `git status --short --branch`
7. `git log --oneline --decorate --graph --all -30`

## Current Direction Boundary

CEML_RA is being rebuilt as a PhD-level integrated research colleague with
long-term memory, not as an automatic report tool or status dashboard.

Recent rare-earth artifacts, proposal-seed artifacts, thread patch tooling, and
the Research Work Package Planner exist as usable tools and prior context. They
are not the next roadmap unless the user explicitly chooses that direction.

If repo-local docs and Codex memory disagree, trust the repo-local docs and
clean context before feature work.

## Open Cleanup TODO

- `Subagent Output Envelope v1` has been fast-forwarded into local `main`, and
  the merged local `codex/ceml-ra-subagent-output-envelope` branch was removed
  with normal `git branch -d`. `origin/main` has not been pushed past
  `0a5b274` because push requires explicit user approval.
- The prior linear branch stack has been promoted to `main`, pushed to GitHub,
  and local checkpoint branches were removed with normal `git branch -d`.
- Clean Codex memory Markdown/index files when the environment permits direct
  memory maintenance:
  - `/Users/woosun/.codex/memories/memory_summary.md`
  - `/Users/woosun/.codex/memories/MEMORY.md`
- Remove stale CEML_RA memory references to old 2-week/RQF plans, old
  autonomy/runtime work, rare-earth proposal follow-ons, HRE table suggestions,
  descriptor table suggestions, and Work Package Planner output as an implied
  next step.

## Current Code Boundary

`Research Loop Packet v1` turns a selected `research_thread`, trigger context,
candidate subagent roles, expected outputs, stop conditions, artifact
candidates, and thread patch preview into dry-run-first Markdown/JSON planning
artifacts.

`Subagent Output Envelope v1` lets a selected loop-packet role return an
explicitly supplied, Korean-first, reviewable JSON/Markdown envelope plus a
thread patch preview. It does not execute subagents, call LLMs, create research
claims, mutate `research_thread`, or touch live stores.

## Boundaries

- Do not push without explicit approval.
- Do not delete local branches or stashes without explicit approval.
- Do not mutate live Slack, runtime services, Scout DB, Qdrant, Neo4j,
  Graphiti, KG, or RAG stores without explicit approval.
- Do not treat `RA_artifacts` as source code.
- Do not restart the stopped Mac Mini runtime unless the user explicitly asks.
