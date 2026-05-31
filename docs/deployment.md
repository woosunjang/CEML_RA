# 배포·운영 가이드

## 운영 환경

| 항목 | 값 |
|------|-----|
| 하드웨어 | Mac Mini M2, 16GB RAM |
| OS | macOS (최신) |
| IP | 192.168.0.12 |
| SSH | `ssh mersoom@Mersoomui-Macmini.local` |
| Python | conda `lab-research-agents` (3.12.13) |
| Node.js | v25.6.1 |
| Docker | v29.4.3 |

---

## 서비스 구성

| 서비스 | 포트 | 관리 방식 |
|--------|------|----------|
| Orchestrator API | 8000 | launchd |
| Next.js UI | 3000 | launchd |
| Qdrant | 6333 | Docker (`lab_qdrant`) |
| FalkorDB | 6379 | Docker (`lab_falkordb`) |

---

## Docker 컨테이너

### Qdrant (벡터 DB)
```bash
# 상태 확인
docker ps | grep qdrant

# 시작
docker start lab_qdrant

# 처음 생성
docker run -d --name lab_qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant:latest
```

### FalkorDB (지식 그래프)
```bash
# 상태 확인
docker ps | grep falkordb

# 시작
docker start lab_falkordb

# 처음 생성
docker run -d --name lab_falkordb \
  -p 6379:6379 \
  -v falkordb_data:/data \
  --restart unless-stopped \
  falkordb/falkordb:latest
```

---

## launchd 서비스

### Orchestrator API

파일: `~/Library/LaunchAgents/kr.ceml.lab-orchestrator.plist`

```bash
# 상태 확인
launchctl list | grep ceml

# 시작
launchctl load ~/Library/LaunchAgents/kr.ceml.lab-orchestrator.plist

# 중지
launchctl unload ~/Library/LaunchAgents/kr.ceml.lab-orchestrator.plist

# 재시작
launchctl unload ~/Library/LaunchAgents/kr.ceml.lab-orchestrator.plist
launchctl load ~/Library/LaunchAgents/kr.ceml.lab-orchestrator.plist
```

### Next.js UI

파일: `~/Library/LaunchAgents/kr.ceml.lab-ui.plist`

동일한 `launchctl load/unload` 패턴 사용.

---

## 로그 위치

| 서비스 | stdout | stderr |
|--------|--------|--------|
| Orchestrator | `~/Dropbox/Dev/CEML_RA/lab-orchestrator/logs/orchestrator.log` | `~/Dropbox/Dev/CEML_RA/lab-orchestrator/logs/orchestrator.error.log` |
| Next.js UI | `~/Dropbox/Dev/CEML_RA/lab-orchestrator/logs/ui.log` | `~/Dropbox/Dev/CEML_RA/lab-orchestrator/logs/ui.error.log` |

```bash
# 실시간 로그
tail -f ~/Dropbox/Dev/CEML_RA/lab-orchestrator/logs/orchestrator.error.log

# 최근 에러 확인
tail -20 ~/Dropbox/Dev/CEML_RA/lab-orchestrator/logs/orchestrator.error.log | grep ERROR
```

---

## 모니터링

### 헬스체크

```bash
# API 서버
curl http://localhost:8000/health

# Qdrant
curl http://localhost:6333/healthz

# FalkorDB
redis-cli -p 6379 PING
```

### 에이전트 상태
```bash
curl http://localhost:8000/agents
```

### Debate Engine 상태
```bash
curl http://localhost:8000/debate/status
```

---

## 환경 변수

`.env` 파일: `~/Dropbox/Dev/CEML_RA/lab-orchestrator/.env`

| 변수 | 설명 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `ANTHROPIC_API_KEY` | Anthropic API 키 |
| `GOOGLE_API_KEY` | Google AI API 키 |
| `OPENAI_CHAT_MODEL` | 기본 OpenAI 모델 |
| `OPENAI_EMBEDDING_MODEL` | 임베딩 모델 |
| `QDRANT_URL` | Qdrant 접속 URL |
| `QDRANT_COLLECTION` | 기본 컬렉션 이름 |
| `SCOUT_DB_PATH` | Scout SQLite DB 경로 |

> ⚠️ `.env`에 절대 경로 사용 금지 — `config.py`의 상대 경로 default 활용

---

## 업데이트 절차

코드는 Dropbox로 개발 환경↔운영 환경 간 자동 동기화됩니다.

1. 개발 환경에서 코드 수정
2. Dropbox 동기화 대기 (~5초)
3. M2 맥미니에서 서비스 재시작:
   ```bash
   ssh mersoom@Mersoomui-Macmini.local \
     'launchctl unload ~/Library/LaunchAgents/kr.ceml.lab-orchestrator.plist && \
      sleep 2 && \
      launchctl load ~/Library/LaunchAgents/kr.ceml.lab-orchestrator.plist'
   ```
4. 헬스체크 확인:
   ```bash
   ssh mersoom@Mersoomui-Macmini.local 'curl -s http://localhost:8000/health'
   ```
