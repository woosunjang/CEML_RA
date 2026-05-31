# Slack App 설정 가이드

## 1. 슬래시 커맨드 등록

https://api.slack.com/apps 에서 Lab Orchestrator 앱 선택 → **Slash Commands** 메뉴

다음 커맨드를 하나씩 등록 (Socket Mode이므로 Request URL은 자동 처리):

| 커맨드 | 설명 | 사용법 |
|--------|------|--------|
| `/ask` | 일반 질문 | `/ask NASICON 도핑 조건 알려줘` |
| `/debate` | 3-LLM 토론 모드 | `/debate 고체전해질 장단점 비교` |
| `/memsearch` | 장기 기억 검색 | `/memsearch NASICON` |
| `/agents` | 에이전트 상태 조회 | `/agents` |
| `/profile` | 모델 프로필 전환 | `/profile cost` |
| `/brief` | Proactive Research Brief 생성 | `/brief today`, `/brief week`, `/brief topic materials ontology` |
| `/labstatus` | 시스템 상태 조회 | `/labstatus` |
| `/report` | 수동 리포트 생성 | `/report daily` 또는 `/report weekly` |

### 등록 절차
1. **Create New Command** 클릭
2. **Command**: `/ask`
3. **Short Description**: 일반 질문
4. **Usage Hint**: 질문 내용
5. **Save** 클릭
6. 나머지 커맨드도 동일하게 반복

## 2. Event Subscriptions 설정

**Features → Event Subscriptions** 메뉴:
- **Enable Events**: On
- **Subscribe to bot events**:
  - `app_mention` — 채널에서 @bot 멘션 수신
  - `message.im` — DM 수신

## 3. OAuth & Permissions

**Features → OAuth & Permissions** 메뉴:
- **Bot Token Scopes** (필수):
  - `chat:write` — 메시지 전송
  - `commands` — 슬래시 커맨드
  - `app_mentions:read` — 멘션 수신
  - `files:write` — 파일 업로드
  - `channels:history` — 채널 기록 접근
  - `groups:history` — 프라이빗 채널 기록
  - `im:history` — DM 기록 접근
  - `im:read` — DM 읽기
  - `im:write` — DM 쓰기

스코프 변경 후 **Reinstall to Workspace** 클릭

## 4. Socket Mode

**Settings → Socket Mode** 메뉴:
- **Enable Socket Mode**: On
- App-Level Token이 `.env`의 `SLACK_APP_TOKEN`과 일치하는지 확인

## 5. 봇 채널 초대

Slack 워크스페이스에서:
1. `#lab-reports` 채널 생성 (리포트 수신용)
2. 해당 채널에서 `/invite @Lab Orchestrator` 입력
3. 필요 시 `#system-alerts`, `#research-papers` 채널에도 초대

## 6. .env 설정

```bash
# 리포트 전송 채널 (채널 ID 또는 #channel-name)
SLACK_REPORT_CHANNEL=#lab-reports

# 또는 DM으로 받으려면 본인 Slack User ID 입력
# SLACK_REPORT_CHANNEL=U0XXXXXXXX
```

Slack User ID 확인: 본인 프로필 클릭 → **⋮** 메뉴 → **Copy member ID**

## 7. 서비스 재시작

```bash
# M2 Mac Mini에서
launchctl unload ~/Library/LaunchAgents/kr.ceml.lab-slack-bot.plist
launchctl load ~/Library/LaunchAgents/kr.ceml.lab-slack-bot.plist
```

## 8. 테스트

1. DM에서 `@Lab Orchestrator 테스트` → 응답 확인
2. `/labstatus` 입력 → 시스템 상태 표시
3. `/report daily` → 데일리 리포트 생성
4. `/brief today` → 오늘자 Proactive Brief 생성
