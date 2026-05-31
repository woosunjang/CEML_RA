# CEML Research Assistant — 프로젝트 규칙

## 인프라 환경

### 개발 환경 (이 컴퓨터)
- **역할**: 코드 작성, AG 인터랙션, 파일 편집
- **사용자**: woosun
- **코드 동기화**: Dropbox (`/Users/woosun/Dropbox/Dev/CEML_RA/`)

### 운영 환경 (M2 Mac Mini)
- **역할**: 실제 서비스 구동, 테스트, 검증
- **SSH 접속**: `ssh mersoom@Mersoomui-Macmini.local`
- **IP**: 192.168.0.12
- **코드 동기화**: Dropbox (개발 환경과 동일 경로로 동기화)
- **Python**: conda 환경 `lab-research-agents` (Python 3.12.13)
- **Node.js**: v25.6.1
- **Docker**: v29.4.3 (Qdrant 컨테이너 `lab_qdrant` 상시 구동)
- **conda 활성화**: `source ~/.zshrc 2>/dev/null; conda activate lab-research-agents`

### 규칙
- 코드 작성/편집은 **개발 환경(이 컴퓨터)**에서 수행
- `pip install`, 서버 기동, 테스트, 검증은 **M2 Mac Mini(SSH)**에서 수행
- SSH 키 인증 설정 완료 (비밀번호 입력 불가)
- `.env`에 절대 경로 사용 금지 — config.py의 상대 경로 default 활용

### SSH 명령 실행 패턴
```bash
# Non-interactive SSH에서는 .zshrc가 완전히 로드되지 않으므로 conda + homebrew 명시 필요
ssh mersoom@Mersoomui-Macmini.local 'source ~/.zshrc 2>/dev/null; conda activate lab-research-agents && cd ~/Dropbox/Dev/CEML_RA/lab-orchestrator && <명령>'

# Node.js 사용 시 homebrew PATH 추가 필요
ssh mersoom@Mersoomui-Macmini.local 'export PATH="/opt/homebrew/bin:$PATH" && <명령>'
```


## 프로젝트 구조

```
CEML_RA/
├── lab-orchestrator/    # 멀티 에이전트 오케스트레이션 시스템
│   ├── agents/          # 에이전트 (literature, teaching, writing, presentation, project)
│   ├── orchestrator/    # Planner → Router → Executor → Synthesizer
│   ├── api/             # FastAPI 오케스트레이터 서버 (:8000)
│   ├── integrations/    # Qdrant, Scout, BM25
│   ├── llm/             # 멀티 모델 LLM 클라이언트
│   ├── config/          # agents.yaml, models.yaml
│   └── ui/              # Next.js 채팅 UI (:3000)
├── lab-research-agents/ # Phase 0 — 기존 RAG 시스템 (레거시)
├── lab-paper-scout/     # Phase 0 — 논문 자동 수집 파이프라인
└── development/         # 개발 계획, 스케줄, 결과 보고서
```

## 크론 스케줄링 주의
- AG 스케줄러의 크론 표현식은 **로컬 시간(KST)** 기준
- UTC 변환 없이 KST 그대로 입력할 것
