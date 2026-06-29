# CEML_RA Docs

This directory is a small index for current repo-local project truth.

Read first:

1. [CEML_RA Ground Goal And Phased Rebuild](ceml-ra-ground-goal-and-phases.md)
2. [Capability Development Plan v1](ceml-ra-capability-development-plan-v1.md)
3. [Research Loop Contract v1](ceml-ra-research-loop-contract-v1.md)
4. [Repo operating instructions](../AGENTS.md)
5. [Current handoff](../.agents/context/HANDOFF.md)
6. [Task log](../.agents/context/TASK_LOG.md)

## Direction Boundary

CEML_RA is being rebuilt as a PhD-level integrated research colleague with
long-term memory. It is not defined by old local runtimes, old Slack command
surfaces, old launchd services, old API references, old autonomy mission flows,
or stale Codex global memory.

Recent research artifacts, proposal artifacts, and planner outputs are
available context only. They are not an implied roadmap. Choose the next product
step from the current repo-local files and the user's latest instruction.

The Research Loop Contract defines how automatic and on-demand research modes
should share the same `research_thread` memory before more surfaces or
automation are added.

Current dry-run entrypoints:

- `lab-orchestrator/tools/research_context_bundle_plan.py` builds the shared
  automatic/on-demand context bundle without mutating live stores.
- `lab-orchestrator/tools/research_loop_packet_plan.py` plans one research loop
  from the shared context bundle without writing research content or mutating
  live stores.
- `lab-orchestrator/tools/subagent_output_envelope_plan.py` turns a selected
  loop-packet role output into a reviewable envelope, critique gate, artifact
  candidate preview, and thread patch preview without executing live subagents
  or mutating live stores.

Read-only review surfaces:

- `GET /research/threads/{thread_id}/context`
- `POST /research/threads/{thread_id}/evidence-matrix/preview`
- `POST /research/loops/preview`
- `POST /research/subagent-envelopes/preview`
- `lab-orchestrator/ui/src/app/research/page.tsx`

Evidence Matrix review surface:

- `POST /research/threads/{thread_id}/evidence-matrix/preview` builds a
  structured review matrix that places focus objects beside linked evidence,
  counterarguments, missing evidence, maturity lanes, and a recommended thread
  patch preview. It is read-only and keeps `live_store_mutations: []`.
- `POST /research/threads/{thread_id}/evidence-matrix/write` writes the matrix
  Markdown/JSON and patch-preview JSON only when `confirm_artifact_write: true`
  is present. It does not apply the patch or mutate KG/RAG/Slack/runtime state.
- Evidence Matrix v1 is a review surface, not an autonomous judgment engine:
  unresolved evidence gaps and counterarguments must flow into the patch review
  workflow before anything is remembered as accepted.

Knowledge accumulation:

- `POST /research/threads/{thread_id}/knowledge/preview` builds portable
  knowledge records from reviewed/accepted `research_thread` objects without
  writing artifacts.
- `POST /research/threads/{thread_id}/knowledge/write` writes the knowledge
  record Markdown/JSON and archival queue preview only when
  `confirm_artifact_write: true` is present.
- `POST /research/threads/{thread_id}/knowledge/enqueue-archival` also writes
  archival worker queue jobs, but only when both `confirm_artifact_write: true`
  and `confirm_archival_enqueue: true` are present. It queues local jobs; it
  does not call Graphiti or mutate live KG/RAG/Slack/runtime state directly.

Weekly Useful Research Loop:

- `lab-orchestrator/tools/research_weekly_loop.py` runs the first actually
  usable weekly loop. v0 is intentionally constrained to
  `materials_ontology_kg`.
- Live-memory acceptance uses the M2 Mac Mini runtime, not the development Mac.
  Start Qdrant and Neo4j from `lab-orchestrator/docker-compose.yml`; keep
  `NEO4J_PASSWORD`, OpenAI keys, and Scout DB paths in local env or `.env`.
- `lab-orchestrator/tools/research_memory_healthcheck.py --json --deep` checks
  artifact root, `materials_ontology_kg` thread, Scout DB, Qdrant, Neo4j,
  Graphiti import/init, and OpenAI embedding readiness before a real run.
- `POST /research/threads/{thread_id}/weekly-loop/run` previews or runs the
  same loop. `execute=true` writes a Korean weekly brief, reusable memory note,
  and `research_thread` update. By default it also attempts Graphiti and Qdrant
  live memory writes; set `use_live_memory=false` for artifact-only runs. The
  response includes `source_availability` and `preflight_summary` so
  `partial_failure` has actionable causes.
- Artifacts are written under `research_weekly_loops/{thread_id}/` and
  `research_memory_notes/{thread_id}/`. The success criterion is not another
  review surface; it is that a later weekly run can reuse an earlier memory
  note with a citation.
- Weekly Brief Quality v1 fixes the first useful output shape: the Markdown
  brief must show new evidence, reused memory, judgment change, weak/deferred
  claims, next-week questions, and recommended reading/check targets. Reuse
  provenance records whether prior memory came from `RA_artifacts`, Qdrant, or
  Graphiti.
- Weekly Loop Evidence Separation v1 keeps internal memory echo out of the
  "new evidence" lane. Qdrant/Graphiti hits for `research_memory_note` or
  weekly memory-note episodes are reported under `memory_reuse_sources`; only
  Scout papers, external RAG documents, and fresh KG facts appear under
  `new_evidence`.
- `source_availability` reports raw source counts plus `fresh_evidence_count`,
  `memory_reuse_count`, `scout_retrieval_mode`, and
  `fresh_evidence_missing_reason`. If Scout exact query search misses, the
  weekly loop falls back to token-overlap ranking across analyzed Scout papers.
- M2 manual bring-up sequence:

  ```bash
  cd /Users/mersoom/Dev/CEML_RA/lab-orchestrator
  docker compose up -d qdrant neo4j
  export CEML_RA_ARTIFACTS_DIR=/Users/mersoom/Dropbox/Dev/CEML/RA_artifacts
  export SCOUT_DB_PATH=/Users/mersoom/Dev/CEML_RA/lab-paper-scout/data/paper_scout.db
  python tools/research_memory_healthcheck.py --json --deep
  cd ../lab-paper-scout && python run.py run
  cd ../lab-orchestrator && python tools/research_weekly_loop.py --execute
  ```
- If Graphiti logs `EquivalentSchemaRuleAlreadyExists` while the final
  healthcheck JSON is `status: "ok"`, treat it as a noisy successful
  initialization rather than a failed bring-up.

Patch review workflow:

- `POST /research/threads/{thread_id}/patches/preview` previews an edited patch
  without writing artifacts.
- `POST /research/threads/{thread_id}/patches/apply` applies a patch only when
  `confirm_artifact_write: true` is present, then writes a patch review record.
- `POST /research/threads/{thread_id}/patches/reject` records a rejected patch
  only when `confirm_artifact_write: true` is present, without changing the
  research thread.
- These endpoints write only local durable artifacts and keep
  `live_store_mutations: []`.

## Storage Boundary

- Source code belongs in git and GitHub.
- Durable research artifacts belong under `CEML_RA_ARTIFACTS_DIR`, normally:

  ```text
  /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
  ```

- Live runtime state, local databases, logs, caches, queues, volumes, and
  `.env` files stay host-local and out of git.

## Runtime Boundary

Do not assume a local service is current just because a port is open. Stale
runtimes and watchdogs are not product evidence.
