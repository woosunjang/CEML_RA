# Lab Research Agents

연구실용 RAG 기반 연구 어시스턴트 — 문서 기반 질의응답 시스템

## Overview

연구 문서(논문, 제안서, 원고, 강의자료)를 업로드하고, 4가지 에이전트 모드를 통해 문서 기반의 근거 있는 답변을 생성합니다.

### Agent Modes

| Mode | Role | 주요 기능 |
|------|------|----------|
| **Literature** | 과학 문헌 분석가 | 문헌 비교, 연구 gap 분석, 재사용 가능 문단 |
| **Proposal** | R&D 제안서 작성 보조 | 문제→병목→방법→차별성→기대성과 |
| **Manuscript** | 비판적 리뷰어 | Claim-evidence 정합성, reviewer concern 예측 |
| **Lecture** | 강의 설계 보조 | 슬라이드 구조, 학습 목표, speaker note |

## Installation

### 1. Conda 환경 설정 (권장)

```bash
# 환경 생성 (Python 3.12 + 모든 의존성 설치)
conda env create -f environment.yml

# 환경 활성화
conda activate lab-research-agents
```

<details>
<summary>대안: venv 사용</summary>

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
</details>

### 2. Environment Variables

```bash
cp .env.example .env
# .env 파일을 열고 API 키 입력
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `OPENAI_CHAT_MODEL` | ✅ | Chat model (default: `gpt-4o`) |
| `OPENAI_EMBEDDING_MODEL` | ✅ | Embedding model (default: `text-embedding-3-small`) |
| `QDRANT_URL` | ✅ | Qdrant URL (default: `http://localhost:6333`) |
| `QDRANT_COLLECTION` | ✅ | Collection name (default: `lab_research_chunks`) |
| `ANTHROPIC_API_KEY` | ❌ | Optional Claude API key |

### 3. Start Qdrant

```bash
docker compose up -d
```

### 4. Run the App

```bash
streamlit run ui/streamlit_app.py
```

## Usage

### Uploading Documents

1. 사이드바에서 파일 업로드 (PDF, DOCX, PPTX, TXT, MD)
2. 메타데이터 입력: 제목, 문서 유형, 프로젝트, 연도
3. **Ingest** 버튼 클릭
4. 인제스트된 청크 수 확인

### Asking Questions

1. 에이전트 모드 선택
2. 프로젝트 / 문서 유형 필터 설정
3. 채팅창에 질문 입력
4. 응답 + 인용 정보 확인

## Test Questions

### Literature Agent
- `이 문서들을 바탕으로 이 주제의 연구 gap을 정리해줘.`
- `LLZO 관련 문헌들을 방법론, 물성, 한계, 제안서에 활용 가능한 논리로 비교해줘.`

### Proposal Agent
- `기존 제안서 문체를 참고해서 연구개발 필요성을 0.5페이지 분량으로 써줘.`
- `AI 기반 소재 탐색 연구내용을 문제 정의, 병목, 방법론, 기대성과 중심으로 정리해줘.`

### Manuscript Agent
- `이 manuscript의 novelty claim과 evidence alignment를 비판적으로 검토해줘.`
- `Reviewer가 지적할 가능성이 높은 major concern을 찾아줘.`

### Lecture Agent
- `이 내용을 대학원 강의 10장 슬라이드 outline으로 바꿔줘.`
- `SISSO와 symbolic regression을 대학원생 대상 90분 강의로 구성해줘.`

## Known Limitations (v0.1)

- 단순 문자 기반 청킹 (섹션/문단 인식 없음)
- 키워드 검색 미지원 (벡터 검색만)
- 테이블/캡션 추출 미지원
- 파일 중복 감지 없음
- Anthropic/Claude 연동 미구현

## Roadmap

- **v0.2**: Hybrid retrieval (BM25 + vector), 섹션 인식 청킹, 파일 해시 중복 방지
- **v0.3**: 연구실 메모리, 제안서/리뷰응답 스타일 템플릿
- **v0.4**: Controlled vocabulary, synonym expansion, 경량 materials ontology
- **v0.5+**: Claim-evidence graph, RDF/OWL, VASP/DFT parser, PPTX 생성
