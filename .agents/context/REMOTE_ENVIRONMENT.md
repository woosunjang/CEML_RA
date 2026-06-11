# Remote Environment Reference

이 파일은 CEML_RA의 원격 운영/검증 환경을 참조하기 위한 메모다.
제품 방향, 개발 우선순위, 런타임 변경 권한의 기준은 항상 `AGENTS.md`와
`docs/ceml-ra-ground-goal-and-phases.md`다.

## 개발 환경: 이 컴퓨터

- **역할**: 코드 작성, AG/Codex/Gemini 인터랙션, 파일 편집
- **사용자**: `woosun`
- **로컬 저장소**: `/Users/woosun/Dropbox/Dev/CEML_RA`
- **소스 코드 source of truth**: GitHub
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
- **코드 동기화**: Dropbox 기반 동기화 경로 사용
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
- 원격 Mac Mini에서 `pip install`, 서버 기동, 테스트, 검증이 필요하면 먼저
  `AGENTS.md`의 runtime guardrail과 사용자 요청 범위를 확인한다.
- SSH 키 인증은 설정되어 있으며 비밀번호 입력을 전제로 하지 않는다.
- `.env`에 절대 경로를 넣지 않는다. 가능한 경우 config의 상대 경로 default
  또는 명시적 artifact root 환경변수를 사용한다.
- runtime service, live DB, KG/RAG store, Scout DB, Slack mutation은 사용자의
  명시적 요청 없이는 수행하지 않는다.

## SSH 명령 실행 패턴

```bash
# Non-interactive SSH에서는 .zshrc가 완전히 로드되지 않으므로 conda 활성화를 명시한다.
ssh mersoom@Mersoomui-Macmini.local 'source ~/.zshrc 2>/dev/null; conda activate lab-research-agents && cd ~/Dropbox/Dev/CEML_RA/lab-orchestrator && <명령>'

# Node.js 사용 시 Homebrew PATH가 필요할 수 있다.
ssh mersoom@Mersoomui-Macmini.local 'export PATH="/opt/homebrew/bin:$PATH" && <명령>'
```

## 스케줄링 주의

- AG 스케줄러의 cron 표현식은 로컬 시간(KST) 기준으로 해석한다.
- UTC로 변환하지 말고 KST 기준 입력을 사용한다.
- 단, 현재 rebuild에서는 old scheduler/runtime을 기본 개발 맥락으로 쓰지
  않는다.
