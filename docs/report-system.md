# 리포트 시스템 설계

## 리포트 종류

| 리포트 | 채널 | 빈도 | 내용 |
|--------|------|------|------|
| 시스템 주간 | `#lab-report` | 매주 월 09:00 | 에이전트 통계, 추이, 권장사항 |
| 논문 데일리 | `#lab-papers` | 매일 09:00 | 전일 수집 논문, 상위 5편 요약, Proactive Brief |
| 논문 주간 | `#lab-papers` | 매주 월 09:00 | 주간 통계+변화, 비교 테이블, 키워드 트렌드, Proactive Brief |
| 프로젝트 주간 | `#lab-project` | 매주 월 09:00 | 진척률, 마감, 액션 아이템 |

## 데이터 소스

| 소스 | 위치 | 수집 방식 |
|------|------|-----------|
| 에이전트 호출 | `data/usage.db` → `agent_calls` | `graph.py` 자동 계측 |
| 대화 기록 | `data/usage.db` → `conversations` | `graph.py` 자동 계측 |
| 파이프라인 실행 | `data/usage.db` → `pipeline_runs` | `graph.py` 자동 계측 |
| 대화 로그 (전문) | `logs/chat/YYYY-MM-DD.md` | `chat_logger.py` 자동 기록 |
| Scout 수집 이력 | `lab-paper-scout/data/paper_scout.db` | Scout 파이프라인 |
| Scout 분석 결과 | `analysis_json` 컬럼 내부 | Gemini 분석기 |
| 프로젝트 마감일 | `data/projects.json` | 수동 등록 |
| Proactive Brief | `data/knowledge_briefs/*.json`, `generated/reports/brief_*.md` | Scout 근거 기반 자동 생성 |
| 자율 실행 로그 | `data/autonomy_actions.jsonl` | 로컬 자동 변경 기록 |

CloudStorage/Dropbox에 있는 Scout SQLite는 직접 읽기에서 `disk I/O error`가 날 수 있어, Orchestrator는 임시 로컬 스냅샷으로 재시도한다. 요청 기간의 Scout DB가 비어 있지만 같은 기간 brief artifact가 이미 있으면 기존 brief를 재사용한다.

### Scout DB 활용 필드 (리포트용)

| 필드 | 용도 |
|------|------|
| `title`, `authors`, `venue`, `year`, `url` | 기본 메타 |
| `relevance_score` | 주목/기타 분류 (90%+ = 주목) |
| `topics_json` | 토픽 커버리지 분석 |
| `analysis_json.summary_kr` | 한국어 요약 |
| `analysis_json.key_contribution` | 핵심 기여 |
| `analysis_json.methodology` | 방법론 |
| `analysis_json.key_results` | 핵심 결과 |
| `analysis_json.tags` | 키워드 |

---

## 논문 데일리 리포트

> 매일 09:00 KST → `#lab-papers`

### 구성

1. **수집 통계**: 편수 + 주목/기타 분류
2. **주목 논문 (90%+)**: 상세 (저자, 저널, 방법론, 결과, 기여, URL)
3. **기타 논문**: compact (관련도, 제목, 저자, 저널)
4. **키워드 태그**: 상위 6개
5. **Proactive Brief**: 새 근거, 논문 간 연결, 모델 추론/가설, 후속 업무 제안

---

## 논문 주간 리포트

> 매주 월요일 09:00 KST → `#lab-papers`

### 구성

1. **수집 통계 (전주 대비)**: 편수 변화, 평균 관련도 변화, 주목 논문 수
2. **토픽 커버리지**: topics_json 기반, ✅/⚠️/❌ + "가장 활발"/"관심 필요" 레이블
3. **주목 논문 상세**: 방법론/결과/기여/URL
4. **비교 테이블**: 주목 논문 방법론·결과 비교 (코드 블록)
5. **키워드 트렌드**: 빈도 + 🆕신규 + 📈상승
6. **기타 논문 목록**: 상위 10편 compact + 나머지 `generated/reports/digest_*.md` 참조
7. **Proactive Brief**: 근거와 추론을 분리한 연구 기회 및 다음 업무 제안

### 데일리 대비 차별화

| 항목 | 데일리 | 주간 |
|------|--------|------|
| 전주 대비 통계 | ✗ | ✅ |
| 토픽 커버리지 | ✗ | ✅ |
| 비교 테이블 | ✗ | ✅ |
| 키워드 변화 | ✗ | ✅ (신규/상승) |
| 전체 목록 | 기타 5편 | 10편 + 파일 참조 |

---

## 리포트 산출물 저장

Scout 다이제스트 리포트 파일 → `CEML_RA/generated/reports/`

```
generated/reports/
├── daily_20260520.md
├── daily_20260521.md
├── brief_20260531.md
├── digest_20260525.md
└── survey_20260518.md
```

## Proactive Brief 정책

- 관련도 70점 이상 논문을 brief 근거로 사용한다.
- 관련도 90점 이상 논문은 Graphiti archival queue 승격 후보로 자동 기록한다.
- 모든 brief는 **새 근거**와 **모델 추론/가설**을 분리한다.
- 자동 생성 및 queue 승격은 `data/autonomy_actions.jsonl`에 기록한다.
