# 마크다운 파일 기반 명령 시스템

> Slack 불가 시 또는 긴 요청을 보낼 때, 공유 폴더에 `.md` 파일을 넣으면 오케스트레이터가 자동 처리합니다.

## 디렉토리 구조

```
lab-orchestrator/commands/
├── inbox/      ← 여기에 .md 파일을 놓으면 자동 감지 (30초 간격)
├── outbox/     ← 처리 결과가 같은 파일명으로 생성됨
└── archive/    ← 처리 완료된 원본 파일 보관 (타임스탬프 접두사)
```

## 사용 방법

### 방법 1: 자연어 (가장 간단)

`inbox/` 폴더에 `.md` 파일을 만들고 질문만 적으면 됩니다.

```markdown
NASICON 고체전해질의 Al 도핑 효과를 정리해줘
```

→ 자동으로 `ask` 명령으로 처리됩니다.

### 방법 2: Frontmatter로 명령 지정

YAML frontmatter를 사용하면 명령 종류, 에이전트, 모드를 지정할 수 있습니다.

```markdown
---
command: ask
agent: literature
mode: normal
---

NASICON 고체전해질의 Al 도핑 효과를 정리해줘
```

## 지원 명령

| command | 설명 | frontmatter 옵션 |
|---------|------|-------------------|
| `ask` | 일반 질문 (기본값) | `agent`: 에이전트 지정, `mode`: normal/debate |
| `debate` | 3-LLM 토론 모드 | — |
| `search` | 장기 기억 검색 | — |
| `report` | 리포트 생성 | 본문에 `daily` 또는 `weekly` |
| `status` | 시스템 상태 조회 | — |
| `pipeline` | 파이프라인 실행 | 본문 첫 줄: pipeline_id, 이후: 메시지 |

## 예시

### 예시 1: 단순 질문
**파일명**: `inbox/nasicon.md`
```markdown
Li-ion 전지에서 NASICON 구조의 장점은?
```

### 예시 2: 특정 에이전트 지정
**파일명**: `inbox/proposal_draft.md`
```markdown
---
command: ask
agent: writing
---

NASICON 기반 고체전해질 연구 제안서 초안을 작성해줘.
배경, 목적, 방법론, 기대효과 섹션을 포함할 것.
```

### 예시 3: 토론 모드
**파일명**: `inbox/debate_electrolyte.md`
```markdown
---
command: debate
---

황화물계 vs 산화물계 고체전해질, 상용화 관점에서 어느 쪽이 유리한가?
```

### 예시 4: 시스템 상태
**파일명**: `inbox/check.md`
```markdown
---
command: status
---
```

### 예시 5: 데일리 리포트 수동 생성
**파일명**: `inbox/report.md`
```markdown
---
command: report
---

daily
```

### 예시 6: 파이프라인 실행
**파일명**: `inbox/run_pipeline.md`
```markdown
---
command: pipeline
---

literature_to_writing
NASICON 도핑 논문 3편을 분석하고 리뷰 초안을 작성해줘
```

## 결과 확인

- `outbox/` 폴더에 입력 파일과 동일한 이름으로 결과 파일이 생성됩니다.
- 결과 파일 상단에 실행 시각과 명령 종류가 표시됩니다.
- 원본 입력 파일은 `archive/`로 이동되며, 파일명에 타임스탬프가 붙습니다.

## 참고

- 감시 간격: 30초
- 파일 확장자: `.md`만 인식
- 인코딩: UTF-8
- Dropbox 동기화 환경에서 다른 기기에서도 파일을 넣을 수 있습니다.
