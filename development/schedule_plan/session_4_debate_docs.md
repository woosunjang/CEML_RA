# 세션 4 — Debate Engine 고도화 + 통합 문서화

## 참조 문서
- 전략 계획: [implementation_plan.md](file:///Users/woosun/.gemini/antigravity/brain/4d64b553-80bb-48b8-ab54-96a5cddd4c07/implementation_plan.md)
- Debate 워크스루: [walkthrough.md](file:///Users/woosun/.gemini/antigravity/brain/4d64b553-80bb-48b8-ab54-96a5cddd4c07/walkthrough.md)

---

## Step 1: Debate Engine 개선 (2h)

현재 Debate는 동작하지만, 실용성을 높이기 위한 개선이 필요합니다.

### 1-1. Gemini 병목 해소
- gemini-2.5-pro → gemini-2.5-flash로 변경 검토 (R1 35초 → ~10초 예상)
- `config/debate.yaml`에서 모델만 교체 후 A/B 테스트
- 품질 vs 속도 trade-off 평가

### 1-2. 스트리밍 지원
- debate 진행 상황을 SSE로 실시간 전달
- `graph.py`의 `orchestrate_stream` 패턴 참고
- 이벤트: `debate_round_start`, `panelist_response`, `judge_start`, `judge_done`

### 1-3. 라운드 수 동적 조정
- 2라운드 옵션 추가 (간단한 비교 질문에 적합)
- `ChatRequest`에 `debate_rounds: Optional[int]` 필드 추가
- 미지정 시 `debate.yaml` 기본값(3) 사용

---

## Step 2: 통합 문서화 — docs/ 디렉토리 생성 (5h)

### 2-1. `docs/README.md` — 프로젝트 개요 (30분)
- 시스템 비전, 아키텍처 다이어그램
- 빠른 시작 가이드 (서비스 접속 → 첫 대화)
- 기술 스택 표

### 2-2. `docs/user-guide.md` — 사용자 가이드 (2시간)
- 에이전트별 가이드 (📚📎✍️📽️📋)
  - 각 에이전트가 할 수 있는 것
  - 예시 프롬프트 5개씩
  - 팁과 주의사항
- Debate 모드 사용법
  - 적합한 질문 유형
  - 예시 + 예상 소요 시간
- 장기 기억 (Archival Memory) 작동 방식
- 모델 프로필 전환 방법

### 2-3. `docs/api-reference.md` — REST API 참조 (1시간)
- 현재 서버의 모든 엔드포인트 목록화
  - `GET /health`, `GET /agents`, `POST /chat`, `GET /chat/stream`
  - `GET /conversations/{id}`, `GET /memory/search`, `GET /memory/entities`
  - `GET /debate/status`, `POST /debate/classify`
  - `GET /models/profiles`, `POST /models/profile/{name}`
- 각 엔드포인트별: 설명, 파라미터, 응답 스키마, curl 예시

### 2-4. `docs/agent-catalog.md` — 에이전트 카탈로그 (30분)
- `config/agents.yaml` 기반
- 에이전트별: 이름, 아이콘, 기능, 모델(default/heavy), 시스템 프롬프트 요약

### 2-5. `docs/architecture.md` — 아키텍처 상세 (30분)
- 오케스트레이션 파이프라인 (Planner → Router → Executor → Synthesizer)
- 메모리 시스템 (Core/Recall/Archival)
- Debate Engine 구조
- 모델 프로필 시스템

### 2-6. `docs/deployment.md` — 배포·운영 가이드 (30분)
- M2 맥미니 환경 설정
- Docker 컨테이너 (Qdrant, FalkorDB)
- launchd 서비스 등록
- 로그 위치, 모니터링

---

## 검증 기준

- [ ] debate에서 gemini-2.5-flash 사용 시 전체 소요시간 3분 이하
- [ ] docs/ 디렉토리에 6개 문서 완성
- [ ] 각 API 엔드포인트에 curl 예시 포함
- [ ] user-guide에 에이전트별 예시 프롬프트 최소 3개
