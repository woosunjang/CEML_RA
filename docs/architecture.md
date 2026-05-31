# 시스템 아키텍처

## 오케스트레이션 파이프라인

```
사용자 요청
    ↓
┌─────────────────┐
│    Planner       │ ← 질문 분석 + 작업 분해
│ (gpt-5.4-mini)  │
└────────┬────────┘
         ↓
┌─────────────────┐
│    Router        │ ← 에이전트 선택 + 태스크 분배
│                  │
└────────┬────────┘
         ↓
┌─────────────────┐
│   Executor       │ ← 에이전트 병렬 실행
│ (asyncio.gather) │
└────────┬────────┘
         ↓
┌─────────────────┐
│  Synthesizer     │ ← 결과 종합 (multi-agent 시)
│ (gpt-5.4-mini)  │
└────────┬────────┘
         ↓
    최종 응답
```

### 분기 모드

| mode | 동작 |
|------|------|
| `normal` | Planner → Router → Executor → Synthesizer |
| `debate` | Debate Engine (3모델 토론) |
| `pipeline` | Pipeline Executor (향후 구현) |

### Planner

[planner.py](../orchestrator/planner.py)

- 사용자 질문을 분석하여 `ExecutionPlan` 생성
- 단일 에이전트 / 멀티 에이전트 판별
- 각 태스크에 적절한 에이전트 배정

### Router

[router.py](../orchestrator/router.py)

- `ExecutionPlan`의 각 태스크를 해당 에이전트로 전달
- 에이전트별 `AgentTask` 생성 + `agent.run()` 호출
- 의존성이 있는 태스크는 순차 실행

---

## 메모리 시스템 (3-Tier)

[memory.py](../orchestrator/memory.py) / [archival.py](../orchestrator/archival.py)

```
┌────────────────────────────────────┐
│ Core Memory (~200 tokens)          │
│ • 사용자 선호 (언어, 수준, 스타일) │
│ • 활성 프로젝트                    │
│ • 핵심 사실 (최근 10개)            │
│ ★ 항상 컨텍스트에 포함             │
├────────────────────────────────────┤
│ Recall Memory                      │
│ • 최근 5턴 대화 원문               │
│ • 20턴마다 자동 요약               │
│ • 대화 내 검색                     │
├────────────────────────────────────┤
│ Archival Memory (Graphiti)         │
│ • 엔티티-관계 자동 추출            │
│ • FalkorDB 지식 그래프 저장        │
│ • 시맨틱 검색으로 관련 기억 검색   │
│ ★ 대화 완료 후 비동기 저장         │
└────────────────────────────────────┘
```

### 메모리 흐름

1. **대화 시작**: Core Memory + Recall Memory를 system prompt에 주입
2. **대화 중**: 사용자·AI 메시지를 Recall에 저장
3. **대화 종료**: Archival Memory에 비동기 저장 (Graphiti → FalkorDB)
4. **다음 대화**: Archival에서 관련 기억 검색 → Core/Recall과 합쳐 주입

---

## Debate Engine

[debate.py](../orchestrator/debate.py) / [debate.yaml](../config/debate.yaml)

```
┌─────────────────────────────────┐
│ iMAD 복잡도 분류기               │
│ (gpt-5.4-nano, threshold=0.7)  │
├─────────────────────────────────┤
│ score < 0.7 → 단일 모델 응답    │
│ score ≥ 0.7 → 토론 엔진 시작    │
└────────────┬────────────────────┘
             ↓
┌────────────────────────────────────────┐
│ Round 1: 독립 응답 (병렬)              │
│   🟢 analyst (GPT)                    │
│   🟣 critic (Claude)                  │
│   🔵 synthesizer (Gemini)             │
├────────────────────────────────────────┤
│ Round 2: 상호 비판 (병렬)              │
│   각 패널리스트가 다른 2명의 R1을 비판 │
├────────────────────────────────────────┤
│ Round 3: 최종 입장 (병렬)              │
│   R1+R2 결과를 바탕으로 최종 입장 정리 │
├────────────────────────────────────────┤
│ Judge: 종합                            │
│   R3의 3개 최종 입장을 종합 → 최종 답변│
└────────────────────────────────────────┘
```

---

## 모델 프로필 시스템

[model_profiles.py](../llm/model_profiles.py)

두 가지 프로필 간 전환 가능:

| 에이전트 | 성능 모델 | 가성비 모델 |
|---------|----------|-----------|
| Orchestrator | gpt-5.4-mini | gpt-5-mini |
| Literature | gpt-4.1 (heavy) | gpt-4.1-mini |
| Teaching | gpt-4.1-mini | gpt-4.1-nano |
| Writing | claude-sonnet-4 (heavy) | gpt-4.1-mini |
| Presentation | gpt-4.1-mini | gpt-4.1-nano |
| Project | gpt-4.1-mini | gemini-2.0-flash |

프로필 전환은 런타임에 즉시 적용되며 서버 재시작이 필요 없습니다.

---

## 데이터 계층

| 서비스 | 역할 | 포트 |
|--------|------|------|
| Qdrant | Vector DB (Hybrid RAG) | 6333 |
| FalkorDB | 지식 그래프 (Archival) | 6379 |
| Scout DB | 논문 수집 메타데이터 | SQLite |
