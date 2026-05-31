# 세션 6 — Slack 오케스트레이터 연동

## 참조 문서
- 현재 API: [server.py](file:///Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/api/server.py)
- Slack Bolt 문서: https://slack.dev/bolt-python/

---

## 배경

현재 오케스트레이터와의 상호작용은 Next.js UI 또는 직접 API 호출만 가능합니다.
Slack 연동으로:
- 모바일에서도 즉시 접근 가능
- 팀원과 대화 공유 용이
- 알림·리포트 자동 전송 채널 확보
- `/debate`, `/search` 등 슬래시 커맨드로 빠른 접근

---

## Step 1: Slack App 설정 + Bolt 서버 (2h)

### 1-1. Slack App 생성
- https://api.slack.com/apps 에서 앱 생성
- Bot Token Scopes 설정:
  - `chat:write` — 메시지 전송
  - `commands` — 슬래시 커맨드
  - `app_mentions:read` — 멘션 수신
  - `files:write` — 파일 업로드 (PPT, 문서 등)
  - `channels:history`, `groups:history` — 대화 기록 접근
- Event Subscriptions 활성화:
  - `app_mention`, `message.im` (DM)
- Slash Commands 등록:
  - `/ask` — 일반 질문
  - `/debate` — debate 모드
  - `/search` — 장기 기억 검색
  - `/agents` — 에이전트 목록
  - `/profile` — 모델 프로필 전환

### 1-2. 환경 설정
- `.env`에 추가:
  ```
  SLACK_BOT_TOKEN=xoxb-...
  SLACK_APP_TOKEN=xapp-...  # Socket Mode용
  SLACK_SIGNING_SECRET=...
  ```
- `requirements.txt`에 추가:
  ```
  slack-bolt>=1.18.0
  slack-sdk>=3.27.0
  ```

### 1-3. `integrations/slack_bot.py` 구현
- Slack Bolt (Socket Mode) 서버
- 메시지 핸들러: `@bot 질문` → `POST /chat` → 결과 반환
- 긴 응답 스레드 처리 (3000자 이상 → 스레드로 분할)
- 마크다운 → Slack mrkdwn 변환

---

## Step 2: 슬래시 커맨드 구현 (2h)

### 2-1. `/ask` — 일반 질문
```python
@app.command("/ask")
async def handle_ask(ack, say, command):
    await ack()
    # 즉시 "처리 중..." 메시지
    msg = await say(f"🔄 처리 중... `{command['text'][:50]}`")
    # API 호출
    response = await call_orchestrator(command["text"])
    # 결과 업데이트
    await say(response, thread_ts=msg["ts"])
```

### 2-2. `/debate` — Debate 모드
- `/debate 질문` → `POST /chat {mode: "debate"}`
- 진행 상황 실시간 업데이트:
  - "🟢 R1: analyst 응답 중..."
  - "🟣 R1: critic 응답 중..."
  - "🔵 R1: synthesizer 응답 중..."
  - "⚖️ Judge 종합 중..."
- 최종 답변을 스레드에 전달

### 2-3. `/search` — 장기 기억 검색
- `/search NASICON 도핑` → `GET /memory/search?q=...`
- 결과를 Block Kit 포맷으로 표시

### 2-4. `/agents` — 에이전트 상태
- `GET /agents` → Block Kit 카드로 에이전트 목록 표시

### 2-5. `/profile` — 모델 프로필 전환
- `/profile cost` → `POST /models/profile/cost`
- `/profile performance` → `POST /models/profile/performance`

---

## Step 3: 백그라운드 알림 + 자동 리포트 (1.5h)

### 3-1. 알림 인프라
- `integrations/slack_notifier.py`
- `async def notify(channel, message, blocks=None)` — 범용 알림
- 실패 시 로그만 남기고 진행 (알림 실패가 작업을 중단하면 안 됨)

### 3-2. 자동 알림 이벤트
- Scout 신규 논문 수집 완료 → `#research-papers` 채널에 요약
- 파이프라인 완료 → 요청자 DM
- 에이전트 실행 오류 → `#system-alerts` 채널

### 3-3. Weekly Digest (향후 Scout 고도화와 연결)
- 크론 스케줄에 연결점만 마련: `notify_weekly_digest()`
- 실제 구현은 Scout 고도화 세션에서

---

## Step 4: 서비스 등록 + 통합 테스트 (1.5h)

### 4-1. launchd 등록
- `kr.ceml.lab-slack-bot.plist` — M2 맥미니에 상시 구동
- 오케스트레이터와 동일한 방식

### 4-2. 통합 테스트
- DM으로 `@bot NASICON 도핑 조건 알려줘` → 정상 응답
- `/debate 고체전해질 장단점 비교` → debate 실행 + 결과 수신
- `/search NASICON` → 장기 기억 검색 결과
- `/profile cost` → 모델 프로필 전환 확인

---

## 검증 기준

- [ ] Slack DM으로 질문 → 30초 이내 응답
- [ ] `/debate` 커맨드 → debate 진행 상황 실시간 업데이트
- [ ] `/search` → 장기 기억 검색 결과 Block Kit 표시
- [ ] 에이전트 오류 시 `#system-alerts`에 자동 알림
- [ ] M2 맥미니에서 launchd로 상시 구동
