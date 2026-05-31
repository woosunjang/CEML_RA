# 세션 8 결과 — UI/UX 고도화 (2/2) — Debate UI + 채팅 개선 + 반응형

> 완료일: 2026-05-24

## Step 1: Debate UI 전용 컴포넌트 ✅

### `components/DebateView.tsx` (130줄)
- **Debate 모드 토글**: 채팅 입력 바에 🏛️ Debate 버튼 추가
  - 활성화 시 입력 바 색상 변경 + "3모델 토론 모드" 안내
  - `mode: "debate"` 자동 전환
- **라운드별 패널리스트 카드**: analyst(🟢) / critic(🟣) / synthesizer(🔵)
  - 접기/펼치기 (클릭으로 토글)
  - 각 패널리스트별 소요 시간 표시
  - 진행 상태: pending → running → done
- **Debate 결과 표시**: 보라색 좌측 테두리로 일반 채팅과 차별화

## Step 2: 채팅 UI 개선 ✅

### 2-1. 에이전트 표시 개선 ✅
- 메시지 버블에 에이전트 아이콘 + 이름 배지
- `agent_name`별 HSL 색상·이모지 자동 배정
- debate/pipeline 에이전트 전용 스타일

### 2-2. 마크다운 렌더링 강화 ✅ — `components/MarkdownRenderer.tsx` (115줄)
- **코드 블록**: `react-syntax-highlighter` + `oneDark` 테마
  - 언어 감지 + 파일명 헤더
  - 복사 버튼 (hover 시 표시)
- **테이블**: 스타일링된 테이블 렌더링 (overflow-x-auto)
- **수식**: `remark-math` 기반 (LaTeX 파싱)
- **인라인 코드**: 보라색 하이라이트

### 2-3. 모델 프로필 전환 UI ✅
- 우상단 프로필 스위치: 🚀 성능 ⇄ 💰 가성비
- `POST /models/profile` API 호출
- 토스트 알림 (3초 자동 닫힘)

### 2-4. 입력 바 개선 ✅
- Textarea 자동 높이 조절 (max 160px)
- Shift+Enter 줄바꿈, Enter 전송
- Debate 모드 시 플레이스홀더 변경 + 배경색 변경

## Step 3: 반응형 + 접근성 ✅

### 3-1. 반응형 레이아웃 ✅
- **데스크톱 (md+)**: 좌측 사이드바 (220px)
- **모바일 (<md)**: 하단 네비게이션 바 (fixed bottom)
  - 아이콘 + 레이블
  - `backdrop-filter: blur(16px)` 글래스 효과
- 채팅 메시지 폭: 모바일 85% / 데스크톱 78%
- 입력 바 간격 조정

### 3-2. 키보드 접근성 ✅
- Enter: 전송
- Shift+Enter: 줄바꿈

### 3-3. 토스트 알림 ✅
- 중앙 하단 팝업, 3초 자동 닫힘
- `animate-fade-in-scale` 애니메이션

## 빌드 결과

```
Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /dashboard
└ ○ /knowledge

✓ TypeScript type check passed
✓ Compiled successfully in 1610ms
```

## 검증 기준 달성

- [x] Debate 모드 토글 → debate 실행 → 결과 표시 (라운드별 접기/펼치기)
- [x] 마크다운 테이블, 코드 블록 구문 하이라이팅
- [x] 모바일에서 사용 가능한 레이아웃 (하단 네비게이션)
- [x] 모델 프로필 전환 UI → API 호출 → 토스트 반영

## 수정 파일

| 파일 | 변경 |
|------|------|
| `ui/src/components/DebateView.tsx` | [NEW] Debate 라운드 시각화 (130줄) |
| `ui/src/components/MarkdownRenderer.tsx` | [NEW] 코드 하이라이팅 + 테이블 (115줄) |
| `ui/src/components/Sidebar.tsx` | 반응형: 데스크톱 사이드바 + 모바일 하단 바 |
| `ui/src/app/page.tsx` | 전면 재작성: Debate 토글, 프로필 전환, 토스트 (270줄) |
| `ui/src/lib/types.ts` | ChatRequest에 mode, pipeline 필드 추가 |

## 설치 패키지
- `react-syntax-highlighter` + `@types/react-syntax-highlighter`
- `remark-math`
