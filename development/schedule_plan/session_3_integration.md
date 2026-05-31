# Phase 1 세션 3/3 — 에이전트 통합 + 멀티 에이전트 체이닝 + 통합 테스트

## 참조 문서
- 구현 계획: [implementation_plan.md](file:///Users/woosun/.gemini/antigravity/brain/4d64b553-80bb-48b8-ab54-96a5cddd4c07/implementation_plan.md)
- 세션 1: [session_1_foundation.md](file:///Users/woosun/Dropbox/Dev/CEML_RA/development/schedule_plan/session_1_foundation.md)
- 세션 2: [session_2_orchestrator_ui.md](file:///Users/woosun/Dropbox/Dev/CEML_RA/development/schedule_plan/session_2_orchestrator_ui.md)

---

## 전제 조건 확인

아래 조건을 먼저 확인하고, 불충족 시 해당 항목을 완료한 후 진행:

1. 오케스트레이터 서버 (:8000) 정상 작동
2. Literature Agent (:8001) 정상 작동
3. Next.js UI (:3000) 정상 빌드 (`npm run build` 성공)
4. 단일 에이전트 질의 동작 확인 (오케스트레이터 → Literature → 응답)

---

## Step 5: 나머지 에이전트 마이그레이션

1. `agents/writing/agent.py` — WritingAgent(BaseAgent)
   - 기존 `lab-research-agents/app/agents/prompts.py`의 proposal + manuscript 프롬프트 통합
   - `mode` 파라미터로 구분: "proposal" | "manuscript" | "abstract" | "review_response"
   - can_handle(): 제안서, 논문, 초록, 리뷰 관련 키워드 감지

2. `agents/writing/server.py` — FastAPI :8003

3. `agents/teaching/agent.py` — TeachingAgent(BaseAgent)
   - 기존 lecture 프롬프트 이식
   - 모드: "lecture_design" | "quiz" | "notebook"
   - can_handle(): 강의, 수업, 퀴즈, 과제 관련 키워드 감지

4. `agents/teaching/server.py` — FastAPI :8002

5. `agents/presentation/agent.py` — PresentationAgent(BaseAgent)
   - 스텁 구현 (Phase 3에서 강화)
   - 기본: 프레젠테이션 구조 텍스트 생성
   - can_handle(): PPT, 발표, 슬라이드, 포스터 관련 키워드

6. `agents/presentation/server.py` — FastAPI :8004

7. `agents/project/agent.py` — ProjectAgent(BaseAgent)
   - 스텁 구현 (Phase 4에서 강화)
   - 기본: 프로젝트 관리 조언 텍스트 생성
   - can_handle(): 일정, 마감, 프로젝트, 회의 관련 키워드

8. `agents/project/server.py` — FastAPI :8005

9. `agents/registry.py` — 에이전트 레지스트리
   - `config/agents.yaml`에서 에이전트 목록 로드
   - `get_agent(name)`: 이름으로 에이전트 조회
   - `find_best_agent(instruction)`: can_handle() 기반 자동 라우팅
   - `list_agents()`: 전체 에이전트 목록 반환

10. 테스트: 각 에이전트 서버 기동 → `curl localhost:800X/health` 전체 확인

## Step 6: 멀티 에이전트 체이닝

1. `orchestrator/planner.py` 강화
   - 복합 지시 분해: "논문 분석하고 강의안 만들어줘" → `[literature, teaching]`
   - 의존관계 표현: `{"agent": "teaching", "depends_on": ["literature"]}`
   - 병렬 실행 가능한 작업 식별

2. `orchestrator/graph.py` — executor 노드 수정
   - 에이전트 결과를 SharedMemory에 저장
   - 다음 에이전트 호출 시 `parent_results`에 이전 결과 포함
   - 의존관계 순서대로 실행

3. `orchestrator/graph.py` — synthesizer 노드
   - 여러 에이전트의 결과를 하나의 구조화된 응답으로 통합
   - 각 에이전트의 기여를 명시적으로 구분

4. Next.js UI 업데이트
   - 작업 진행 상태 실시간 표시
   - 각 에이전트 단계별 상태: ⏳ 대기 → 🔄 실행 중 → ✅ 완료
   - 에이전트별 결과를 접을 수 있는 섹션으로 표시

5. 테스트: "NASICON 논문 정리하고 세미나 강의안 만들어줘"
   - planner → [literature, teaching] 분해
   - literature 실행 → 결과 저장
   - teaching 실행 (literature 결과 참조) → 결과 저장
   - synthesizer → 통합 응답

## Step 7: Multi-turn + 통합 테스트

1. `orchestrator/memory.py` — 대화 히스토리 관리
   - 대화 히스토리를 LLM 컨텍스트에 포함 (최근 3턴, user+assistant)
   - 토큰 제한 초과 시 오래된 턴부터 자동 제거
   - conversation_id별 메모리 격리

2. `api/server.py` — conversation_id 기반 세션 관리
   - 새 대화: conversation_id 자동 생성
   - 기존 대화 이어가기: conversation_id 전달

3. Next.js UI — 대화 관리
   - 대화 히스토리 유지 (페이지 새로고침 시에도)
   - "새 대화" 버튼
   - 이전 대화 목록 (선택 사항)

4. 엔드투엔드 테스트 시나리오:
   - **a. 단일 에이전트**: "NASICON 논문 분석해줘" → Literature 정상 응답
   - **b. 후속 질문**: "아까 분석한 논문 중 가장 관련도 높은 것의 방법론 설명해줘" → 맥락 유지
   - **c. 에이전트 전환**: "그 내용으로 제안서 배경 문단 써줘" → Writing 에이전트 자동 선택
   - **d. 멀티 에이전트**: "NASICON 최신 동향 정리하고 다음 학기 강의안 만들어줘" → Literature → Teaching
   - **e. Scout 연동**: 사이드바에서 수집 논문 확인, 검색 동작

5. 발견된 버그 수집 및 수정

## 에러 처리 가이드

- **포트 충돌**: `lsof -i :800X`로 확인, 충돌 프로세스 `kill -9`
- **에이전트 체이닝 중 중간 실패**: 실패 에이전트 결과 스킵, 실패 내용을 최종 응답에 "[에이전트명] 실행 실패: 사유" 포함
- **Multi-turn 토큰 초과**: tiktoken으로 토큰 수 계산, 모델 한도의 70% 이내로 히스토리 자동 트림
- **전체 통합 테스트 실패**: 실패 지점 로그 확인 → 개별 컴포넌트 단위 테스트로 문제 격리 → 수정 → 재테스트
- **LLM 쿼타 소진**: `config/models.yaml`의 fallback 모델로 자동 전환, 사용자에게 알림

## 완료 기준

- [ ] 5개 에이전트 서버 전부 기동 + /health 200 OK
- [ ] 에이전트 레지스트리에서 `find_best_agent()` 정상 동작
- [ ] 복합 지시 → 멀티 에이전트 체이닝 정상 실행
- [ ] UI에 작업 진행 상태 실시간 표시
- [ ] Multi-turn 대화 맥락 유지 동작
- [ ] 엔드투엔드 테스트 5개 시나리오 전부 통과
