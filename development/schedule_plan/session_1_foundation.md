# Phase 1 세션 1/3 — 프로젝트 기반 구축 + BaseAgent

## 참조 문서
- 구현 계획: [implementation_plan.md](file:///Users/woosun/.gemini/antigravity/brain/4d64b553-80bb-48b8-ab54-96a5cddd4c07/implementation_plan.md)
- 로드맵: [roadmap.md](file:///Users/woosun/.gemini/antigravity/brain/4d64b553-80bb-48b8-ab54-96a5cddd4c07/roadmap.md)

---

## Step 1: 프로젝트 초기화

1. `/Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/` 디렉토리 생성
2. 전체 디렉토리 구조 생성:
   - `orchestrator/` — LangGraph 오케스트레이터
   - `agents/` — 에이전트 공통 + 개별 에이전트
   - `llm/` — 멀티 모델 클라이언트
   - `integrations/` — Qdrant, Scout 연동
   - `api/` — 오케스트레이터 API 서버
   - `config/` — agents.yaml, models.yaml
3. `requirements.txt` 작성:
   - langgraph, fastapi, uvicorn, openai, anthropic, google-genai
   - qdrant-client, python-dotenv, rank-bm25, pydantic
4. `.env` 파일 생성 — 기존 `lab-research-agents/.env`에서 API 키 복사
5. Next.js 앱 초기화:
   - `ui/` 디렉토리에 생성
   - `npx create-next-app@latest --help`로 옵션 확인 후
   - TypeScript + Tailwind + App Router로 비대화형 실행
6. `docker-compose.yml` 작성 — Qdrant 컨테이너 (기존 포트 6333 유지)
7. `config/agents.yaml`, `config/models.yaml` 초기 설정 파일 작성

## Step 2: BaseAgent + LiteratureAgent

1. `agents/base.py` — BaseAgent ABC, AgentTask, AgentResult 스키마 구현
   - implementation_plan.md의 "핵심 컴포넌트 설계" 섹션 참조
2. `orchestrator/schemas.py` — 공통 타입 정의
3. `integrations/qdrant.py` — Qdrant 공통 클라이언트
   - 이식 원본: `lab-research-agents/app/retrieval/vector_store.py`
4. `integrations/scout_reader.py` — Scout DB 읽기 전용 클라이언트
   - 이식 원본: `lab-research-agents/app/integrations/scout_reader.py`
5. `agents/literature/agent.py` — LiteratureAgent(BaseAgent) 구현
   - 이식 원본: `lab-research-agents/app/agents/prompts.py` (literature + scout 프롬프트)
   - hybrid_search 연동
6. `agents/literature/server.py` — FastAPI 서버 (:8001)
   - 엔드포인트: `/execute` (POST), `/health` (GET)
7. retrieval 모듈 이식:
   - `keyword_store.py` (BM25) ← `lab-research-agents/app/retrieval/keyword_store.py`
   - `hybrid_retriever.py` (RRF) ← `lab-research-agents/app/retrieval/hybrid_retriever.py`
8. 테스트: Literature 서버 단독 기동 → `curl localhost:8001/health` 확인

## 에러 처리 가이드

- **패키지 설치 실패**: 실패한 패키지를 제외하고 나머지 설치, 대안 검색 후 대체
- **Next.js 초기화 실패**: `node --version` 확인, 필요 시 버전 지정 (`@14`)
- **import 경로 오류**: `lab-research-agents`의 `app.*` 경로를 새 구조에 맞게 자동 변환
- **Qdrant 연결 실패**: `docker-compose up -d` 실행하여 컨테이너 기동 확인
- **FastAPI 서버 기동 실패**: `lsof -i :8001`로 포트 충돌 확인, 로그 확인 후 수정

## 완료 기준

- [ ] `lab-orchestrator/` 전체 디렉토리 구조 생성됨
- [ ] `pip install -r requirements.txt` 성공
- [ ] `cd ui && npm run dev` 성공 (기본 Next.js 화면 표시)
- [ ] `python -m agents.literature.server` 기동 → `/health` 200 OK
- [ ] `curl -X POST localhost:8001/execute` → 정상 응답
