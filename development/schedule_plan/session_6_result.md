# 세션 6 결과 — Slack 오케스트레이터 연동

> 완료일: 2026-05-23

## Step 1: Slack App + Bolt 서버 ✅

### 환경
- Slack Bot Token + App Token: `.env`에 설정 완료
- `slack-bolt>=1.28.0`, `slack-sdk>=3.41.0`, `aiohttp>=3.13.5` 설치 완료
- Socket Mode 사용 (별도 HTTP 서버 불필요)

### `integrations/slack_bot.py` (295줄)
- `AsyncApp` (Socket Mode) 기반
- 멘션 핸들러 (`@bot 질문`)
- DM 핸들러 (channel_type='im')
- 마크다운 → Slack mrkdwn 변환 (`_md_to_slack`)
- 장문 자동 분할 (`_split_message`, 3000자 단위)

## Step 2: 슬래시 커맨드 ✅

| 커맨드 | 기능 | API |
|--------|------|-----|
| `/ask` | 일반 질문 | POST /chat |
| `/debate` | Debate 모드 + 실시간 진행상황 | POST /debate/stream (SSE) |
| `/search` | 장기 기억 검색 (Block Kit) | GET /memory/search |
| `/agents` | 에이전트 상태 (Block Kit) | GET /agents |
| `/profile` | 모델 프로필 전환 | POST /models/profile |

### `/debate` 구현 세부
- SSE 스트리밍으로 진행 상황 수신
- 이벤트별 Slack 메시지: round_start, panelist_done, judge_start, debate_done
- 최종 답변은 스레드로 전달

## Step 3: 알림 인프라 ✅

### `integrations/slack_notifier.py` (170줄)
| 함수 | 용도 |
|------|------|
| `slack_notify(channel, text)` | 범용 알림 (Bot Token) |
| `slack_notify_webhook(text)` | Webhook 알림 |
| `notify_error(agent, error)` | → #system-alerts 에이전트 오류 |
| `notify_pipeline_done(user, pipeline, status)` | → DM 파이프라인 완료 |
| `notify_scout_papers(papers)` | → #research-papers 신규 논문 |
| `notify_weekly_digest()` | 주간 다이제스트 (stub) |

- 알림 실패 시 로그만 남기고 진행 (블로킹 방지)

## Step 4: 서비스 등록 + 통합 테스트 ✅

### launchd 등록
- `kr.ceml.lab-slack-bot.plist` → `~/Library/LaunchAgents/`
- `launchctl load` 성공, 상시 구동 확인

### 구동 확인
```
launchctl list | grep ceml:
12836  0  kr.ceml.lab-slack-bot     ← NEW
31228  0  kr.ceml.lab-orchestrator
50193  0  kr.ceml.lab-ui
```

### 로그 확인
```
2026-05-23 11:03:05 ⚡️ Bolt app is running!
```

### 테스트 결과
- [x] Socket Mode 연결 성공
- [x] Import + 유틸 함수 (md 변환, 메시지 분할) 동작 확인
- [x] launchd 상시 구동 등록 완료
- [ ] Webhook 알림: URL 만료 추정 (사용자 재설정 필요)
- [ ] Bot Token 알림: 봇이 채널에 초대되어야 동작 (사용자 작업)

## 사용자 조치 필요 사항

1. **Slack App 슬래시 커맨드 등록**: api.slack.com/apps에서 `/ask`, `/debate`, `/search`, `/agents`, `/profile` 등록
2. **봇 채널 초대**: `#system-alerts`, `#research-papers`, `#general` 등에 봇 초대
3. **Webhook URL 갱신**: `.env`의 `SLACK_WEBHOOK_API` 업데이트 (선택)

## 수정 파일

| 파일 | 변경 |
|------|------|
| `integrations/slack_bot.py` | [NEW] Slack Bot (295줄) |
| `integrations/slack_notifier.py` | [NEW] 알림 인프라 (170줄) |
| `config/kr.ceml.lab-slack-bot.plist` | [NEW] launchd 설정 |
| `requirements.txt` | slack-bolt, slack-sdk 추가 |
