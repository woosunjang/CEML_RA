# 🚀 lab-paper-scout 맥미니 배포 가이드

이 문서는 **별도 M2 Pro 맥미니**에 lab-paper-scout 데몬을 설치하는 절차입니다.

## 전제 조건

- macOS (Apple Silicon)
- Dropbox가 설치되어 있고 `~/Dropbox/Dev/CEML_RA/lab-paper-scout/` 경로가 동기화된 상태
- 인터넷 연결

---

## Step 1: Python 환경 설정

### Option A: Conda (권장)

```bash
# Miniconda 설치 (이미 있으면 스킵)
curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh
bash Miniconda3-latest-MacOSX-arm64.sh

# 환경 생성
conda create -n lab-research-agents python=3.12 -y
conda activate lab-research-agents

# 의존성 설치
pip install -r ~/Dropbox/Dev/CEML_RA/lab-paper-scout/requirements.txt
```

### Option B: venv

```bash
python3.12 -m venv ~/envs/lab-paper-scout
source ~/envs/lab-paper-scout/bin/activate
pip install -r ~/Dropbox/Dev/CEML_RA/lab-paper-scout/requirements.txt
```

### Python 경로 확인 (이후 필요)

```bash
which python
# 예: /Users/<username>/anaconda3/envs/lab-research-agents/bin/python
# 또는: /Users/<username>/envs/lab-paper-scout/bin/python
```

이 경로를 메모해 두세요. Step 3에서 plist에 넣어야 합니다.

---

## Step 2: 환경변수 설정

`~/.zshrc`에 추가:

```bash
# lab-paper-scout API keys
export GEMINI_API_KEY="여기에_키_입력"
export S2_API_KEY="여기에_키_입력"
export SLACK_WEBHOOK_API="여기에_웹훅_URL_입력"
export OPENAI_API_KEY="여기에_키_입력"
```

적용:

```bash
source ~/.zshrc
```

### 동작 확인

```bash
conda activate lab-research-agents  # 또는 source ~/envs/.../activate
cd ~/Dropbox/Dev/CEML_RA/lab-paper-scout
python run.py daily
```

슬랙에 일간 보고가 오면 성공입니다.

---

## Step 3: launchd 서비스 등록 (자동 실행)

### 3-1. host-local plist 파일 생성

프로젝트에 포함된 `com.ceml.paper-scout.plist`는 template입니다. 실제 API key,
Slack webhook, local path를 이 tracked 파일에 직접 쓰지 않습니다. 먼저 host-local
copy를 만들고, 그 파일만 이 맥미니 환경에 맞게 수정합니다:

```bash
cd ~/Dropbox/Dev/CEML_RA/lab-paper-scout
cp com.ceml.paper-scout.plist com.ceml.paper-scout.local.plist
```

`com.ceml.paper-scout.local.plist`에서 아래 값을 수정합니다:

```xml
<!-- Step 1에서 확인한 Python 경로 -->
<string>/Users/<username>/anaconda3/envs/lab-research-agents/bin/python</string>

<!-- Dropbox 경로 (username 확인) -->
<string>/Users/<username>/Dropbox/Dev/CEML_RA/lab-paper-scout/run.py</string>

<!-- 환경변수 (실제 키 값으로 교체) -->
<key>GEMINI_API_KEY</key>
<string>실제_키_값</string>
<key>S2_API_KEY</key>
<string>실제_키_값</string>
<key>SLACK_WEBHOOK_API</key>
<string>실제_웹훅_URL</string>
<key>OPENAI_API_KEY</key>
<string>실제_키_값</string>

<!-- PATH에 Python 경로 포함 -->
<key>PATH</key>
<string>/Users/<username>/anaconda3/envs/lab-research-agents/bin:/usr/local/bin:/usr/bin:/bin</string>
```

> 중요: launchd는 `.zshrc`를 읽지 않으므로 API 키는 launchd가 읽는 host-local plist
> 안에 있어야 합니다. 단, repo에 commit되는 `com.ceml.paper-scout.plist`에는 절대 실제
> 값을 넣지 않습니다. `com.ceml.paper-scout.local.plist`는 `.gitignore` 대상입니다.

### 3-2. 서비스 등록

```bash
# LaunchAgents 폴더에 host-local plist 복사
cp ~/Dropbox/Dev/CEML_RA/lab-paper-scout/com.ceml.paper-scout.local.plist ~/Library/LaunchAgents/com.ceml.paper-scout.plist

# 서비스 로드 (즉시 시작)
launchctl load ~/Library/LaunchAgents/com.ceml.paper-scout.plist
```

### 3-3. 확인

```bash
# 프로세스 확인 (PID와 exit code 0이 보이면 성공)
launchctl list | grep paper-scout

# 로그 확인
tail -f ~/Dropbox/Dev/CEML_RA/lab-paper-scout/logs/launchd_stderr.log
```

정상이면 아래와 같은 로그가 출력됩니다:

```
lab-paper-scout daemon started
  Collection: every 24h
  Inbox poll: every 6h
  Daily digest: 8:00
  Weekly digest: monday 7:00
  Restart watch: data/.restart (every 30s)
```

---

## 코드 변경 후 재시작

Dropbox 동기화로 코드를 수정한 후, 데몬을 재시작하려면:

### 방법 1: CLI (권장)

```bash
# 어느 머신에서든 (Dropbox 동기화됨)
cd ~/Dropbox/Dev/CEML_RA/lab-paper-scout
python run.py reload
```

→ 데몬이 30초 이내에 자동으로 재시작됩니다.

### 방법 2: 직접 마커 생성

```bash
touch ~/Dropbox/Dev/CEML_RA/lab-paper-scout/data/.restart
```

---

## 운영 명령어

```bash
# 서비스 중지
launchctl unload ~/Library/LaunchAgents/com.ceml.paper-scout.plist

# 서비스 재시작
launchctl unload ~/Library/LaunchAgents/com.ceml.paper-scout.plist
launchctl load ~/Library/LaunchAgents/com.ceml.paper-scout.plist

# 수동 실행 (디버깅용)
conda activate lab-research-agents
cd ~/Dropbox/Dev/CEML_RA/lab-paper-scout
python run.py daemon        # 전체 데몬
python run.py daily          # 일간 보고만
python run.py digest         # 주간 보고만
python run.py inbox          # 인박스 확인만
python run.py run            # 수집+처리+분석 1회
```

---

## 스케줄 설정 변경

`config/config.yaml`의 `schedule` 섹션을 수정하면 됩니다. Dropbox 동기화 후 서비스 재시작:

```bash
launchctl unload ~/Library/LaunchAgents/com.ceml.paper-scout.plist
launchctl load ~/Library/LaunchAgents/com.ceml.paper-scout.plist
```

---

## 트러블슈팅

| 증상 | 확인 |
|------|------|
| 서비스 시작 안 됨 | `launchctl list \| grep paper` → exit code 확인 |
| Python not found | plist의 `ProgramArguments` 경로가 정확한지 확인 |
| API 에러 | plist의 `EnvironmentVariables`에 키가 정확히 들어갔는지 확인 |
| 로그 안 생김 | `logs/` 디렉토리가 존재하는지 확인 (`mkdir -p logs`) |
| Slack 안 옴 | `python run.py daily`로 수동 테스트 |
