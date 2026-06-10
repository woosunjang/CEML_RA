# Old Surface Audit And Fresh Rebuild Decision

**Date:** 2026-06-10
**Status:** Stage 0 audit index. This explicitly rejects wholesale reuse of old
code.

## Purpose

The Stage 0 rebuild starts from `main`, not from the old autonomy branches. The
old autonomy-pulse work moved too far in the wrong direction: too many
read-only reports, probes, ledgers, packets, and mutation lanes accumulated
before the product loop was clean.

This document is therefore not a salvage plan. It is a guardrail index: old
branches may explain failure modes and vocabulary, but new Stage 0 capabilities
should be implemented fresh from the current source/artifact/runtime contracts.

## Inputs

Audited read-only from git history, without checkout or runtime mutation:

- current branch: `codex/ceml-ra-stage0-main`
- reference branches: `codex/ceml-ra-reset-baseline`,
  `codex/mission-autonomy-pulse`
- primary comparisons:
  - `git diff --name-status main..codex/ceml-ra-reset-baseline`
  - `git diff --name-status main..codex/mission-autonomy-pulse`
  - `git ls-tree -r --name-only <branch>`
  - `git show <branch>:<selected-file>`

The old reset-baseline branch includes the unpushed local commit
`4fd6f46 feat: route research and specialist artifacts`. That commit remains a
reference archive only and should not be pushed, cherry-picked, or used as the
implementation base unless the user explicitly re-approves a specific file or
hunk.

## Fresh Rebuild Decision

Default rule:

```text
Do not reuse old autonomy-pulse code.
```

Instead:

- implement new modules from current Stage 0 requirements
- use old branch names only as warning signs and rough feature vocabulary
- copy no old writer/report/probe/worker code without explicit user approval
- prefer one small, tested core contract over many restored surfaces

## Classification Labels

| Label | Meaning |
| --- | --- |
| `core` | Product need remains valid, but implementation should be new and narrow. |
| `merge` | Useful product idea, but fold into a smaller new surface instead of restoring the old module family. |
| `dev-diagnostic` | Keep only as developer tooling or smoke checks, not product output. |
| `remove-candidate` | Do not carry forward unless a future need proves it. |
| `hold` | Potentially useful but blocked until a smaller dependency lands first. |

## Heuristic Inventory

The old branch contained a large surface area. A filename-level scan found about:

| Family | Approximate old references |
| --- | ---: |
| probe/smoke surfaces | 24 |
| read-only board/report/packet/standup surfaces | 20 |
| mission-core related files/tests | 27 |
| evidence-core related files/tests | 4 |
| store/worker/KG/job related files/tests | 17 |
| specialist/delegation related files/tests | 29 |

These counts are not API contracts. They show why Stage 0 should choose a small
spine rather than replay the old branch.

## Audit Table

| Old surface family | Example old paths | Classification | Stage 0 decision |
| --- | --- | --- | --- |
| Mission intake and mission ledger | `integrations/mission_intake.py`, `mission_store.py`, `mission_planner.py`, `mission_brief.py`, `mission_evidence_matrix.py` | `core` | Product need remains: one mission spine with explicit questions, evidence, approvals, and follow-ups. Implement fresh. Do not reuse old SQLite files, old active mission IDs, or old module internals. |
| Evidence contract and evidence review | `integrations/evidence_contract.py`, `evidence_review.py`, `agents/evidence_critic/` | `core` | Product need remains and should be rebuilt first from scratch. Keep it thin, source-agnostic, and conservative about claim support. |
| Background job store and worker | `integrations/job_store.py`, `job_worker.py`, `tests/test_job_*`, `ui/src/app/jobs/` | `core` plus `hold` | Product need likely remains for non-blocking work, but implement fresh only after mission/evidence contracts are stable. Runtime DB must stay host-local. Launchd worker is separate and later. |
| KG queue and promotion | `kg_store.py`, `kg_candidate_review.py`, `kg_enrichment_backlog.py`, `kg_promotion_worker.py`, `tools/kg_quality_report.py` | `merge` plus `hold` | Product need may remain, but old code is too broad. Later create one explicit KG export/promotion lane. Do not recreate many KG reports or automatic ingestion lanes before mission/evidence core exists. |
| Artifact manifests and knowledge snapshots | `orchestrator/artifact_manifest.py`, `tools/knowledge_snapshot_export.py`, `docs/artifact-storage.md` | `merge` | Current Stage 0 already replaced this with a smaller `ARTIFACTS_DIR` contract and explicit one-file export manifest. The old implementation is superseded. |
| Daily Run, Sprint Executor, Autopilot | `autonomy_daily_run.py`, `autonomy_sprint_executor.py`, `autonomy_autopilot.py`, `autonomy_next_turn.py` | `merge` plus `hold` | Product need is one operator surface showing next important action. Do not restore Sprint Executor mutation lanes, self-answering behavior, or backlog pressure. Later build a new thin view over mission/job state. |
| Proposal backlog and proposal boards | `autonomy_proposal_backlog.py`, `autonomy_proposal_board.py`, `research_proposals.py` | `remove-candidate` plus `hold` | Do not restore as a durable pressure system. Salvage only the idea of explicit proposal questions when scientific judgment is needed. No proposal promotion logic by default. |
| Source-review question machinery | `record_research_proposal_review_questions`, proposal/source-review packet tools | `remove-candidate` | This created visible but indirect progress. Keep user questions in the mission ledger instead of a separate review-question lane. |
| Specialist work-order ledgers | `autonomy_specialist_work_orders.py`, `autonomy_specialist_*`, `autonomy_council.py`, `autonomy_critic_briefs.py` | `hold` | Subagents matter, but a separate specialist ledger should not return before job store and mission state are rebuilt. Later, represent specialist tasks as job kinds or mission follow-ups. |
| Many read-only boards/reports/packets | `autonomy_*_board.py`, `*_packet.py`, `*_report.py`, `*_standup.py`, `*_digest.py`, `*_notebook.py`, `*_program.py`, `*_seminar.py` | `remove-candidate` | Do not restore as product surfaces. At most merge selected fields into one operator surface after the mission/job spine exists. |
| Probe and smoke tools | `autonomy_*_probe.py`, `autonomy_*_readonly_smoke.py`, `ops_smoke.py` | `dev-diagnostic` | Keep the testing idea, not the product artifacts. Rebuild only narrow smoke checks for current APIs/UI when they are needed. |
| Runtime proof and deploy readiness reports | `autonomy_runtime_proof.py`, `autonomy_deploy_readiness.py`, runtime remediation docs | `dev-diagnostic` | Useful during deployment debugging, but not a user-facing research loop. Keep as runbook reference only. |
| Launchd workers and watchdog plists | `deploy/kr.ceml.lab-*-worker.plist`, `kr.ceml.lab-watchdog.plist` | `hold` | Do not reintroduce until the code path is rebuilt, tested, and operational guard checks pass. Plist changes require `plutil -lint`. |
| Mission/jobs UI pages | `ui/src/app/missions/`, `ui/src/app/jobs/`, `JobCard.tsx` | `merge` | Rebuild only after API contracts land. The first UI should be one compact operator surface, not many historical boards. |
| Research agents added in old branch | `agents/project_operator/`, `agents/evidence_critic/` | `core` for evidence critic, `hold` for project operator | Evidence critic fits source-grounded review. Project operator should wait until mission/job contracts define what it operates. |

## Fresh Rebuild Order

1. Keep the current Stage 0 storage boundary and explicit snapshot export.
2. Implement a new `evidence_contract` and `evidence_review` as the first
   source-grounded core.
3. Rebuild a minimal mission ledger: mission, question, evidence, decision,
   follow-up, approval.
4. Rebuild a minimal host-local job store only after mission actions need
   asynchronous execution.
5. Add one operator surface that summarizes mission/job/evidence state and the
   next user action.
6. Add KG/RAG/Scout promotion lanes only as explicit, reviewed actions.
7. Consider specialist delegation as job kinds or mission follow-ups, not a
   separate ledger, unless later evidence shows the separate ledger is needed.

## Do Not Carry Forward By Default

- old active mission IDs, old proposal pressure, or old Sprint Executor state
- self-answering or automatic approval behavior
- broad artifact-root directory constants for every old writer
- separate `autonomy_*_report`, `*_packet`, `*_board`, `*_standup`, and
  `*_probe` surfaces
- proposal promotion and source-review question machinery
- specialist work-order ledgers
- launchd worker/watchdog plists
- generated/ops artifacts as current requirements

## Acceptance Gates For Any Similar Feature

Any capability inspired by the old branches must pass these gates before it
becomes code:

1. It serves research progress directly, not observation volume.
2. It has one owner boundary: API, worker, UI, Scout/RAG/KG, docs, or artifact
   contract.
3. It keeps live DB/log/cache/queue state host-local.
4. It writes durable outputs only through `ARTIFACTS_DIR` or an explicit export.
5. It has focused tests or a narrower syntax/compile check.
6. It updates docs when it changes architecture, commands, runtime data paths,
   job behavior, or artifact contracts.
7. It replaces or consolidates an older surface instead of adding another
   parallel report.

## Next Implementation Candidate

The next useful Stage 0 implementation slice is:

```text
fresh evidence_contract + fresh evidence_review + focused tests
```

This is smaller and safer than reintroducing mission execution, Sprint
Executor, or old operator boards. It gives the future mission ledger a stable
way to distinguish source evidence, retrieval hints, unsupported claims, and
explicit limitations.
