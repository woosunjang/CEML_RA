# 세션 7 — UI/UX 고도화 (1/2) — 대시보드 + 지식그래프

## 참조 문서
- 현재 UI: [page.tsx](file:///Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/ui/src/app/page.tsx)
- API 클라이언트: [api.ts](file:///Users/woosun/Dropbox/Dev/CEML_RA/lab-orchestrator/ui/src/lib/api.ts)

---

## 배경

현재 UI는 기본 채팅 인터페이스만 구현되어 있습니다.
이 세션에서는 프리미엄 대시보드와 지식그래프 시각화를 구축합니다.

---

## Step 1: UI 디자인 시스템 재정비 (1.5h)

### 1-1. 글로벌 스타일 개선
- `globals.css` 전면 리팩토링
- 다크 모드 기본, 색상 팔레트 정의 (HSL 기반)
- 타이포그래피: Inter (영문) + Noto Sans KR (한글)
- 글래스모피즘 카드 컴포넌트
- 마이크로 애니메이션 (hover, transition)

### 1-2. 공통 컴포넌트
- `components/Card.tsx` — 글래스모피즘 카드
- `components/Badge.tsx` — 에이전트 아이콘 뱃지
- `components/Sidebar.tsx` — 좌측 네비게이션
- `components/LoadingSpinner.tsx` — 로딩 상태

---

## Step 2: 워크스페이스 대시보드 (2.5h)

### 2-1. 대시보드 레이아웃
```
┌──────────┬──────────────────────────┐
│ Sidebar  │ ┌────────────────────┐   │
│          │ │ 프로젝트 현황 카드  │   │
│ 대시보드  │ ├────────────────────┤   │
│ 채팅     │ │ 최근 활동 타임라인  │   │
│ 지식그래프│ ├────────────────────┤   │
│ 설정     │ │ 에이전트 상태       │   │
│          │ └────────────────────┘   │
└──────────┴──────────────────────────┘
```

### 2-2. 프로젝트 현황 카드
- API: `GET /agents` + `GET /memory/search` + `GET /debate/status`
- 총 대화 수, 장기 기억 팩트 수, 에이전트별 호출 횟수
- 모델 프로필 현재 상태 (성능/가성비)
- 마지막 활동 시각

### 2-3. 에이전트 상태 그리드
- 각 에이전트를 카드로 표시 (아이콘, 이름, 모델, 상태)
- 클릭 시 해당 에이전트에 직접 질문 가능
- 실시간 상태 (available / busy / error)

### 2-4. 최근 활동 타임라인
- 최근 대화 목록 (conversation_id, 첫 메시지, 사용 에이전트, 시각)
- API: `GET /conversations` 엔드포인트 추가 필요

---

## Step 3: 지식그래프 시각화 (3h)

### 3-1. 시각화 라이브러리 설치
- `react-force-graph-2d` 또는 `d3-force` — 엔티티-관계 네트워크
- `npm install react-force-graph-2d`

### 3-2. 백엔드 API 추가
- `GET /memory/graph` — 엔티티 + 관계를 노드-엣지 포맷으로 반환
  ```json
  {
    "nodes": [{"id": "NASICON", "type": "material", "summary": "..."}],
    "edges": [{"source": "NASICON", "target": "Al doping", "relation": "도핑조건", "fact": "..."}]
  }
  ```
- `orchestrator/archival.py`에 `get_graph_data()` 메서드 추가
- FalkorDB Cypher 쿼리로 노드/엣지 추출

### 3-3. 프론트엔드 구현
- `app/knowledge/page.tsx` — 지식그래프 페이지
- 인터랙티브 네트워크 그래프
  - 노드: 엔티티 (크기 = 연결 수)
  - 엣지: 관계 (hover 시 fact 표시)
  - 색상: 엔티티 타입별 구분
- 검색 바: 노드 필터링
- 노드 클릭 시: 해당 엔티티 관련 팩트 목록 사이드패널

---

## 검증 기준

- [ ] 대시보드에서 에이전트 상태, 프로젝트 현황, 최근 활동 확인
- [ ] 지식그래프에서 엔티티-관계 네트워크 시각화
- [ ] 노드 클릭 시 관련 팩트 표시
- [ ] 다크 모드 기본, 글래스모피즘 카드 적용
- [ ] 모바일 반응형 기본 대응
