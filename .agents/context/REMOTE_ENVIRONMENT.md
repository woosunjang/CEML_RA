# Remote Environment Reference

이 파일은 CEML_RA의 원격 운영/검증 환경을 참조하기 위한 메모다.
제품 방향, 개발 우선순위, 런타임 변경 권한의 기준은 항상 `AGENTS.md`와
`docs/ceml-ra-ground-goal-and-phases.md`다.

## 개발 환경: 이 컴퓨터

- **역할**: 코드 작성, AG/Codex/Gemini 인터랙션, 파일 편집
- **사용자**: `woosun`
- **로컬 저장소**: `/Users/woosun/Dev/CEML_RA`
- **소스 코드 source of truth**: GitHub
- **코드 반영 방식**: 개발 환경에서만 commit/push한다. M2 Mac Mini는 실행과
  검증을 위해 GitHub에서 pull만 한다.
- **durable research artifact root**:

  ```text
  /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
  ```

## 운영/검증 환경: M2 Mac Mini

이 정보는 접속과 환경 참조용이다. 현재 rebuild 단계에서는 stale runtime과
watchdog이 의도적으로 중지되어 있으므로, 사용자가 명시적으로 요청하지 않는
한 서비스를 재시작하거나 live store를 변경하지 않는다.

- **역할**: 실제 서비스 구동, 테스트, 검증에 사용할 수 있는 원격 호스트
- **SSH 접속**: `ssh mersoom@Mersoomui-Macmini.local`
- **IP**: `192.168.0.12`
- **원격 저장소 경로**: `/Users/mersoom/Dev/CEML_RA`
- **원격 artifact root**: `/Users/mersoom/Dropbox/Dev/CEML/RA_artifacts`
- **Scout DB path**:
  `/Users/mersoom/Dev/CEML_RA/lab-paper-scout/data/paper_scout.db`
- **코드 반영 방식**: Dropbox 동기화가 아니라 GitHub pull-only 방식이다.
  M2에서 개발하거나 push하지 않는다.
- **기본 브랜치**: `main`
- **작업 브랜치**: 테스트에 필요한 경우에만 checkout한다.
- **Python**: conda 환경 `lab-research-agents` (Python 3.12.13)
- **Node.js**: v25.6.1
- **Docker**: v29.4.3
- **Qdrant 컨테이너**: `lab_qdrant`
- **conda 활성화**:

  ```bash
  source ~/.zshrc 2>/dev/null; conda activate lab-research-agents
  ```

## 기본 규칙

- 코드 작성과 편집은 개발 환경에서 수행한다.
- M2 Mac Mini는 개발 호스트가 아니라 실행/검증 호스트다. 테스트 전에는
  필요에 따라 `git fetch`, 대상 branch checkout, `git pull --ff-only`,
  dirty-state 확인을 수행할 수 있다.
- SSH 키 인증은 설정되어 있으며 비밀번호 입력을 전제로 하지 않는다.
- `.env`에 절대 경로를 넣지 않는다. 가능한 경우 config의 상대 경로 default
  또는 명시적 artifact root 환경변수를 사용한다.
- runtime 상시 서비스 재시작, launchd/watchdog/background worker/scheduler
  구동, Slack/외부 알림 발송, 장시간 운영 검증은 사용자의 명시적 승인 후에만
  수행한다.

## 검증 카테고리와 승인 경계

- **소스 동기화 검증**: M2에서 `git fetch`, 대상 branch checkout,
  `git pull --ff-only`, dirty-state 확인은 승인 없이 수행할 수 있다.
- **정적/빠른 코드 검증**: 같은 코드가 개발 환경에도 있으므로 기본적으로 이
  Mac에서 먼저 수행한다. M2 환경 차이가 검증 대상일 때만 M2에서 실행한다.
- **임시 개발 서버 검증**: 테스트 목적의 foreground/임시 API 또는 UI 서버는
  승인 없이 실행할 수 있다. 테스트 후 종료해야 하며 상시 서비스로 등록하지
  않는다.
- **live store read-only 검증**: Scout DB, Qdrant, Neo4j, Graphiti, KG/RAG
  상태 확인과 read-only query smoke는 승인 없이 수행할 수 있다.
- **live store mutation/ingest/migration**: 일차 개발 이후 DB, KG, RAG를
  초기화할 예정이므로 테스트 목적의 write/ingest/migration은 승인 없이
  진행할 수 있다. 단, 실행 내용과 변경 범위는 결과 보고에 남긴다.
- **runtime/서비스 구동**: 새 runtime, launchd, watchdog, Slack bot,
  background worker, scheduler를 실제로 시작하거나 재시작하는 작업은 사전
  승인을 받는다.
- **Slack/외부 알림 검증**: 실제 Slack 메시지 발송, webhook, scheduled
  alert는 명시적 목표와 승인 후에만 수행한다.
- **장시간/운영 안정성 검증**: overnight run, cron, launchd, Docker 지속
  실행, health monitor는 명시적 목표와 승인 후에만 수행한다.

## SSH 명령 실행 패턴

```bash
# Non-interactive SSH에서는 .zshrc가 완전히 로드되지 않으므로 conda 활성화를 명시한다.
ssh mersoom@Mersoomui-Macmini.local 'source ~/.zshrc 2>/dev/null; conda activate lab-research-agents && cd /Users/mersoom/Dev/CEML_RA/lab-orchestrator && <명령>'

# Node.js 사용 시 Homebrew PATH가 필요할 수 있다.
ssh mersoom@Mersoomui-Macmini.local 'export PATH="/opt/homebrew/bin:$PATH" && <명령>'
```

## 스케줄링 주의

- AG 스케줄러의 cron 표현식은 로컬 시간(KST) 기준으로 해석한다.
- UTC로 변환하지 말고 KST 기준 입력을 사용한다.
- 이는 향후 새 scheduler/cron을 도입할 때의 시간 기준 메모다. 현재 rebuild에서는
  old scheduler/runtime을 기본 개발 맥락으로 쓰지 않는다.

## Known Noisy Success

- Graphiti/Neo4j 초기화 중 이미 존재하는 schema/index에 대해
  `Neo.ClientError.Schema.EquivalentSchemaRuleAlreadyExists` 로그가 출력될 수
  있다. 최종 healthcheck JSON이 `status: "ok"`이고 `graphiti`, `neo4j`,
  `qdrant`, `scout`, `research_thread` 체크가 통과하면 M2 bring-up은 성공으로
  본다.
