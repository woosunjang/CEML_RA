# Task Log

## 2026-06-12 — Promoted baseline and drafted Research Loop Contract v1

**Status:** Complete on `codex/ceml-ra-research-loop-contract`.

Promoted the linear cleanup stack through:

```text
ae1cdc1 docs: prioritize repo-local context over stale memory
```

`main` and `origin/main` now point to that baseline. The merged local checkpoint
branches were removed with normal `git branch -d`:

```text
codex/ceml-ra-thread-patch-cli
codex/ceml-ra-proposal-seed-artifact
codex/ceml-ra-work-package-planner
```

Created `docs/ceml-ra-research-loop-contract-v1.md` to define how automatic and
on-demand research modes share `research_thread` memory, how Coordinator should
delegate to Scout, Literature/RAG, KG Memory, Evidence Critic, Writing, and
Project roles, and how loop outputs should return as patch previews, durable
artifacts, or explicit stop conditions.

No new rare-earth research artifact was created. No Slack, runtime, Scout DB,
Qdrant, Neo4j, Graphiti, KG/RAG, or durable artifact root state was mutated.

## 2026-06-12 — Tightened repo-local context against stale Codex memory

**Status:** Complete on `codex/ceml-ra-work-package-planner`.

Repo-local docs now explicitly state that CEML_RA must not infer the next
product direction from Codex global memory, old runtime evidence, old 2-week/RQF
plans, rare-earth proposal follow-ons, HRE table suggestions, descriptor table
suggestions, or Work Package Planner output.

`docs/README.md` was reduced to a short current-truth index instead of a
chronological implementation summary. `.agents/context/HANDOFF.md` was reduced
to a short boot note with cleanup TODOs. The pending memory-maintenance TODO is
to clean these Codex memory Markdown/index files when direct memory maintenance
is available:

```text
/Users/woosun/.codex/memories/memory_summary.md
/Users/woosun/.codex/memories/MEMORY.md
```

No runtime services, Slack surfaces, Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG
stores, or durable research artifacts were mutated.

## 2026-06-11 — Implemented Research Work Package Planner v1

**Status:** Complete on `codex/ceml-ra-work-package-planner`.

Implemented a dry-run-first planner that reads a proposal seed plus the matching
`research_thread` and produces a research work-package execution packet instead
of manually authoring another research artifact:

```text
lab-orchestrator/orchestrator/research_work_package.py
lab-orchestrator/tools/research_work_package_plan.py
```

The planner selects the next work package deterministically from proposal-seed
work packages and current open next actions. For the current rare-earth magnet
proposal seed it selects:

```text
hre_intensity_route_comparison
```

The output includes selected work package, selection rationale, source artifact
refs, artifact contract, claim boundaries, missing evidence, stop conditions,
and a `research_thread` patch preview. `--execute` writes only packet Markdown,
packet JSON, and patch-preview JSON under `research_work_packages/`; it does
not mutate the live research_thread. No Slack, runtime, Scout DB, Qdrant,
Neo4j, Graphiti, KG/RAG, or remote branch state was mutated.

## 2026-06-11 — Completed research-thread patch CLI and rare-earth proposal seed

**Status:** Complete on `codex/ceml-ra-proposal-seed-artifact`.

Implemented a small reviewable research-thread patch CLI:

```text
lab-orchestrator/orchestrator/research_thread_patch.py
lab-orchestrator/tools/research_thread_patch.py
```

The CLI defaults to dry-run, writes only with `--execute`, supports append and
status/metadata updates for `decisions`, `next_actions`, and `failure_modes`,
and keeps live-store mutation count at zero.

Generated durable proposal-seed artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/proposal_seed_artifact/
```

The seed is written in Korean for the user-readable narrative and keeps machine
keys/IDs in English. It advances the HRE-sparing rare-earth magnet idea into a
bounded proposal-review shape: FSPS HRE-free and Tb-Ga GBD HRE-lean are the
primary proposal-review comparison, digital-twin/ML is the calculation-scoping
lane, and recycling-linked reprocessing remains supporting circularity context
with an explicit added-Tb caveat.

Updated only the `rare_earth_magnets` research_thread using the new patch CLI:
`proposal_seed_readiness.draft_seed` and `proposal_seed_readiness.thread_patch_cli`
are now completed, and new next actions point to a one-page concept note,
HRE-intensity table, and digital-twin/ML descriptor table. No Slack, runtime,
Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG, or watchdog state was mutated.

## 2026-06-11 — Promoted rebuild chunks to main and cleaned local branches

**Status:** Complete on `main`.

Fast-forwarded `main` from `24c2536` to:

```text
a5de04b docs: update remote environment workflow
```

Pushed the promoted `main` to GitHub so `origin/main` is the current source of
truth for the rebuild state. All intermediate local `codex/ceml-ra-*` chunk
branches were deleted with normal `git branch -d` after confirming they were
merged into `main`; no force deletion, rebase, squash, or history rewrite was
used.

The chunk commits remain preserved in `main` history. At that time, a bounded
proposal-seed artifact was considered as a possible follow-on, but this entry is
historical and must not be used as the current roadmap.

## 2026-06-11 — Completed rare-earth magnet proposal-seed readiness

**Status:** Complete on `codex/ceml-ra-proposal-seed-readiness`.

Generated durable source-gap audit and proposal-readiness artifacts:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/proposal_seed_readiness/
```

The pass preserved the route-ranking sheet as prior reviewed memory and did not
overwrite it. The source-gap audit keeps final GBD Br/BHmax as explicit
`not_found` fields, confirms Tb-Ga GBD Hcj/process/HRE-content signals, and
confirms primary recycling values for Br 1.31 T, BHmax 328 kJ/m3, HcJ 1703
kA/m, renewed GBD with 1.5 wt.% Tb foil, and high-temperature restoration
signals. Missing data remains a gap, not negative proof.

The readiness artifact keeps FSPS HRE-free and GBD HRE-lean routes in the
proposal-review lane, digital-twin/ML in calculation-scoping, and recycling as
supporting circularity context rather than a primary HRE-sparing route. The
`rare_earth_magnets` research_thread was updated only with reviewed decisions,
failure modes, and next actions; `materials_ontology_kg` was not changed. No
Scout DB, Qdrant, Neo4j, Graphiti, Slack, KG/RAG, runtime, or watchdog state was
mutated.

At that time, a bounded proposal-seed artifact and reviewable
`research_thread_patch_cli` were considered as follow-ons. This entry is
historical and must not be used as the current roadmap.

## 2026-06-11 — Completed rare-earth magnet route-ranking sheet

**Status:** Complete on `codex/ceml-ra-route-ranking-sheet`.

Generated durable Markdown and JSON artifacts for the HRE-sparing route-ranking
sheet:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/route_ranking_extraction_sheet/
```

The sheet compares four route families without treating missing data as
negative proof:

```text
grain-boundary diffusion / HRE-lean boundary engineering
HRE-free microstructure refinement / rapid consolidation
digital-twin or ML-guided process optimization
recycling-linked reprocessing / magnet-to-magnet route
```

It identifies FSPS HRE-free and GBD HRE-lean routes as proposal-review lanes,
digital-twin/ML as a calculation-scoping lane, and recycling-linked
reprocessing as weak until more downstream property evidence is extracted. The
`rare_earth_magnets` research_thread was updated only with reviewed evidence,
failure mode, decision, and next action items. No Scout DB, Qdrant, Neo4j,
Graphiti, Slack, KG/RAG, runtime, or watchdog state was mutated.

Remaining friction: this chunk again needed a one-off thread update script. If
the next artifact-producing chunk also needs thread writes, promote
`research_thread_patch_cli` before further proposal or KG preview work.

## 2026-06-11 — Completed Goal 4 observed-value automation backlog

**Status:** Complete on `codex/ceml-ra-automation-backlog`.

Generated an observed-value automation backlog from the question factory,
evidence briefs, idea matrices, and local partner-test transcript.

Artifact root:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_4_automation_backlog/
```

The top-ranked next implementation slice is:

```text
codex/ceml-ra-route-ranking-sheet
```

Goal objective:

```text
Implement an artifact-first route-ranking extraction sheet for rare-earth
magnet HRE-sparing ideas, using local artifacts only and no live runtime or
KG/RAG/Scout/Slack mutations.
```

KG ingest preview remains deferred and should only be implemented as a
preview-only artifact after the route-ranking/evidence-matrix workflow proves
which fields are worth structuring. No Scout DB, Qdrant, Neo4j, Graphiti,
Slack, or runtime services were mutated.

## 2026-06-11 — Completed Goal 3 local research partner test

**Status:** Complete on `codex/ceml-ra-research-partner-test`.

Generated a local Slack-style research partner transcript for:

```text
idea_rem_hre_sparing_route_ranking
```

Artifact root:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_3_partner_transcript/
```

The transcript reused Test Chunk 2 evidence and improved the selected idea by:

- splitting it into proposal-review and calculation-scoping lanes;
- flagging magnet-to-magnet recycling as weak until downstream magnet-property
  evidence appears;
- rejecting overbroad rare-earth-free framing in favor of HRE intensity
  reduction with performance-preserving microstructure control;
- defining a route-ranking extraction sheet as the concrete follow-on artifact
  at that time.

No Slack message was sent. No Scout DB, Qdrant, Neo4j, Graphiti, Slack, or
runtime services were mutated.

At that time, Goal 4 observed-value automation backlog was the follow-on. This
entry is historical and must not be used as the current roadmap.

## 2026-06-11 — Completed Test Chunk 2 evidence briefs and idea matrices

**Status:** Complete on `codex/ceml-ra-test-chunk-2-evidence-briefs`.

Generated durable evidence brief artifacts for:

```text
materials_ontology_kg
rare_earth_magnets
```

Generated a shared idea matrix with four idea candidates and selected three for
follow-up:

```text
idea_rem_hre_sparing_route_ranking
idea_mo_provenance_gated_kg_preview
idea_rem_digital_twin_ml_descriptor_triage
```

Artifact root:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/research_value_tests/test_chunk_2_evidence_briefs/
```

The durable research_thread artifacts were updated with candidate claims,
reviewed evidence signals, counterarguments, selected idea candidates, failure
modes, decisions, and next actions. The claims remain candidate status, not
accepted final facts. No Scout DB, Qdrant, Neo4j, Graphiti, Slack, or runtime
services were mutated.

At that time, Goal 3 was a local Slack-style research partner transcript on
`idea_rem_hre_sparing_route_ranking`. This entry is historical and must not be
used as the current roadmap.

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

At that time, Test Chunk 2 evidence briefs and idea matrices were considered as
the follow-on. This entry is historical and must not be used as the current
roadmap.

## 2026-06-11 — Realigned post-Chunk-4 validation direction

**Status:** Complete on `codex/ceml-ra-test-plan-realign`.

After Chunk 4, the repo still pointed to a KG ingest preview as the next
product step. That was premature for the validation plan at that time, which
then moved to Test Chunk 1: Research Question Factory for:

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

At that time, Chunk 4 was a read-only review surface for research_thread
artifacts. This entry is historical and must not be used as the current roadmap.

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

At that time, Chunk 3 was a Coordinator dry-run loop using local artifacts only.
This entry is historical and must not be used as the current roadmap.

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

At that time, Chunk 2 was the Scout evidence to research_thread adapter. This
entry is historical and must not be used as the current roadmap.

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
