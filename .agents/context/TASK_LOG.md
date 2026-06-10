# Task Log

## 2026-06-11 — Completed Test Chunk 1 Research Question Factory

**Status:** Complete on `codex/ceml-ra-test-chunk-1-question-factory`.

Generated durable Research Question Factory artifacts for:

```text
materials_ontology_kg
rare_earth_magnets
```

Artifact root:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_1_question_factory/
```

Each topic has 10 fresh question candidates, source/domain signals, do-not-copy
checks, and top two recommendations. The durable research_thread artifacts
were updated only with decisions and next actions. No literature claims were
accepted, and no Scout DB, Qdrant, Neo4j, Graphiti, Slack, or runtime services
were mutated.

Next product step: Test Chunk 2, evidence briefs and idea matrices from the
selected question-factory outputs.

## 2026-06-11 — Realigned post-Chunk-4 validation direction

**Status:** Complete on `codex/ceml-ra-test-plan-realign`.

After Chunk 4, the repo still pointed to a KG ingest preview as the next
product step. That was premature for the current validation plan. The next
product step is now Test Chunk 1: Research Question Factory for:

```text
materials_ontology_kg
rare_earth_magnets
```

KG ingest preview work is deferred until useful question, evidence-brief, and
idea-matrix artifacts prove what should be remembered. Do not write to live
Neo4j, Graphiti, Qdrant, Scout DB, Slack, or runtime services.

## 2026-06-11 — Implemented read-only research_thread review API

**Status:** Complete on `codex/ceml-ra-thread-review-api`.

The Chunk 4 API exposes research_thread artifacts through read-only endpoints:

```text
GET /research/threads
GET /research/threads/{thread_id}
GET /research/threads/{thread_id}/markdown
```

No POST, PUT, or DELETE mutation endpoints were added.

Implementation:

```text
lab-orchestrator/api/server.py
lab-orchestrator/tests/test_research_thread_api.py
```

Next product step was later corrected to Test Chunk 1: Research Question
Factory. KG ingest preview is deferred until research-value artifacts prove
what should be remembered. Do not write to live Neo4j, Graphiti, Qdrant, Scout
DB, Slack, or runtime services.

## 2026-06-11 — Implemented Coordinator dry-run loop

**Status:** Complete on `codex/ceml-ra-coordinator-dry-run`.

The Chunk 3 coordinator advances local `research_thread` artifacts through
Scout, evidence synthesis, idea candidate, critique, and next-action stages.
It is deterministic and does not call LLMs, Slack, KG/RAG stores, Scout writes,
or runtime services.

Implementation:

```text
lab-orchestrator/orchestrator/research_coordinator.py
lab-orchestrator/tools/research_coordinator_dry_run.py
lab-orchestrator/tests/test_research_coordinator.py
```

The CLI defaults to dry-run. `--execute` updates only local research_thread
JSON and Markdown artifacts.

Next product step: Chunk 4, read-only review surface for research_thread
artifacts.

## 2026-06-11 — Implemented Scout evidence to research_thread adapter

**Status:** Complete on `codex/ceml-ra-scout-thread-adapter`.

The Chunk 2 adapter converts read-only Scout paper metadata into
`research_thread` source signals and evidence previews.

Implementation:

```text
lab-orchestrator/orchestrator/scout_thread_adapter.py
lab-orchestrator/tools/scout_evidence_to_thread.py
lab-orchestrator/tests/test_scout_thread_adapter.py
```

The CLI defaults to dry-run. `--execute` updates only the existing
research_thread JSON and Markdown artifacts. It does not mutate Scout DB,
Qdrant, Neo4j, Graphiti, Slack, or runtime services.

Next product step: Chunk 3, Coordinator dry-run loop using local artifacts
only.

## 2026-06-11 — Implemented Phase 1 research_thread core

**Status:** Complete on `codex/ceml-ra-research-thread-core`.

The Phase 1 core memory spine now has durable `research_thread` JSON and
Markdown artifacts, a dry-run-by-default seed CLI, and focused tests.

Implementation:

```text
lab-orchestrator/orchestrator/research_thread.py
lab-orchestrator/tools/seed_research_threads.py
lab-orchestrator/tests/test_research_thread.py
```

The default seed topics are:

```text
materials_ontology_kg
rare_earth_magnets
```

The seed artifacts contain ground-contract source signals, first-proof-loop
decisions, concrete next research questions, and a KG preview guardrail. They
do not contain fake literature claims or mutate live Scout, Qdrant, Neo4j,
Graphiti, Slack, or runtime state.

Next product step: Chunk 2, Scout evidence to research_thread adapter.

## 2026-06-11 — Collapsed docs to the ground contract

**Status:** Complete on `codex/ceml-ra-ground-contract`.

After the hard reset, the user asked to remove confusing old documentation and
stop treating stale local runtime surfaces as product truth.

The `docs/` directory now keeps only:

```text
docs/README.md
docs/ceml-ra-ground-goal-and-phases.md
```

The standalone operational planning documents were removed. Their
still-current source, artifact, and runtime rules were folded into the ground
contract.

## 2026-06-11 — Stopped stale Mac Mini runtime

**Status:** Complete.

Runtime cleanup completed:

- stale `uvicorn api.server:app` on `127.0.0.1:8000` was terminated;
- no CEML_RA launchd labels were loaded at cleanup time;
- CEML_RA-related local service ports `3000`, `8000`, `6333`, `6379`, `7474`,
  and `7687` were verified closed;
- Apple `/usr/libexec/watchdogd` was left alone because it is an OS process,
  not a CEML_RA runtime.

Do not restart the stopped Mac Mini runtime unless the user explicitly asks.

## 2026-06-11 — Added ground goal and phased rebuild contract

**Status:** Complete.

The Phase 0 ground contract is:

```text
docs/ceml-ra-ground-goal-and-phases.md
```

It defines CEML_RA as a PhD-level integrated research colleague with long-term
memory, not an automatic report tool. It fixes the role split between
`RA_artifacts`, Neo4j + Graphiti, and Qdrant, and makes `research_thread` the
next memory-spine target.

## 2026-06-10 to 2026-06-11 — Source reset and artifact preservation

**Status:** Complete.

Source was reset onto clean `main`, old live context was purged, and the
current source tree uses an internal `.git/` directory.

The pre-cleanup source archive remains under the durable artifact root:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/source_archives/CEML_RA_full_with_gitdir_20260610_220548.tar.gz
```

Keep `/Users/woosun/Dropbox/Dev/CEML/RA_artifacts` as the durable artifact
location. Live DBs, logs, caches, command queues, service state, and local
`.env` files stay host-local and out of git.
