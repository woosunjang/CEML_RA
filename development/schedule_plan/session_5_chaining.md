# 세션 5 — 에이전트 체이닝 고도화

## 참조 문서
- 전략 계획: [implementation_plan.md](file:///Users/woosun/.gemini/antigravity/brain/4d64b553-80bb-48b8-ab54-96a5cddd4c07/implementation_plan.md)
- 현재 파이프라인: [graph.py](file:///Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/orchestrator/graph.py)
- 현재 플래너: [planner.py](file:///Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/orchestrator/planner.py)
- 현재 라우터: [router.py](file:///Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/orchestrator/router.py)

---

## 배경

현재 Planner가 작업을 분해하고 Router가 에이전트를 호출하지만:
- 에이전트 간 **직접 핸드오프** 없음 (각 에이전트가 독립 실행)
- 이전 에이전트 출력을 **다음 에이전트 입력으로 전달**하는 구조 미비
- 사전 정의된 **파이프라인 템플릿** 없음

---

## Step 1: Pipeline Templates 설계 + 구현 (3h)

### 1-1. `config/pipelines.yaml` 생성
```yaml
pipelines:
  literature_to_writing:
    name: "문헌분석 → 논문작성"
    description: "논문 수집·분석 후 해당 내용으로 논문 섹션 작성"
    steps:
      - agent: literature
        task_template: "다음 주제에 대한 문헌 조사: {topic}"
        output_key: literature_review
      - agent: writing
        task_template: "다음 문헌 조사 결과를 바탕으로 {section} 작성:\n{literature_review}"
        output_key: draft

  full_paper_pipeline:
    name: "논문 풀 파이프라인"
    steps:
      - agent: literature
        output_key: literature_review
      - agent: writing
        output_key: draft
      - agent: presentation
        task_template: "다음 논문 초안을 기반으로 발표 슬라이드 구성:\n{draft}"
        output_key: slides

  review_response:
    name: "리뷰 응답 파이프라인"
    steps:
      - agent: literature
        task_template: "리뷰어 지적사항 관련 추가 문헌 조사:\n{reviewer_comments}"
        output_key: additional_refs
      - agent: writing
        task_template: "다음 추가 문헌과 원 논문을 바탕으로 리뷰 응답서 작성:\n{additional_refs}"
        output_key: response_letter
```

### 1-2. `orchestrator/pipeline.py` 구현
- `PipelineExecutor` 클래스
- 파이프라인 정의 로드 (`config/pipelines.yaml`)
- 순차 실행: step N의 output → step N+1의 context에 자동 주입
- 각 step의 AgentResult를 `parent_results`로 전달
- 실패 시: 해당 step 에러 보고 + 이후 step 스킵

### 1-3. Planner 연동
- `planner.py` 수정: 사용자 지시에 "논문 쓰고 발표자료까지", "리뷰 응답" 등의 패턴이 감지되면 파이프라인 ID 반환
- `ExecutionPlan`에 `pipeline_id: Optional[str]` 필드 추가
- `graph.py`에서 pipeline_id가 있으면 `PipelineExecutor` 호출

---

## Step 2: Artifact Passing 구현 (2h)

### 2-1. AgentResult 확장
- `artifacts` 필드 활용: `[{"type": "markdown", "content": "..."}, {"type": "json", "content": {...}}]`
- 에이전트가 파일을 생성한 경우 경로 포함: `{"type": "file", "path": "/tmp/output.pptx"}`

### 2-2. 에이전트별 artifact 생산 표준화
- Literature: `{"type": "literature_review", "papers": [...], "summary": "..."}`
- Writing: `{"type": "draft", "sections": {...}, "full_text": "..."}`
- Presentation: `{"type": "slide_spec", "slides": [...]}`

### 2-3. Synthesizer 개선
- 파이프라인 실행 결과일 때: 최종 step의 출력을 주 응답으로, 중간 step은 요약
- 각 step의 artifact를 `metadata.pipeline_artifacts`에 포함

---

## Step 3: Human-in-the-Loop (HITL) 체크포인트 (2h)

### 3-1. 체크포인트 스키마
```python
class CheckpointRequest(BaseModel):
    """파이프라인 중간에 사용자 확인 요청."""
    pipeline_id: str
    step_index: int
    step_result: AgentResult
    question: str  # "이 문헌 조사 결과로 논문을 작성할까요?"
    options: list[str] = ["proceed", "modify", "abort"]
```

### 3-2. API 엔드포인트
- `POST /pipeline/checkpoint/{id}/respond` — 사용자 응답
- 파이프라인은 checkpoint에서 일시 정지, 응답 후 재개

### 3-3. 프론트엔드 연동 (UI 세션에서 마무리)
- 체크포인트 수신 시 UI에서 승인/수정/취소 버튼 표시

---

## 검증 기준

- [ ] `literature_to_writing` 파이프라인 E2E 테스트 성공
- [ ] Literature 출력이 Writing 입력에 자동 주입 확인
- [ ] 파이프라인 실패 시 에러 보고 + graceful degradation
- [ ] HITL 체크포인트 기본 동작 (API level)
