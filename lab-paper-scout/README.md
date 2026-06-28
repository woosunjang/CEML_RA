# lab-paper-scout 🔭

자동 논문 수집 → 분석 → 보고 파이프라인 (ArXiv + Semantic Scholar)

---

## 빠른 시작

### 1. 환경 설정

```bash
cd lab-paper-scout
conda activate lab-research-agents
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
export GEMINI_API_KEY="your-gemini-api-key"
export SLACK_WEBHOOK_API="https://hooks.slack.com/services/..."   # 슬랙 알림 (선택)
export S2_API_KEY="your-s2-key"                                   # S2 API 키 (선택, 없으면 rate limit)
```

### 3. 토픽 설정

`config/config.yaml`에서 관심 토픽을 추가/수정:

```yaml
topics:
  - name: "battery_materials"
    display_name: "Next-Generation Battery Materials Design"
    priority: 1
    keywords: ["solid-state electrolytes", "battery materials informatics"]
    arxiv_categories: ["cond-mat.mtrl-sci"]
    semantic_scholar_fields: ["Materials Science", "Chemistry"]
```

---

## 실행 모드: `run` vs `daemon`

### `python run.py run` — 일회성 실행 (수동)

수집 → 처리 → 분석을 **한 번** 실행하고 종료합니다.
개발/테스트 중 특정 단계를 수동으로 돌릴 때 사용합니다.

```bash
python run.py run          # 수집+처리+분석 1회 실행
```

### `python run.py daemon` — 자동 상시 가동 (운영)

스케줄러가 **자동으로 반복** 실행합니다. 맥미니 상시 가동용.

```
스케줄 (config.yaml에서 조정 가능):
  00:00 / 08:00 / 16:00  ← 수집+분석 (8시간마다 3회)
  03:00                   ← Citation Chase (인용 추적)
  04:00                   ← Backfill (과거 논문 수집)
  08:00                   ← ☀️ Daily Digest → Slack 발송
  월요일 07:00            ← 📋 Weekly Digest → Slack 발송
```

데몬 시작 시 즉시 첫 수집+분석이 실행됩니다.

```bash
python run.py daemon       # 데몬 시작
python run.py reload       # 실행 중인 데몬 재시작 (코드 수정 후)
```

---

## 전체 CLI 명령어

### 파이프라인 단계별 수동 실행

```bash
python run.py collect      # 논문 수집만 (ArXiv + S2)
python run.py process      # PDF 텍스트 추출만
python run.py analyze      # Gemini 분석만
python run.py chase        # Citation Chase (인용 추적) 1회
python run.py backfill     # Backfill (과거 논문 수집) 1회
python run.py inbox        # data/inbox/ PDF 감지·처리
```

### 보고서 수동 생성

```bash
python run.py daily        # 일간 다이제스트 생성 + Slack 발송
python run.py digest       # 주간 다이제스트 생성 + Slack 발송
python run.py survey       # 서베이 리포트 생성 (backfill+chase 논문)
```

### 테스트 및 데이터 관리

```bash
python run.py smoketest    # 전체 파이프라인 테스트 (격리된 임시 DB 사용, 운영 DB 무영향)
python run.py backup       # 현재 DB 백업 (data/backups/{timestamp}/)
python run.py reset        # DB 초기화 (자동 백업 후 삭제, yes/no 확인)
```

> **smoketest vs run 차이**: `smoketest`는 임시 DB를 사용해 운영 데이터를 건드리지 않습니다. Slack 알림에도 `[🧪 TEST]` 표시가 붙습니다.

---

## 수동 PDF 추가

`data/inbox/` 폴더에 PDF를 넣으면 `python run.py inbox` 또는 데몬 자동 감지로 처리됩니다.

---

## 폴더 구조

```
lab-paper-scout/
├── config/
│   └── config.yaml          # 토픽, 스케줄, API 설정
├── data/
│   ├── inbox/               # PDF를 여기에 넣으면 자동 처리
│   ├── processed/           # 텍스트 추출 결과 (JSON)
│   ├── archive/             # 처리된 원본 PDF 보관
│   ├── reports/             # Markdown 보고서 (daily, weekly, survey)
│   ├── backups/             # reset/backup 시 자동 생성
│   └── paper_scout.db       # SQLite DB (수집된 논문 전체)
├── logs/                    # 날짜별 로그 (scout_{hostname}_{date}.log)
└── src/
    ├── collector/           # ArXiv, S2, Backfill, CitationChase, Inbox 수집기
    ├── processor/           # PDF 추출, DocumentStore (SQLite)
    ├── analyzer/            # Gemini 기반 논문 분석
    ├── reporter/            # Markdown 리포트 생성
    └── notifier/            # Slack 알림
```

---

## 설정 상세 (config.yaml)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `collection_interval_hours` | `8` | 수집+분석 반복 간격 (데몬) |
| `chase_hour` | `3` | Citation Chase 실행 시각 |
| `backfill_hour` | `4` | Backfill 실행 시각 |
| `daily_digest_hour` | `8` | 일간 다이제스트 발송 시각 |
| `weekly_digest_day` | `monday` | 주간 다이제스트 요일 |
| `max_papers_per_run` | `20` | 1회 최대 수집 수 |
| `days_lookback` | `7` | 최근 N일 논문만 수집 |
| `throttle_seconds` | `2` | API 호출 간 대기 시간 |
| `citation_chasing.batch_size` | `10` | Chase 1회 처리 논문 수 |
| `backfill.max_papers_per_topic` | `10` | Backfill 토픽당 수집 수 |

---

## M2 Pro 맥미니 launchd 등록

```bash
# tracked plist는 template입니다. 실제 키는 ignored local plist에만 넣습니다.
cp com.ceml.paper-scout.plist com.ceml.paper-scout.local.plist
$EDITOR com.ceml.paper-scout.local.plist
cp com.ceml.paper-scout.local.plist ~/Library/LaunchAgents/com.ceml.paper-scout.plist
launchctl load ~/Library/LaunchAgents/com.ceml.paper-scout.plist

# 상태 확인
launchctl list | grep paper-scout

# 재시작
launchctl stop com.ceml.paper-scout && launchctl start com.ceml.paper-scout
# 또는
python run.py reload
```
