# Handoff

**Updated:** 2026-06-28 KST
**Current checkout:** `codex/ceml-ra-weekly-useful-loop`

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

- Repo root currently has an untracked nested `CEML_RA/` directory. Do not stage
  it. Inspect and remove or ignore it only as a separate cleanup task after the
  user confirms the intended disposition.
- Keep M2 code checkout under `/Users/mersoom/Dev/CEML_RA`; do not use the old
  Dropbox source path as the executable repo path.

## Current Code Boundary

`Weekly Useful Research Loop v0` is the first product-facing path. It now
supports `materials_ontology_kg` and `rare_earth_magnets`, and can read
`research_thread`, Scout, RAG, KG, and prior memory notes, then write a weekly
brief, reusable memory note, `research_thread` update, and Graphiti/Qdrant
memory writes when `execute=true`.

`Weekly Brief Quality v1` is the existing weekly output contract: the brief
should show new evidence, reused memory, judgment change, weak/deferred claims,
next-week questions, recommended checks, and reuse provenance across
`RA_artifacts`, Qdrant, and Graphiti. It is not the current next-step boundary.

`Weekly Loop Evidence Separation v1` keeps Qdrant/Graphiti
`research_memory_note` hits out of `new_evidence`. Internal memory hits belong
in `memory_reuse_sources`; only Scout papers, external RAG documents, and fresh
KG facts count as new evidence.

`On-demand Research Question Loop v0` is the current feature-first expansion.
It answers a user question from the same thread/artifact/Scout/RAG/KG memory,
writes a Korean answer artifact, reusable memory note, question-based work
package draft, `research_thread` update, and Graphiti/Qdrant memory writes when
`execute=true`. LLM synthesis is the default; failures fall back to deterministic
Korean artifacts with `synthesis_mode: fallback`.

Scheduler, Slack notification, runtime service registration, and new review UI
remain deferred. Do not drift back into selection/summarization-only polish
until the two-thread question -> answer -> work package -> memory reuse path is
accepted on M2.

## Boundaries

- Do not push without explicit approval.
- Do not delete local branches or stashes without explicit approval.
- Do not mutate live Slack, runtime services, Scout DB, Qdrant, Neo4j,
  Graphiti, KG, or RAG stores without explicit approval.
- Do not treat `RA_artifacts` as source code.
- Do not restart the stopped Mac Mini runtime unless the user explicitly asks.
