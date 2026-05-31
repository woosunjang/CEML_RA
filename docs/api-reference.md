# REST API Reference

Base URL: `http://192.168.0.12:8000`

---

## 시스템

### `GET /health`
서버 상태 확인.

**응답**
```json
{"status": "ok", "service": "orchestrator"}
```

```bash
curl http://192.168.0.12:8000/health
```

---

## 에이전트

### `GET /agents`
등록된 모든 에이전트 목록과 상태.

**응답**
```json
{
  "agents": [
    {
      "name": "literature",
      "description": "논문 수집·분석·문헌 리뷰",
      "icon": "📚",
      "capabilities": ["paper_analysis", "literature_review", "citation_search"],
      "status": "available"
    }
  ]
}
```

```bash
curl http://192.168.0.12:8000/agents
```

---

## 대화

### `POST /chat`
오케스트레이터에 메시지 전송. 자동으로 적절한 에이전트에 라우팅.

**요청 본문**
| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `message` | string | (필수) | 사용자 메시지 |
| `conversation_id` | string | null | 대화 ID (없으면 자동 생성) |
| `workspace` | string | "default" | 워크스페이스 이름 |
| `agent_override` | string | null | 특정 에이전트 강제 지정 |
| `mode` | string | "normal" | `normal` 또는 `debate` |
| `debate_rounds` | int | null | Debate 라운드 수 (2 또는 3) |
| `filters` | object | {} | 검색 필터 |

**응답**
```json
{
  "conversation_id": "abc-123",
  "content": "응답 내용...",
  "agent_name": "literature",
  "citations": [],
  "execution_steps": [],
  "metadata": {}
}
```

```bash
# 기본 대화
curl -X POST http://192.168.0.12:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "NASICON 연구 동향을 알려줘"}'

# 특정 에이전트 지정
curl -X POST http://192.168.0.12:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "퀴즈 5문제 만들어줘", "agent_override": "teaching"}'

# Debate 모드 (2라운드)
curl -X POST http://192.168.0.12:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "질문...", "mode": "debate", "debate_rounds": 2}'
```

### `GET /chat/stream`
SSE 스트리밍으로 실시간 응답.

**파라미터**
| 이름 | 타입 | 설명 |
|------|------|------|
| `message` | string | 사용자 메시지 |
| `conversation_id` | string | 대화 ID |

**이벤트**
- `token`: 텍스트 청크
- `agent`: 처리 중인 에이전트 정보
- `done`: 완료 + 메타데이터

```bash
curl -N "http://192.168.0.12:8000/chat/stream?message=NASICON이란"
```

### `GET /conversations/{conversation_id}`
특정 대화의 기록 조회.

```bash
curl http://192.168.0.12:8000/conversations/abc-123
```

---

## 메모리

### `GET /memory/search`
장기 기억(Archival Memory) 검색.

**파라미터**
| 이름 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `q` | string | (필수) | 검색 쿼리 |
| `limit` | int | 5 | 최대 결과 수 |

**응답**
```json
{
  "query": "도핑 조건",
  "results": [
    {"fact": "NASICON 도핑 조건은 Al 5mol%", "created_at": "2026-05-22T..."}
  ],
  "count": 1
}
```

```bash
curl "http://192.168.0.12:8000/memory/search?q=도핑+조건&limit=3"
```

### `GET /memory/entities`
추출된 엔티티 목록.

**파라미터**
| 이름 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `limit` | int | 20 | 최대 엔티티 수 |

```bash
curl "http://192.168.0.12:8000/memory/entities?limit=10"
```

---

## Knowledge Brief

### `GET /knowledge/briefs`
생성된 Proactive Research Brief 목록.

```bash
curl "http://192.168.0.12:8000/knowledge/briefs?limit=10"
```

### `GET /knowledge/briefs/latest`
가장 최근 생성된 brief 전체 JSON.

```bash
curl http://192.168.0.12:8000/knowledge/briefs/latest
```

### `POST /knowledge/briefs/generate`
Scout DB 근거로 새 Proactive Brief를 생성하고 Markdown/JSON 파일로 저장.
CloudStorage/Dropbox의 SQLite 직접 읽기가 실패하면 임시 로컬 스냅샷으로 재시도한다. 요청 기간의 Scout DB 행이 전혀 없고 같은 기간의 기존 brief가 있으면 기존 artifact를 재사용하며, 응답 `metadata.reused_existing_due_to_empty_source`가 `true`로 표시된다.

**요청 본문**
| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `date` | string | 오늘 | 종료 날짜 (`YYYY-MM-DD`) |
| `days` | int | 1 | 포함할 기간 |
| `query` | string | "" | 선택 토픽/검색어 |
| `min_score` | number | 70 | 근거 포함 최소 관련도 |
| `promote` | bool | true | 90점 이상 논문을 archival queue로 승격 |
| `write_files` | bool | true | `data/knowledge_briefs`, `generated/reports`에 저장 |

```bash
curl -X POST http://192.168.0.12:8000/knowledge/briefs/generate \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-05-31","days":1,"promote":true}'
```

### `GET /knowledge/search`
Scout DB, Qdrant RAG, Archival Memory를 함께 검색.
한 소스가 실패해도 나머지 결과를 반환하고, 실패 정보는 `errors` 배열에 담긴다.

```bash
curl "http://192.168.0.12:8000/knowledge/search?q=materials+ontology&limit=5"
```

### `GET /autonomy/actions`
자율 실행 로그 조회.

```bash
curl "http://192.168.0.12:8000/autonomy/actions?limit=20"
```

---

## Debate Engine

### `GET /debate/status`
Debate Engine 상태 및 설정.

**응답**
```json
{
  "enabled": true,
  "panelists": [
    {"name": "analyst", "model": "gpt-5.4-mini", "provider": "openai"},
    {"name": "critic", "model": "claude-sonnet-4-20250514", "provider": "anthropic"},
    {"name": "synthesizer", "model": "gemini-2.5-flash", "provider": "google"}
  ],
  "rounds": 3,
  "auto_trigger": true,
  "complexity_threshold": 0.7
}
```

```bash
curl http://192.168.0.12:8000/debate/status
```

### `POST /debate/classify`
질문의 복잡도 분류 (iMAD 테스트).

**파라미터**: `q` (string)

```bash
curl -X POST "http://192.168.0.12:8000/debate/classify?q=NASICON이+뭐야"
```

### `GET /debate/stream`
Debate 진행 상황을 SSE로 실시간 스트리밍.

**파라미터**
| 이름 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `q` | string | (필수) | 질문 |
| `rounds` | int | 3 | 라운드 수 |

**이벤트**
- `debate_start`: 토론 시작 (패널리스트, 라운드 수)
- `round_start`: 라운드 시작
- `panelist_done`: 패널리스트 응답 완료
- `judge_start`: Judge 종합 시작
- `debate_done`: 최종 답변 포함

```bash
curl -N "http://192.168.0.12:8000/debate/stream?q=질문&rounds=2"
```

---

## 모델 프로필

### `GET /models/profiles`
사용 가능한 모델 프로필 목록.

```bash
curl http://192.168.0.12:8000/models/profiles
```

### `POST /models/profile/{name}`
모델 프로필 전환.

| name | 설명 |
|------|------|
| `performance` | 성능 우선 모델 세트 |
| `cost` | 가성비 모델 세트 |

```bash
curl -X POST http://192.168.0.12:8000/models/profile/cost
```

---

## 워크스페이스

### `GET /workspaces`
워크스페이스 목록.

### `POST /workspaces`
새 워크스페이스 생성.

### `GET /workspaces/{name}`
워크스페이스 상세 정보.
