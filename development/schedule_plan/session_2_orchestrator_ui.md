# Phase 1 세션 2/3 — LangGraph 오케스트레이터 + Next.js UI

## 참조 문서
- 구현 계획: [implementation_plan.md](file:///Users/woosun/.gemini/antigravity/brain/4d64b553-80bb-48b8-ab54-96a5cddd4c07/implementation_plan.md)
- 세션 1 작업: [session_1_foundation.md](file:///Users/woosun/Dropbox/Dev/CEML_RA/development/schedule_plan/session_1_foundation.md)

---

## 전제 조건 확인

아래 조건을 먼저 확인하고, 불충족 시 해당 항목을 완료한 후 진행:

1. `/Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/` 프로젝트 존재 여부
2. `agents/literature/server.py` 정상 작동 (서버 기동 → `/health` 200 OK)
3. `agents/base.py`에 BaseAgent, AgentTask, AgentResult 정의됨

---

## Step 3: LangGraph 오케스트레이터

1. `orchestrator/memory.py` — SharedMemory 구현
   - `conversation_id`, `messages` (전체 대화 히스토리)
   - `task_context` (현재 작업 중간 결과물)
   - `active_documents` (참조된 문서 ID)
   - `get_recent_context(n_turns=3)` — 최근 N턴 반환
   - `store_agent_result(result)` — 후속 에이전트가 참조할 수 있도록 저장

2. `orchestrator/schemas.py` — OrchestratorState 정의
   - LangGraph MessagesState 상속
   - `plan`: 분해된 작업 리스트
   - `current_step`: 현재 실행 중인 단계
   - `agent_results`: 각 에이전트의 결과
   - `final_answer`: 통합 최종 답변

3. `orchestrator/planner.py` — LLM 기반 작업 분해
   - 사용자 지시를 분석하여 필요한 에이전트와 작업 목록 생성
   - 단일 에이전트로 충분한 경우 1개만 반환
   - 출력 형식: `[{"agent": "literature", "task": "...", "depends_on": []}]`

4. `orchestrator/router.py` — 에이전트 라우팅
   - `agents/registry.py`에서 등록된 에이전트 목록 조회
   - 작업을 적절한 에이전트의 FastAPI 서버로 HTTP 전달

5. `orchestrator/graph.py` — LangGraph StateGraph 구축
   - 노드: planner → router → executor → synthesizer
   - 조건부 엣지: executor 완료 후 남은 작업 확인 → continue/done
   - implementation_plan.md의 "LangGraph 오케스트레이터" 섹션 그대로 구현

6. `api/server.py` — 오케스트레이터 FastAPI 서버 (:8000)
   - `POST /chat` — SSE 스트리밍 응답
   - `GET /health`
   - `GET /agents` — 등록된 에이전트 목록 반환
   - CORSMiddleware 추가 (Next.js :3000에서 접근)

7. 테스트: 단일 에이전트 모드
   - Literature 서버 기동 (:8001)
   - 오케스트레이터 서버 기동 (:8000)
   - `curl -X POST localhost:8000/chat -d '{"message": "NASICON 논문 분석해줘"}'`
   - planner → literature 1개 선택 → 실행 → 응답 확인

## Step 4: Next.js UI 기본

1. 글로벌 스타일 설정
   - 다크 모드 기본
   - 기존 Streamlit UI 색상 참조: 사이드바 `#1a1a2e → #16213e`, 에이전트 뱃지 색상
   - Google Fonts: Inter 또는 Outfit

2. `components/chat/ChatPanel.tsx` — 메시지 목록 + 입력창
3. `components/chat/MessageBubble.tsx` — user/assistant 메시지 스타일링, 마크다운 렌더링
4. `components/chat/StreamingMessage.tsx` — SSE 기반 스트리밍 응답 실시간 표시
5. `components/sidebar/AgentSelector.tsx` — Auto(기본) / 수동 에이전트 선택 라디오
6. `components/sidebar/ScoutPanel.tsx` — Scout DB 통계(총 논문/오늘 수집) + 고관련도 논문 목록
7. `components/sidebar/FilterPanel.tsx` — 프로젝트/문서 타입 필터
8. `components/common/Header.tsx` — 상단 헤더 (로고 + 다크모드 토글)
9. `app/page.tsx` — 메인 채팅 레이아웃 (사이드바 + 채팅 영역)
10. `lib/api.ts` — 오케스트레이터 API 클라이언트 (fetch + SSE EventSource 파싱)
11. `lib/types.ts` — TypeScript 타입: AgentTask, AgentResult, Message, ScoutStats 등
12. 테스트: `npm run dev` → 채팅 입력 → 오케스트레이터 → 스트리밍 응답 표시

## 에러 처리 가이드

- **LangGraph import 오류**: `pip install langgraph` 재실행, 버전 `>=0.2` 확인
- **오케스트레이터 → 에이전트 HTTP 실패**: 에이전트 서버 프로세스 확인, 자동 재기동 시도
- **SSE 스트리밍 연결 실패**: FastAPI에 CORSMiddleware 추가 확인, Next.js 프록시 설정 (`next.config.js`에 rewrites)
- **Next.js 빌드 에러**: TypeScript 타입 오류 로그 확인 후 수정
- **LLM API 호출 실패**: API 키 확인, 쿼타 확인, `config/models.yaml`에서 fallback 모델로 전환

## 완료 기준

- [ ] 오케스트레이터 서버 (:8000) 기동 → `/health` 200 OK
- [ ] 단일 에이전트 질의 정상 동작 (오케스트레이터 → Literature → 응답)
- [ ] Next.js UI (:3000) 기동 → 채팅 화면 표시
- [ ] 채팅 입력 → 스트리밍 응답 표시 동작
- [ ] 사이드바 에이전트 선택 UI 동작
