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
