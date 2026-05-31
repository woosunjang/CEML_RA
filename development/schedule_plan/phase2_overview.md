# Phase 2 고도화 — 세션 계획 총괄

> 작성일: 2026-05-22
> 기준: 세션당 7시간 업무량

## 현재 완료 상태

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 기반 안정화 (Scout, Hybrid RAG) | ✅ |
| 1 | 오케스트레이터 + 5에이전트 + Next.js UI | ✅ |
| 메모리 | 3-tier (Core/Recall/Archival-Graphiti) | ✅ |
| 모델 | 성능/가성비 프로필 스위칭 | ✅ |
| Debate | Multi-LLM Debate Engine (GPT/Claude/Gemini) | ✅ |

---

## 세션 배정 개요

| 세션 | 주제 | 파일 | 예상 |
|------|------|------|------|
| **4** | Debate Engine 고도화 + 통합 문서화 | `session_4_debate_docs.md` | 7h |
| **5** | 에이전트 체이닝 고도화 | `session_5_chaining.md` | 7h |
| **6** | Slack 오케스트레이터 연동 | `session_6_slack.md` | 7h |
| **7** | UI/UX 고도화 (1/2) — 대시보드 + 지식그래프 | `session_7_ui_part1.md` | 7h |
| **8** | UI/UX 고도화 (2/2) — Debate UI + 반응형 | `session_8_ui_part2.md` | 7h |

---

## 장기 TODO (우선순위 낮음, 나중에 계획)

- [ ] Scout 자동 파이프라인 고도화 (자동 키워드 확장, Weekly Digest, Citation Network)
- [ ] Level 1 자율화 (스케줄러, 작업 큐, 에러 복구, 비용 추적)
- [ ] Level 2 자율화 (Goal Decomposition, Proactive Suggestions)
- [ ] MCP 연동 (외부 도구 표준 인터페이스)
