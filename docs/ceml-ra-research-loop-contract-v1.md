# CEML_RA Research Loop Contract v1

**Status:** planning contract
**Date:** 2026-06-12 KST

## Purpose

이 문서는 CEML_RA가 단순히 연구 artifact를 계속 작성하는 도구가 아니라,
장기 기억을 가진 통합 연구 동료로 작동하기 위한 루프 계약이다.

핵심 기준은 다음과 같다.

- 자동 모드와 요청 기반 모드는 같은 `research_thread` 기억을 사용한다.
- 모든 산출물은 누적된 맥락을 읽고, 근거/반론/결정/다음 행동을 다시 기억으로
  돌려보낸다.
- Coordinator는 모든 연구를 직접 쓰는 작성자가 아니라, 역할별 subagent를 호출하고
  기억 갱신을 조율하는 책임자다.
- KG/RAG/Slack/UI/runtime은 이 계약을 구현하는 표면일 뿐, 그 자체가 제품 진전은
  아니다.

## Shared Memory Contract

`research_thread`는 연구 루프의 작업 기억이다.

각 루프는 최소한 다음 중 하나를 남긴다.

- 변경 없음과 그 이유;
- `research_thread` patch preview;
- 사람이 읽을 수 있는 durable artifact;
- KG ingest preview;
- 다음 루프를 위한 명시적 stop condition.

기억 갱신 원칙:

- 조용히 live store를 변경하지 않는다.
- artifact는 사람이 검토할 수 있는 ground truth로 남긴다.
- KG/RAG는 artifact를 대체하지 않고, 검색과 추론을 돕는 보조 기억으로 둔다.
- 사용자에게 보일 Markdown과 설명 문장은 한국어를 기본으로 한다.
- 근거가 부족한 값은 추정하지 않고 `missing`, `not_found`, `incomparable`,
  `secondary_only` 같은 상태로 남긴다.

## Operating Loops

### Automatic Research Loop

자동 루프는 사용자가 요청하지 않아도 연구 맥락을 정리할 수 있다. 단, 자동 실행의
목표는 많은 작업량이 아니라 유용한 기억 갱신이다.

기본 흐름:

1. Coordinator가 활성 `research_thread`와 열린 next action을 고른다.
2. Scout 또는 Literature/RAG 역할이 source signal과 evidence preview를 만든다.
3. Evidence Critic이 claim boundary, missing evidence, counterargument, failure
   mode를 분리한다.
4. Writing 또는 Project 역할이 필요한 경우 artifact draft 또는 next-action plan을
   만든다.
5. Coordinator가 patch preview와 durable artifact 후보를 묶어 사용자 검토 가능한
   형태로 남긴다.

자동 루프는 live Slack 메시지, KG/RAG ingest, runtime service mutation을 기본으로
하지 않는다. 그런 동작은 별도 승인 경계다.

### On-Demand Research Loop

요청 기반 루프는 사용자의 질문, 토론, 제안서 작성 요청, 프로젝트 관리 요청에서
시작한다.

기본 흐름:

1. Coordinator가 관련 `research_thread`, durable artifact, 필요한 source preview를
   로드한다.
2. 사용자 요청을 기존 claim, evidence, counterargument, decision, next action과
   대조한다.
3. Evidence Critic이 약한 주장과 전진 가능한 주장을 구분한다.
4. Writing 또는 Project 역할이 필요한 출력 형식을 만든다.
5. 토론 결과는 thread patch preview 또는 artifact update 후보로 되돌아간다.

요청 기반 루프도 단발 답변으로 끝나면 안 된다. 새 판단이나 결정이 생기면 같은
`research_thread`에 재사용 가능한 형태로 남긴다.

## Coordinator And Subagent Contracts

Coordinator의 책임:

- 어떤 thread를 읽고 갱신할지 결정한다.
- subagent 호출 순서와 stop condition을 정한다.
- 결과를 patch preview, durable artifact, KG preview 중 어디에 둘지 정한다.
- 약한 근거를 강한 주장처럼 승격하지 않는다.
- live store mutation, runtime restart, Slack send 같은 승인 경계를 지킨다.

Subagent 역할 계약:

| Role | Input | Output | Must not |
| --- | --- | --- | --- |
| Scout | topic, source hint, thread context | source signals, candidate sources | Scout DB를 조용히 변경하지 않는다 |
| Literature/RAG | source refs, question, thread context | evidence preview, retrieval summary | RAG 결과를 확정 claim으로 승격하지 않는다 |
| KG Memory | thread items, artifact refs | KG ingest preview | 승인 없이 Neo4j/Graphiti에 ingest하지 않는다 |
| Evidence Critic | claims, evidence, artifact draft | counterarguments, missing evidence, failure modes | 빈 근거를 확정처럼 포장하지 않는다 |
| Writing | thread context, evidence boundary, audience | Korean-first draft or artifact | 출처 없는 새 연구 주장을 만들지 않는다 |
| Project | decisions, next actions, deadlines | next-action plan, stop conditions | status loop를 제품 진전으로 포장하지 않는다 |

각 subagent 출력은 독립 산출물로 끝나지 않는다. Coordinator가 같은
`research_thread`로 다시 연결해야 한다.

## Advancement Filter

새 기능 또는 다음 개발 chunk는 아래 질문을 통과해야 한다.

- 이 작업이 `research_thread`의 장기 기억을 더 좋게 만드는가?
- 이전 artifact와 대화 맥락을 재사용하는가?
- 약한 아이디어와 전진 가능한 아이디어를 구분하는가?
- 계산, 실험, 제안서 검토 중 하나로 이어지는 next action을 더 선명하게 만드는가?
- 자동 모드와 요청 기반 모드가 같은 기억을 공유하게 만드는가?
- live store mutation 없이 preview 또는 durable artifact로 검토 가능한가?

이 질문에 답하지 못하면 dashboard, status surface, executor, Slack command, KG ingest
preview를 먼저 만들지 않는다.

## Near-Term Implementation Direction

다음 구현은 새 연구 artifact를 직접 쓰는 일이 아니라, 이 계약을 작은 코드 경계로
옮기는 일이어야 한다.

우선순위 후보:

- Coordinator가 한 루프의 입력, 역할 호출, 출력 후보를 기록하는 loop packet;
- subagent 출력이 `research_thread` patch preview로 돌아오는 공통 envelope;
- 자동 모드와 요청 기반 모드가 같은 thread context loader를 쓰는 read-only path;
- artifact update 전 `Evidence Critic` 검토를 강제하는 preview step.

아직 하지 않을 것:

- rare-earth/HRE 후속 artifact 직접 작성;
- Work Package Planner executor 구현;
- Slack command 확장;
- runtime service 재시작;
- Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG live mutation.
