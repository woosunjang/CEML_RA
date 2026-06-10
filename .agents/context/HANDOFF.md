# Handoff

**Updated:** 2026-06-11 KST
**Status:** Rare-earth magnet proposal-seed readiness is implemented on
`codex/ceml-ra-proposal-seed-readiness`. Stale local runtimes were stopped on
2026-06-11 KST.

## Current Ground

```text
main
```

The repo now uses an internal `.git/` directory. The user may disable Dropbox
sync for the source folder:

```text
/Users/woosun/Dropbox/Dev/CEML_RA
```

Keep this artifact root Dropbox-synced:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts
```

## Read First

1. `AGENTS.md`
2. `docs/ceml-ra-ground-goal-and-phases.md`
3. `.agents/context/TASK_LOG.md`
4. `git status --short --branch`

## Live Direction

CEML_RA is being rebuilt as a PhD-level integrated research colleague with
long-term memory, not as an automatic report tool or status dashboard. The
ground contract is:

```text
docs/ceml-ra-ground-goal-and-phases.md
```

The Phase 1 memory-spine implementation is:

```text
lab-orchestrator/orchestrator/research_thread.py
lab-orchestrator/tools/seed_research_threads.py
lab-orchestrator/orchestrator/scout_thread_adapter.py
lab-orchestrator/tools/scout_evidence_to_thread.py
lab-orchestrator/orchestrator/research_coordinator.py
lab-orchestrator/tools/research_coordinator_dry_run.py
lab-orchestrator/api/server.py
```

Initial topics remain:

- `materials_ontology_kg`
- `rare_earth_magnets`

The next small product decision is whether to fill the remaining GBD/recycling
source-value gaps for proposal seeding or first add a reviewable
`research_thread` patch CLI if another thread-writing artifact is needed.

KG ingest preview work is deferred until the question factory, evidence brief,
and idea matrix artifacts show what is worth remembering.

Test Chunk 1 artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_1_question_factory/
```

Test Chunk 2 artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_2_evidence_briefs/
```

Goal 3 artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_3_partner_transcript/
```

Goal 4 artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_4_automation_backlog/
```

Route-ranking artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/route_ranking_extraction_sheet/
```

Proposal-seed readiness artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/proposal_seed_readiness/
```

The proposal-seed readiness pass keeps the existing route-ranking sheet as prior
reviewed memory. It confirms primary recycling values for Br, BHmax, HcJ,
renewed Tb-foil GBD, and high-temperature property checks, while keeping final
GBD Br/BHmax as explicit `not_found` source gaps. The next product chunk can be
a bounded proposal-seed artifact. If the next chunk will mutate research_thread
again, first add a small reviewable `research_thread_patch_cli`; route-ranking
and proposal-readiness both needed one-off thread updates.

Do not add live KG/RAG writes, mutation endpoints, runtime restarts, Slack
messages, or writes to Scout DB, Qdrant, Neo4j, or Graphiti for the next chunk.

Do not begin with internal autonomy machinery, old mission flows, old audit
findings, old schedule plans, dashboard/status slices, or Sprint Executor
revival unless the user explicitly redirects.

## Runtime Baseline

The old Mac Mini runtime and watchdog-style surfaces are intentionally stopped.
Do not infer current product state from a previously open localhost port,
stale Slack alerts, old launchd plists, or old API docs. Restarting services is
a future explicit baseline task, not part of the current ground contract.

## Sealed Historical Material

Old branches, old stashes, old autonomy-pulse artifacts, old schedule plans,
old generated/ops reports, and old reset/audit narratives are historical only.
They should not be read or used as default context.

The old local branches and preserved stash were deleted after explicit user
approval. Historical material remains only in the full archive and Git history.

## Guardrails

- Do not push without explicit approval.
- Do not delete local branches or stashes without explicit approval.
- Do not mutate live DB/KG/RAG/Scout state during planning.
- Do not restart services during planning or cleanup.
- Do not restart the stopped Mac Mini runtime unless the user explicitly asks.
- Do not run Sprint Executor, active mission next-actions, or backlog mutation
  commands by default.
- Do not count read-only observation as research progress.
