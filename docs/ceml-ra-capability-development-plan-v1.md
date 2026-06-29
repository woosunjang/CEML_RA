# CEML_RA Capability Development Plan v1

**Status:** implementation guide before Phase 0 feature work.
**Date:** 2026-06-15 KST

**Implementation note:** Research Patch Review Workflow v1 now provides local
artifact-only preview/apply/reject controls for `research_thread` patch
candidates. Apply/reject requires explicit `confirm_artifact_write: true` and
continues to keep `live_store_mutations: []`.

**Implementation note:** Evidence Matrix Review Surface v1 now builds a
Korean-first Markdown/JSON matrix from `ResearchContextBundle` and
`research_thread` objects, placing evidence, counterarguments, missing evidence,
maturity lanes, and a recommended thread patch preview in one review flow. It is
a structured review surface, not an autonomous judgment engine, and continues to
keep `live_store_mutations: []`.

**Implementation note:** Research Knowledge Accumulation v1 now converts
reviewed/accepted `research_thread` objects into portable knowledge records and
optional archival worker queue jobs. This creates an actual accumulation path
from thread memory toward Graphiti without directly mutating live KG/RAG/Slack
stores.

**Implementation note:** Weekly Useful Research Loop v0 shifts the next product
center away from additional review surfaces. The first pilot is
`materials_ontology_kg`: a manual CLI/API weekly run reads `research_thread`,
RA artifacts, Scout, RAG, and KG memory, writes a Korean weekly brief plus
reusable memory note, updates the thread, and attempts live Graphiti/Qdrant
memory writes. Scheduler activation remains deferred until two manual runs
prove that prior memory is reused.

**Implementation note:** M2 Live Memory Bring-up makes the M2 Mac Mini the
runtime acceptance target for live memory. Graphiti is moved to the canonical
Neo4j backend, Qdrant and Neo4j are started from `lab-orchestrator/docker-compose.yml`,
and a `research_memory_healthcheck.py` preflight reports Scout/Qdrant/Neo4j/
Graphiti/OpenAI readiness before weekly runs.

**Implementation note:** Weekly Brief Quality v1 makes the manual
`materials_ontology_kg` weekly run prove research value before scheduler/UI
expansion. The brief now has explicit sections for new evidence, reused memory,
judgment change, weak/deferred claims, next-week questions, recommended checks,
and reuse provenance across `RA_artifacts`, Qdrant, and Graphiti.

**Implementation note:** Weekly Loop Evidence Separation v1 prevents internal
memory echo from being presented as fresh evidence. `research_memory_note`
results from Qdrant/Graphiti are kept in `memory_reuse_sources`, while
`new_evidence` is reserved for Scout papers, external RAG documents, and fresh
KG facts. Scout search also falls back from full-query phrase search to
token-overlap ranking across analyzed papers.

## Purpose

이 문서는 CEML_RA의 다음 개발 방향을 repo-local truth로 저장한다. 기능 구현은
이 문서를 먼저 저장하고 검토 가능한 상태로 만든 뒤에만 시작한다.

CEML_RA의 목표는 자동 보고서 도구나 상태 대시보드가 아니라, 장기 기억을 가진
PhD-level integrated research colleague가 되는 것이다. 자동 모드와 요청 기반
토론은 같은 `research_thread` 기억을 공유해야 하며, 산출물은 다음 대화, 판단,
제안서, 계산, 실험 계획에 재사용되어야 한다.

이 계획의 선택값은 다음과 같다.

- 개발 축: 필수 역량축
- 적용 방식: preview-first
- 계획 입도: 구현 페이즈형
- 기본 mutation 경계: preview/dry-run is `live_store_mutations: []`;
  명시적 weekly `execute=true`는 run artifact에 Graphiti/Qdrant mutation 결과를
  기록한다.

## Current Capability Baseline

현재 rebuild 기준으로 존재하는 기능은 다음과 같다.

- `research_thread` durable JSON/Markdown artifact
- read-only Scout evidence adapter
- Research Coordinator dry-run loop
- read-only research-thread review API
- reviewable research-thread patch CLI
- Research Work Package Planner
- Research Loop Packet v1
- Subagent Output Envelope v1
- Weekly Useful Research Loop v0
- Weekly Brief Quality v1
- Weekly Loop Evidence Separation v1
- M2 live memory healthcheck and bring-up runbook

이 기능들은 연구 기억 spine과 dry-run-first 경계를 만들었지만, 아직 통합 연구
동료로 보기에는 부족하다. 현재 부족한 핵심 기능은 다음과 같다.

- 연구 상태의 authority model
- 참조 가능한 research object model
- 모든 object를 다룰 universal patch protocol
- automatic/on-demand 공용 context loader
- Evidence Critic 기반 critique gate
- 기억 후보를 검토하는 review surface
- KG/RAG/Slack activation path

## Development Phases

### Phase 0. Research State v2

`research_thread`를 단순 section 목록에서 참조 가능한 research object spine으로
확장한다.

필수 변경:

- 기존 v1 artifact를 손실 없이 읽는 backward-compatible loader를 둔다.
- 새 schema는 object refs, authority state, review state, support state,
  provenance, artifact refs를 포함한다.
- 기존 Markdown/JSON round-trip을 깨지 않는다.

Exit gate:

- 기존 두 thread가 v2로 읽힌다.
- Markdown/JSON render와 write가 손실 없이 동작한다.
- live store mutation은 발생하지 않는다.

### Phase 1. Reviewable Update Protocol v2

모든 research object에 대해 preview/apply/reject/edit 가능한 patch protocol을
만든다.

필수 변경:

- `decisions`, `next_actions`, `failure_modes`만 다루는 patch 범위를 확장한다.
- `claims`, `evidence`, `counterarguments`, `idea_candidates`,
  `kg_ingest_preview`도 같은 preview protocol로 다룬다.
- patch에는 변경 이유, source/artifact refs, review state, mutation boundary를
  포함한다.

Exit gate:

- Scout, Coordinator, Work Package, Subagent Envelope가 같은 patch shape를 쓴다.
- apply 전 preview만으로 사용자가 무엇이 기억될 후보인지 검토할 수 있다.

### Phase 2. Shared Context Loader

automatic loop와 on-demand 질문이 같은 `ResearchContextBundle`을 사용하게 한다.

필수 변경:

- thread summary, 관련 objects, open questions, weak/strong claims, evidence
  gaps, recent decisions, artifact refs, retrieval candidates를 묶는다.
- context selection은 observation volume이 아니라 요청 목적과 research value를
  기준으로 제한한다.

Exit gate:

- 같은 연구 질문을 automatic trigger와 on-demand trigger로 넣었을 때 같은
  thread memory spine을 참조한다.

### Phase 3. Dry-run Subagent Execution Loop

Coordinator가 context bundle, loop packet, selected subagent role, output
envelope, merged patch preview를 한 흐름으로 묶는다.

필수 변경:

- Scout, Literature/RAG, KG Memory, Evidence Critic, Writing, Project role을
  같은 loop contract 아래에서 실행하거나 실행 계획으로 남긴다.
- LLM 호출이 붙더라도 결과는 envelope, artifact candidate, patch preview까지만
  남긴다.
- Slack, runtime, Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG live mutation은
  별도 승인 전까지 금지한다.

Exit gate:

- 한 번의 dry-run loop가 context bundle에서 시작해 artifact 후보와 patch preview
  생성까지 도달한다.

### Phase 4. Critique And Idea Maturation

Evidence Critic을 선택 기능이 아니라 루프의 필수 검문으로 둔다.

필수 변경:

- claim마다 missing evidence, counterargument, contradiction, stale support,
  uncertainty를 구조화한다.
- idea candidate에는 maturity lane을 둔다: `raw`, `needs_evidence`,
  `proposal_reviewable`, `calculation_ready`, `experiment_ready`, `defer`.
- 근거 없는 claim은 artifact나 KG fact로 승격하지 않는다.

Exit gate:

- 약한 idea와 전진 가능한 idea가 분리된다.
- proposal, calculation, experiment로 이어지는 next action만 명확히 승격된다.

### Phase 5. Artifact Co-production

concept note, evidence matrix, proposal seed, work-package plan을 같은 thread
context와 patch protocol에서 생성한다.

필수 변경:

- 사람이 읽는 Markdown은 한국어 기본으로 작성한다.
- JSON key, stable ID, source title, DOI, URL, file path, code/log/ops surface는
  영어를 유지할 수 있다.
- 산출물은 독립 보고서로 끝나지 않고 source object refs와 thread patch preview를
  남긴다.

Exit gate:

- 논의 -> artifact draft -> critique -> patch preview가 한 thread에서 재현된다.

### Phase 6. Review Surface API/UI/Slack Preview

thread, context bundle, loop packet, envelope, patch preview, artifact candidates를
검토 가능한 API/UI/Slack preview로 노출한다.

필수 변경:

- UI는 dashboard expansion보다 thread review, claim/evidence view, patch diff,
  approval queue를 우선한다.
- Slack은 초기에는 discussion/read-only preview 표면으로만 연결한다.
- 승인/적용은 명시적 command 또는 UI approval boundary에서만 가능하게 한다.

Exit gate:

- 사용자가 무엇이 기억될 후보인지, 왜 그런지, 어떤 근거인지 검토할 수 있다.

### Phase 7. Memory Infrastructure And Bounded Automation

KG/RAG/Slack/weekly automation은 preview -> 승인 -> ingest/send 순서로만
활성화한다.

필수 변경:

- KG Memory는 Neo4j/Graphiti ingest preview를 먼저 만들고, 승인 뒤에만 ingest한다.
- Qdrant/RAG는 source retrieval memory로 사용하되 decision/provenance의 canonical
  store가 되지 않는다.
- weekly automation은 Phase 0-6의 loop를 재사용하며, blocking API handler나 old
  Sprint Executor 방식으로 돌아가지 않는다.

Exit gate:

- 자동 루프가 research_thread를 읽고 새 evidence, critique, artifact candidate,
  patch preview를 만들되 승인 전 live stores를 바꾸지 않는다. Manual
  weekly-loop `execute=true`는 현재 파일럿의 명시 승인 경계로 취급한다.

## Implementation Defaults

- 사용자 검토용 Markdown과 설명문은 한국어 기본이다.
- `RA_artifacts`는 durable review ground truth이고 KG/RAG는 보조 기억이다.
- preview/dry-run의 live mutation 기본값은 계속 `live_store_mutations: []`이다.
- weekly loop의 `execute=true`는 Graphiti/Qdrant write를 시도할 수 있으며,
  결과와 실패 원인은 run artifact와 memory note provenance에 남긴다.
- 오래된 runtime, Slack command, Sprint Executor, 과거 proposal follow-on 산출물은
  현재 roadmap 근거로 쓰지 않는다.
- 첫 구현 chunk는 Phase 0의 `ResearchThread v2 + authority model`이다.
