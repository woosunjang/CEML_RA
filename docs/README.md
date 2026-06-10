# CEML Lab Orchestrator

> 연구 활동을 지원하는 멀티 에이전트 AI 오케스트레이션 시스템

## 시스템 비전

CEML Lab Orchestrator는 재료공학·전산재료과학 연구를 위한 **5개 전문 에이전트**가 협업하는 AI 연구 비서입니다. 논문 분석, 강의 설계, 논문 작성, 발표 자료 생성, 과제 관리를 하나의 인터페이스에서 수행합니다.

## 아키텍처

```
┌─────────────────────────────────────────────┐
│              사용자 인터페이스                │
│    Next.js UI (:3000)  │  Slack Bot  │ API  │
├─────────────────────────────────────────────┤
│           오케스트레이터 (:8000)              │
│  Planner → Router → Executor → Synthesizer  │
├───────┬───────┬───────┬──────────┬──────────┤
│  📚   │  🎓   │  ✍️   │   📽️    │   📋    │
│ Lit.  │ Teach │ Write │  Pres.   │ Project  │
├───────┴───────┴───────┴──────────┴──────────┤
│              🏛️ Debate Engine                │
│    GPT · Claude · Gemini  3라운드 토론        │
├─────────────────────────────────────────────┤
│              메모리 시스템                    │
│  Core │ Recall │ Archival (Graphiti+FalkorDB)│
├─────────────────────────────────────────────┤
│              데이터 계층                      │
│  Qdrant (RAG) │ Scout DB │ FalkorDB (Graph) │
└─────────────────────────────────────────────┘
```

## 기술 스택

| 계층 | 기술 |
|------|------|
| Backend | Python 3.12, FastAPI, asyncio |
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| LLM | OpenAI (GPT-5.4), Anthropic (Claude Sonnet 4), Google (Gemini 2.5) |
| Vector DB | Qdrant (Hybrid RAG: Dense + BM25) |
| Knowledge Graph | FalkorDB + Graphiti (Archival Memory) |
| Infra | Docker, launchd, M2 Mac Mini |

## 빠른 시작

### 1. 서비스 접속

- **Web UI**: `http://192.168.0.12:3000`
- **API**: `http://192.168.0.12:8000`
- **API 문서**: `http://192.168.0.12:8000/docs` (Swagger)

### 2. 첫 대화

```bash
curl -X POST http://192.168.0.12:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "NASICON 고체전해질의 최근 연구 동향을 알려줘"}'
```

### 3. Debate 모드

```bash
curl -X POST http://192.168.0.12:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "질문...", "mode": "debate", "debate_rounds": 2}'
```

## 문서 목록

| 문서 | 내용 |
|------|------|
| [user-guide.md](user-guide.md) | 에이전트별 사용법, 예시 프롬프트, 팁 |
| [api-reference.md](api-reference.md) | REST API 전체 참조 + curl 예시 |
| [agent-catalog.md](agent-catalog.md) | 에이전트 상세 카탈로그 |
| [architecture.md](architecture.md) | 시스템 아키텍처 상세 |
| [deployment.md](deployment.md) | M2 맥미니 배포·운영 가이드 |
| [artifact-runtime-boundary.md](artifact-runtime-boundary.md) | Stage 0 source/artifact/runtime storage boundary |
| [ceml-ra-2week-research-value-cycle.md](ceml-ra-2week-research-value-cycle.md) | Canonical 2-week research-value validation cycle |
| [ceml-ra-main-rebuild-development-goal-2026-06-10.md](ceml-ra-main-rebuild-development-goal-2026-06-10.md) | Current main-derived rebuild goal and storage boundary |
