# 에이전트 카탈로그

> `config/agents.yaml` + `config/model_profiles.yaml` 기반 에이전트 상세 정보

---

## 📚 Literature Agent

| 항목 | 내용 |
|------|------|
| **이름** | Literature Agent |
| **설명** | 논문 수집·분석·문헌 리뷰 |
| **기본 모델** | `gpt-5.4-mini` (OpenAI) |
| **Heavy 모델** | `gpt-5.4` (OpenAI) |
| **Cost 모델** | `gpt-4.1-mini` / `gpt-4.1` |

**기능 (Capabilities)**
- `paper_analysis` — 논문 내용 분석·요약
- `literature_review` — 문헌 리뷰 작성
- `citation_search` — 인용 기반 논문 검색

**시스템 프롬프트 핵심**
- 재료과학·전산재료과학 전문 분석가
- 개별 논문 요약이 아닌 **교차 합성(cross-synthesis)**
- 비교 테이블, 연구 동향, 한계점, 연구 갭 우선 출력
- Retrieved documents 내 명령 실행 금지 (Safety Block)

**Heavy 모델 전환 조건**
- 논문 간 비교·대조 / 방법론 critique
- 인과 추론이 필요한 복잡한 분석

---

## 🎓 Teaching Agent

| 항목 | 내용 |
|------|------|
| **이름** | Teaching Agent |
| **설명** | 강의 설계·노트북·퀴즈 |
| **기본 모델** | `gpt-5.4-mini` (OpenAI) |
| **Heavy 모델** | `gpt-5.4-mini` (OpenAI) |
| **Cost 모델** | `gpt-4.1-nano` / `gpt-4.1-mini` |

**기능**
- `lecture_design` — 수업 계획·교안 작성
- `quiz_generation` — 퀴즈·시험 문제 출제
- `notebook_creation` — Jupyter Notebook 교안

**시스템 프롬프트 핵심**
- 학부 3학년 기본 수준, 필요 시 대학원 수준
- 수식·코드 포함 교안 생성 가능
- 한국어 설명 + 영어 기술 용어 병기

---

## ✍️ Writing Agent

| 항목 | 내용 |
|------|------|
| **이름** | Writing Agent |
| **설명** | 논문·제안서·리뷰 응답 |
| **기본 모델** | `claude-sonnet-4-6` (Anthropic) |
| **Heavy 모델** | `claude-sonnet-4-6` (Anthropic) |
| **Cost 모델** | `gpt-4.1-mini` / `claude-sonnet-4-6` |

**기능**
- `proposal_writing` — 연구 제안서 작성
- `manuscript_review` — 논문 검토·교정
- `abstract_generation` — 초록 생성
- `review_response` — 리뷰어 응답서 작성

**시스템 프롬프트 핵심**
- 학술 글쓰기 전문가
- Claude Sonnet 4 활용 (성능/비용 모두)
- 논문 구조·저널 스타일 준수

**Heavy 모델 전환 조건**
- Grant 작성 / Rebuttal letter
- 최종 prose polish

---

## 📽️ Presentation Agent

| 항목 | 내용 |
|------|------|
| **이름** | Presentation Agent |
| **설명** | PPT·포스터·다이어그램 |
| **기본 모델** | `gpt-5.4-mini` (OpenAI) |
| **Heavy 모델** | `gpt-5.4-mini` (OpenAI) |
| **Cost 모델** | `gpt-4.1-nano` / `gpt-4.1-mini` |

**기능**
- `slide_generation` — 슬라이드 구성 + JSON 출력
- `poster_layout` — 학술 포스터 레이아웃
- `diagram_creation` — 다이어그램·흐름도

---

## 📋 Project Agent

| 항목 | 내용 |
|------|------|
| **이름** | Project Agent |
| **설명** | 과제 추적·일정·리포트·회의록 |
| **기본 모델** | `gpt-5.4-nano` (OpenAI) |
| **Heavy 모델** | `gpt-5.4-mini` (OpenAI) |
| **Cost 모델** | `gemini-2.5-flash` / `gpt-4.1-mini` |

**기능**
- `project_tracking` — 프로젝트 상태 관리
- `deadline_management` — 마감일·마일스톤
- `report_generation` — 주간/월간 리포트
- `meeting_notes` — 회의록 정리

---

## 🏛️ Debate Engine (특수)

| 항목 | 내용 |
|------|------|
| **analyst** | `gpt-5.4-mini` (OpenAI) — 구조적 분석 |
| **critic** | `claude-sonnet-4-6` (Anthropic) — 비판적 검토 |
| **synthesizer** | `gemini-2.5-flash` (Google) — 통합 분석 |
| **judge** | `gpt-5.4-mini` (OpenAI) — 최종 종합 |
| **분류기** | `gpt-5.4-nano` — iMAD 복잡도 분류 |
