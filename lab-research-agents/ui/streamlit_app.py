"""
Lab Research Agents — Streamlit UI

Main application interface with document upload, metadata tagging,
agent mode selection, and chat with citations.
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so `app.*` imports work
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Lab Research Agents",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Imports (after sys.path setup)
# ---------------------------------------------------------------------------
from app.schemas import AgentMode, DocumentType
from app.ingestion.ingest import ingest_document
from app.agents.runner import run_agent
from app.config import DATA_RAW_DIR
from app.retrieval.keyword_store import bm25_store

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_OPTIONS = [
    "all",
    "general",
    "solid_electrolyte",
    "rare_earth",
    "materials_ontology",
    "hydrogen",
    "sisso",
    "dft",
]

DOCUMENT_TYPE_OPTIONS = ["all"] + [dt.value for dt in DocumentType]
AGENT_MODE_OPTIONS = [am.value for am in AgentMode]

AGENT_MODE_LABELS = {
    "literature": "📚 Literature — 문헌 분석",
    "proposal": "📝 Proposal — 제안서 작성",
    "manuscript": "🔍 Manuscript — 원고 리뷰",
    "lecture": "🎓 Lecture — 강의 설계",
    "scout": "🔭 Scout — 논문 동향 분석",
}

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Initialize BM25 index from Qdrant on first load
if "bm25_initialized" not in st.session_state:
    bm25_store.reload_from_qdrant()
    st.session_state.bm25_initialized = True

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #e0e0e0;
    }

    /* Citation expander */
    .stExpander {
        border: 1px solid #334155;
        border-radius: 8px;
    }

    /* Agent mode badge */
    .agent-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 0.85em;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .agent-badge.literature { background: #1e3a5f; color: #93c5fd; }
    .agent-badge.proposal   { background: #1e3a2e; color: #86efac; }
    .agent-badge.manuscript  { background: #3b1f2b; color: #fda4af; }
    .agent-badge.lecture     { background: #3b2f1f; color: #fcd34d; }
    .agent-badge.scout       { background: #1f2937; color: #67e8f9; }

    /* Ingest success */
    .ingest-success {
        background: #064e3b;
        border: 1px solid #10b981;
        border-radius: 8px;
        padding: 12px 16px;
        color: #d1fae5;
        margin-top: 8px;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================================
# SIDEBAR
# =========================================================================
with st.sidebar:
    st.markdown("# 🔬 Lab Research Agents")
    st.markdown("---")

    # ----- Agent Mode -----
    st.markdown("### 🤖 Agent Mode")
    agent_mode = st.selectbox(
        "에이전트 선택",
        options=AGENT_MODE_OPTIONS,
        format_func=lambda x: AGENT_MODE_LABELS.get(x, x),
        key="agent_mode_select",
        label_visibility="collapsed",
    )

    # ----- Filters (hidden for Scout mode — auto-filters to paper-scout) -----
    if agent_mode != "scout":
        st.markdown("### 🔎 Filters")
        col_proj, col_type = st.columns(2)
        with col_proj:
            project_filter = st.selectbox(
                "Project",
                options=PROJECT_OPTIONS,
                index=0,
                key="project_filter",
            )
        with col_type:
            doc_type_filter = st.selectbox(
                "Doc Type",
                options=DOCUMENT_TYPE_OPTIONS,
                index=0,
                key="doc_type_filter",
            )
    else:
        st.markdown("### 🔎 Filters")
        st.caption("Scout 모드: 자동 수집 논문만 검색합니다.")
        project_filter = "paper-scout"
        doc_type_filter = "paper"

    st.markdown("---")

    # ----- Document Upload -----
    st.markdown("### 📄 Document Upload")
    uploaded_file = st.file_uploader(
        "파일 선택",
        type=["pdf", "docx", "pptx", "txt", "md"],
        key="file_uploader",
        label_visibility="collapsed",
    )

    if uploaded_file:
        st.markdown("#### Metadata")
        meta_title = st.text_input(
            "Title",
            value=Path(uploaded_file.name).stem,
            key="meta_title",
        )
        meta_doc_type = st.selectbox(
            "Document Type",
            options=[dt.value for dt in DocumentType],
            index=0,
            key="meta_doc_type",
        )
        meta_project = st.selectbox(
            "Project",
            options=PROJECT_OPTIONS[1:],  # exclude "all"
            index=0,
            key="meta_project",
        )
        meta_year = st.number_input(
            "Year (optional)",
            min_value=1900,
            max_value=2100,
            value=2025,
            step=1,
            key="meta_year",
        )

        if st.button("📥 Ingest Document", key="ingest_btn", use_container_width=True):
            with st.spinner("파싱 및 인제스트 중..."):
                try:
                    # Sanitize filename
                    safe_name = "".join(
                        c if c.isalnum() or c in "._- " else "_"
                        for c in uploaded_file.name
                    )
                    save_path = DATA_RAW_DIR / safe_name
                    save_path.write_bytes(uploaded_file.getvalue())

                    result = ingest_document(
                        file_path=str(save_path),
                        title=meta_title,
                        document_type=meta_doc_type,
                        project=meta_project,
                        year=int(meta_year),
                    )

                    st.markdown(
                        f'<div class="ingest-success">'
                        f'✅ 인제스트 완료<br/>'
                        f'<b>Document ID:</b> {result["document_id"][:8]}...<br/>'
                        f'<b>Chunks:</b> {result["num_chunks"]}개'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                except Exception as e:
                    st.error(f"인제스트 실패: {e}")

    st.markdown("---")

    # ----- Scout Integration -----
    from app.integrations.scout_reader import ScoutReader
    scout = ScoutReader()

    if scout.available:
        st.markdown("### 📬 Paper Scout")
        try:
            stats = scout.get_stats()
            col1, col2 = st.columns(2)
            col1.metric("총 논문", f"{stats['total']}편")
            col2.metric("오늘 수집", f"{stats['today']}편")

            # Top papers expander
            with st.expander(f"🏆 고관련도 논문 (상위 10편)", expanded=False):
                top_papers = scout.get_top_papers(min_score=70, limit=10)
                if top_papers:
                    for p in top_papers:
                        score = p.get("relevance_score", 0)
                        title = p.get("title", "?")
                        summary = p.get("summary", "")
                        url = p.get("url", "")

                        score_color = "#10b981" if score >= 85 else "#f59e0b" if score >= 70 else "#94a3b8"
                        st.markdown(
                            f'<span style="color:{score_color};font-weight:bold;">'
                            f'{score:.0f}</span> '
                            f'{"["+title+"]("+url+")" if url else title}',
                            unsafe_allow_html=True,
                        )
                        if summary:
                            st.caption(summary)
                else:
                    st.caption("관련도 70+ 논문이 없습니다.")

            # Search in scout DB
            scout_query = st.text_input(
                "🔍 Scout DB 검색",
                key="scout_search",
                placeholder="제목/초록 검색...",
            )
            if scout_query:
                results = scout.search_papers(scout_query, limit=10)
                if results:
                    for p in results:
                        score = p.get("relevance_score", 0)
                        title = p.get("title", "?")
                        url = p.get("url", "")
                        st.markdown(
                            f'**{score:.0f}** — '
                            f'{"["+title+"]("+url+")" if url else title}',
                        )
                else:
                    st.caption("검색 결과 없음")

            scout.close()
        except Exception as e:
            st.caption(f"Scout DB 읽기 오류: {e}")
    else:
        st.markdown("### 📬 Paper Scout")
        st.caption("Scout DB를 찾을 수 없습니다.")

    st.markdown("---")
    st.markdown(
        f"<small style='color: #94a3b8;'>"
        f"Agent: {agent_mode} | Project: {project_filter} | Type: {doc_type_filter}"
        f"</small>",
        unsafe_allow_html=True,
    )


# =========================================================================
# MAIN AREA
# =========================================================================

# Header
badge_class = agent_mode
st.markdown(
    f'<span class="agent-badge {badge_class}">'
    f'{AGENT_MODE_LABELS.get(agent_mode, agent_mode)}</span>',
    unsafe_allow_html=True,
)
st.markdown("---")

# ----- Chat History -----
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        # Show citations in expander for assistant messages
        if msg["role"] == "assistant" and msg.get("citations"):
            with st.expander("📎 참고한 내부 문서 (인용 상세)"):
                st.text(msg["citations"])

# ----- Chat Input -----
user_input = st.chat_input("질문을 입력하세요...")

if user_input:
    # Display user message
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_input,
    })
    with st.chat_message("user"):
        st.markdown(user_input)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("검색 및 응답 생성 중..."):
            try:
                result = run_agent(
                    agent_mode=agent_mode,
                    question=user_input,
                    project=project_filter,
                    document_type=doc_type_filter,
                    top_k=8,
                )

                answer = result["answer"]
                citations = result["citations"]

                st.markdown(answer)

                if citations:
                    with st.expander("📎 참고한 내부 문서 (인용 상세)"):
                        st.text(citations)

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": answer,
                    "citations": citations,
                })

            except Exception as e:
                error_msg = f"응답 생성 중 오류가 발생했습니다: {e}"
                st.error(error_msg)
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": error_msg,
                    "citations": "",
                })
