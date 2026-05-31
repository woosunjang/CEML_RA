"""
Lab Orchestrator — Report Generator

리포트 종류:
  1. generate_weekly_report  — 시스템 주간 리포트 (#lab-report)
  2. generate_papers_daily   — 논문 데일리 리포트 (#lab-papers)
  3. generate_papers_weekly  — 논문 주간 리포트 (#lab-papers)
  4. generate_daily_report   — (레거시) 수동 호출용 (/report daily)
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from collections import Counter
import re

logger = logging.getLogger("report_generator")


async def generate_daily_report(date: Optional[str] = None) -> str:
    """(레거시) 수동 호출용 데일리 리포트. /report daily 커맨드."""
    from integrations.usage_tracker import tracker

    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    stats = await tracker.get_daily_stats(date)

    lines = [
        f"📋 *데일리 리포트 — {stats['date']}*\n",
        "─" * 30,
    ]

    agent_stats = stats.get("agent_stats", {})
    if agent_stats:
        lines.append("\n*🤖 에이전트 호출 통계*")
        total_calls = sum(a["total"] for a in agent_stats.values())
        total_success = sum(a.get("completed", 0) for a in agent_stats.values())
        success_rate = (total_success / total_calls * 100) if total_calls else 0
        lines.append(f"총 호출: *{total_calls}회* · 성공률: *{success_rate:.0f}%*\n")

        for name, s in sorted(agent_stats.items(), key=lambda x: x[1]["total"], reverse=True):
            bar_len = min(s["total"], 20)
            bar = "█" * bar_len
            failed = s.get("failed", 0)
            status_icon = "✅" if failed == 0 else f"❌{failed}"
            avg_info = f"  ⏱️{s['avg_sec']}s" if s.get("avg_sec") else ""
            lines.append(
                f"  {_agent_icon(name)} `{name:14s}` {bar} {s['total']}회 ({status_icon}){avg_info}"
            )
    else:
        lines.append("\n_에이전트 호출 기록 없음_")

    conv_count = stats.get("conversation_count", 0)
    lines.append(f"\n*💬 대화 세션*: {conv_count}개")

    questions = stats.get("recent_questions", [])
    if questions:
        lines.append("\n*❓ 주요 질문 (최근 5개)*")
        for q in questions:
            msg = q.get("message", "")[:80]
            agent = q.get("agent_name", "")
            mode_icon = "🏛️" if q.get("mode") == "debate" else ""
            lines.append(f"  • {mode_icon}`{agent}` {msg}")

    pipes = stats.get("pipeline_stats", [])
    if pipes:
        lines.append("\n*🔗 파이프라인 실행*")
        for p in pipes:
            lines.append(f"  • `{p['pipeline_id']}`: {p['cnt']}회 ({p['status']})")

    lines.append(f"\n_생성: {datetime.now().strftime('%Y-%m-%d %H:%M KST')}_")
    return "\n".join(lines)


async def generate_weekly_report(end_date: Optional[str] = None) -> str:
    """시스템 주간 리포트 (#lab-report). 매주 월 09:00 자동 전송."""
    from integrations.usage_tracker import tracker

    stats = await tracker.get_weekly_stats(end_date)

    lines = [
        "📊 *주간 시스템 리포트*",
        f"_{stats['period']}_\n",
        "═" * 30,
    ]

    # ── 일별 활동 추이 ──
    daily_trend = stats.get("daily_trend", [])
    if daily_trend:
        lines.append("\n*📈 일별 활동 추이*")
        max_calls = max((d["calls"] for d in daily_trend), default=1)
        for d in daily_trend:
            day_short = d["day"][5:]
            bar_len = int(d["calls"] / max(max_calls, 1) * 15)
            bar = "▓" * bar_len + "░" * (15 - bar_len)
            rate = (d["success"] / d["calls"] * 100) if d["calls"] else 0
            lines.append(f"  `{day_short}` {bar} {d['calls']}회 ({rate:.0f}%)")
    else:
        lines.append("\n_이번 주 활동 기록 없음_")

    # ── 에이전트 사용 순위 ──
    agent_rank = stats.get("agent_ranking", [])
    if agent_rank:
        lines.append("\n*🏆 에이전트 사용 순위*")
        medals = ["🥇", "🥈", "🥉"]
        for i, a in enumerate(agent_rank[:5]):
            medal = medals[i] if i < 3 else f" {i+1}."
            avg = f"⏱️{a['avg_sec']:.1f}s" if a.get("avg_sec") else ""
            lines.append(f"  {medal} {_agent_icon(a['agent_name'])} *{a['agent_name']}* — {a['cnt']}회 {avg}")

    # ── 대화 모드 분포 ──
    mode_dist = stats.get("mode_distribution", [])
    if mode_dist:
        lines.append("\n*🎯 대화 모드 분포*")
        for m in mode_dist:
            mode_name = {"normal": "일반", "debate": "토론", "pipeline": "파이프라인"}.get(
                m["mode"], m["mode"]
            )
            lines.append(f"  • {mode_name}: {m['cnt']}회")

    total_conv = stats.get("total_conversations", 0)
    lines.append(f"\n*💬 총 대화 세션*: {total_conv}개")

    # ── 파이프라인 실행 이력 ──
    pipe_summary = stats.get("pipeline_summary", [])
    if pipe_summary:
        lines.append("\n*🔗 파이프라인 실행 이력*")
        for p in pipe_summary:
            rate = (p["success"] / p["runs"] * 100) if p["runs"] else 0
            avg = f"평균 {p['avg_sec']:.1f}s" if p.get("avg_sec") else ""
            lines.append(f"  • `{p['pipeline_id']}`: {p['runs']}회 (성공률 {rate:.0f}%) {avg}")

    # ── 권장 사항 ──
    lines.append("\n*💡 권장 사항*")
    if not agent_rank:
        lines.append("  • 이번 주 활동이 없습니다. 오케스트레이터를 활용해보세요!")
    else:
        least_used = agent_rank[-1]["agent_name"] if len(agent_rank) > 2 else None
        if least_used:
            lines.append(f"  • {_agent_icon(least_used)} `{least_used}` 에이전트 활용도가 낮습니다")
        if mode_dist and not any(m["mode"] == "debate" for m in mode_dist):
            lines.append("  • 🏛️ Debate 모드를 아직 사용하지 않았습니다 — 복잡한 연구 질문에 활용해보세요")

    # ── LLM 비용 요약 ──
    try:
        llm_cost = await tracker.get_weekly_llm_cost(end_date)
        if llm_cost.get("models"):
            lines.append("\n*💰 LLM 비용 요약*")
            lines.append(f"  총 비용: *${llm_cost['total_cost']:.4f}*")
            lines.append(f"  총 토큰: {llm_cost['total_tokens']:,}")
            for m in llm_cost["models"][:5]:
                lines.append(
                    f"  • `{m['model']}` — {m['call_count']}회, "
                    f"{m['total_tokens']:,} tokens, ${m['total_cost']:.4f}"
                )
    except Exception:
        pass  # llm_usage table may not exist yet

    lines.append(f"\n_생성: {datetime.now().strftime('%Y-%m-%d %H:%M KST')}_")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
# 논문 리포트 (#lab-papers)
# ────────────────────────────────────────────────────────────────

async def generate_papers_daily(date: Optional[str] = None) -> str:
    """논문 데일리 리포트 (#lab-papers). 매일 09:00 자동 전송."""
    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    lines = [
        f"📚 *논문 데일리 — {date}*\n",
        "─" * 30,
    ]

    try:
        papers = await _fetch_scout_papers(date, date)
        if papers:
            # Classify by relevance
            spotlight = [p for p in papers if p["relevance_score"] >= 0.90]
            others = [p for p in papers if p["relevance_score"] < 0.90]

            lines.append(
                f"\n전일 수집: *{len(papers)}편* "
                f"(주목 {len(spotlight)} · 기타 {len(others)})\n"
            )

            # Spotlight papers (detailed)
            if spotlight:
                lines.append("*⭐ 주목 논문*\n")
                for i, p in enumerate(spotlight[:5], 1):
                    _append_paper_detail(lines, i, p)

            # Other papers (compact)
            top_others = others[:max(0, 5 - len(spotlight))]
            if top_others:
                lines.append("\n*📋 기타 수집 논문*")
                for p in top_others:
                    score_pct = f"{p['relevance_score']:.0%}"
                    authors = f" — {p['authors']}" if p["authors"] else ""
                    venue = f", {p['venue']}" if p["venue"] else ""
                    lines.append(f"  • [{score_pct}] {p['title']}{authors}{venue}")

            # Keywords
            all_kw = []
            for p in papers:
                all_kw.extend(p.get("keywords", []))
            if all_kw:
                top_kw = Counter(all_kw).most_common(6)
                kw_str = " · ".join(f"`{k}`" for k, _ in top_kw)
                lines.append(f"\n🏷️ 키워드: {kw_str}")
        else:
            lines.append("\n_전일 수집 논문 없음_")
    except Exception as e:
        lines.append("\n_Scout DB 미연동 (연동 후 자동 표시)_")
        logger.debug(f"Scout query failed: {e}")

    try:
        from integrations.knowledge_brief import generate_knowledge_brief
        brief = generate_knowledge_brief(date=date, days=1, promote=True)
        _append_brief_summary(lines, brief)
    except Exception as e:
        logger.debug(f"Knowledge brief generation failed: {e}")

    lines.append(f"\n_생성: {datetime.now().strftime('%Y-%m-%d %H:%M KST')}_")
    return "\n".join(lines)


async def generate_papers_weekly(end_date: Optional[str] = None) -> str:
    """논문 주간 리포트 (#lab-papers). 매주 월 09:00 자동 전송."""
    if not end_date:
        end_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")

    # Previous week for comparison
    prev_end = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_start = (datetime.strptime(prev_end, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")

    lines = [
        "📊 *논문 주간 리포트*",
        f"_{start_date} ~ {end_date}_\n",
        "═" * 30,
    ]

    try:
        papers = await _fetch_scout_papers(start_date, end_date)
        try:
            prev_papers = await _fetch_scout_papers(prev_start, prev_end)
        except Exception:
            prev_papers = []

        if papers:
            # ── 수집 통계 (전주 대비) ──
            sources = Counter(p.get("source", "unknown") for p in papers)
            avg_score = sum(p["relevance_score"] for p in papers) / len(papers)
            spotlight = [p for p in papers if p["relevance_score"] >= 0.90]

            diff_str = ""
            avg_diff_str = ""
            if prev_papers:
                diff = len(papers) - len(prev_papers)
                arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                diff_str = f" (전주 대비 {'+' if diff >= 0 else ''}{diff}편 {arrow})"
                prev_avg = sum(p["relevance_score"] for p in prev_papers) / len(prev_papers)
                avg_diff = avg_score - prev_avg
                avg_diff_str = f" (전주 {prev_avg:.0%} → {'+' if avg_diff >= 0 else ''}{avg_diff*100:.0f}%p)"

            lines.append("\n*📈 수집 통계*")
            lines.append(f"  총 수집: *{len(papers)}편*{diff_str}")
            source_str = " · ".join(f"{s}({c})" for s, c in sources.most_common())
            lines.append(f"  소스: {source_str}")
            lines.append(f"  평균 관련도: {avg_score:.0%}{avg_diff_str}")
            lines.append(f"  주목 논문(90%+): {len(spotlight)}편")

            # ── 토픽 커버리지 ──
            all_topics = []
            for p in papers:
                all_topics.extend(p.get("topics", []))
            if all_topics:
                topic_counts = Counter(all_topics)
                top_cnt = topic_counts.most_common(1)[0][1] if topic_counts else 0
                lines.append("\n*📋 관심 분야 커버리지*")
                for topic, cnt in topic_counts.most_common():
                    icon = "✅" if cnt >= 5 else "⚠️" if cnt >= 2 else "❌"
                    label = "  ← 가장 활발" if cnt == top_cnt else ("  ← 관심 필요" if cnt <= 2 else "")
                    lines.append(f"  {icon} {topic} ({cnt}편){label}")

            # ── 주목 논문 (상세) ──
            if spotlight:
                lines.append(f"\n*⭐ 주목 논문 ({len(spotlight)}편)*\n")
                for i, p in enumerate(spotlight[:5], 1):
                    _append_paper_detail(lines, i, p)

            # ── 비교 테이블 ──
            table_papers = spotlight[:5] if spotlight else papers[:5]
            if len(table_papers) >= 2:
                lines.append("*📊 주요 논문 비교*")
                lines.append("```")
                lines.append(f"{'논문':<25} {'방법론':<15} {'핵심 결과':<18} {'관련도':>5}")
                lines.append("─" * 65)
                for p in table_papers:
                    t = p["title"][:22] + "..." if len(p["title"]) > 25 else p["title"]
                    m = (p.get("methodology", "") or "")[:13]
                    r = (p.get("key_results", "") or "")[:16]
                    s = f"{p['relevance_score']:.0%}"
                    lines.append(f"{t:<25} {m:<15} {r:<18} {s:>5}")
                lines.append("```")

            # ── 키워드 트렌드 (변화 감지) ──
            all_kw = []
            for p in papers:
                all_kw.extend(p.get("keywords", []))
            if all_kw:
                kw_counts = Counter(all_kw)
                lines.append("\n*🔬 주간 키워드 트렌드*")
                top_kw = kw_counts.most_common(10)
                kw_str = " · ".join(f"`{k}`({c})" for k, c in top_kw)
                lines.append(f"  {kw_str}")

                if prev_papers:
                    prev_kw = Counter()
                    for p in prev_papers:
                        prev_kw.update(p.get("keywords", []))
                    new_kw = [k for k, c in kw_counts.most_common(20) if k not in prev_kw and c >= 2]
                    rising = sorted(
                        [(k, c - prev_kw[k]) for k, c in kw_counts.most_common(20)
                         if k in prev_kw and c > prev_kw[k]],
                        key=lambda x: x[1], reverse=True,
                    )
                    if new_kw:
                        lines.append(f"  🆕 신규: {' · '.join(f'`{k}`' for k in new_kw[:5])}")
                    if rising:
                        lines.append(f"  📈 상승: {' · '.join(f'`{k}`(+{d})' for k, d in rising[:5])}")

            # ── 기타 목록 (compact) ──
            remaining = [p for p in papers if p not in spotlight[:5]]
            if remaining:
                show_n = min(10, len(remaining))
                lines.append(f"\n*📋 기타 수집 논문* (상위 {show_n}편 / 총 {len(remaining)}편)")
                for p in remaining[:10]:
                    s = f"{p['relevance_score']:.0%}"
                    a = f" — {p['authors']}" if p["authors"] else ""
                    v = f", {p['venue']}" if p["venue"] else ""
                    lines.append(f"  • [{s}] {p['title'][:60]}{a}{v}")
                if len(remaining) > 10:
                    lines.append(f"  _... 외 {len(remaining) - 10}편 → `generated/reports/digest_*.md` 참조_")

        else:
            lines.append("\n_이번 주 수집 논문 없음_")
    except Exception as e:
        lines.append("\n_Scout DB 미연동 (연동 후 자동 표시)_")
        logger.debug(f"Scout query failed: {e}")

    # ── 이번 주 주요 연구 질문 (literature 에이전트 호출 기록) ──
    try:
        from integrations.usage_tracker import tracker
        import asyncio

        def _get_lit_questions():
            conn = tracker._conn()
            rows = conn.execute(
                "SELECT DISTINCT instruction FROM agent_calls "
                "WHERE agent_name = 'literature' AND status = 'completed' "
                "AND DATE(timestamp) BETWEEN ? AND ? "
                "ORDER BY timestamp DESC LIMIT 10",
                (start_date, end_date),
            ).fetchall()
            conn.close()
            return [r["instruction"] for r in rows if r["instruction"]]

        questions = await asyncio.get_event_loop().run_in_executor(
            None, _get_lit_questions,
        )
        if questions:
            lines.append(f"\n*🔍 이번 주 연구 질문* ({len(questions)}건)")
            for q in questions[:7]:
                lines.append(f"  • {q[:80]}")
    except Exception as e:
        logger.debug(f"Research questions query failed: {e}")

    try:
        from integrations.knowledge_brief import generate_knowledge_brief
        brief = generate_knowledge_brief(date=end_date, days=7, promote=True)
        _append_brief_summary(lines, brief)
    except Exception as e:
        logger.debug(f"Weekly knowledge brief generation failed: {e}")

    lines.append(f"\n_생성: {datetime.now().strftime('%Y-%m-%d %H:%M KST')}_")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _append_paper_detail(lines: list, idx: int, p: dict):
    """Append detailed paper entry to lines list (for spotlight papers)."""
    score_pct = f"{p['relevance_score']:.0%}"
    authors = p.get("authors", "")
    venue = p.get("venue", "")
    year = p.get("year", "")
    methodology = p.get("methodology", "")
    key_results = p.get("key_results", "")
    key_contribution = p.get("key_contribution", "")
    url = p.get("url", "")

    header = f"{idx}. [{score_pct}] *{p['title']}*"
    meta_parts = []
    if authors:
        meta_parts.append(authors)
    if venue:
        meta_parts.append(venue)
    if year:
        meta_parts.append(f"({year})")
    if meta_parts:
        header += f"\n   {' · '.join(meta_parts)}"

    lines.append(header)
    if methodology:
        lines.append(f"   🔬 방법론: {methodology[:150]}")
    if key_results:
        lines.append(f"   📊 핵심 결과: {key_results[:150]}")
    if key_contribution:
        lines.append(f"   💡 핵심 기여: {key_contribution[:150]}")
    if url:
        lines.append(f"   🔗 {url}")
    lines.append("")  # blank line between papers


def _append_brief_summary(lines: list, brief: dict):
    """Append a compact Proactive Brief summary to a Slack report."""
    lines.append("\n*🧭 Proactive Brief*")
    lines.append(f"  근거: {len(brief.get('evidence_items', []))}편 · 기간: {brief.get('period_label', '')}")

    connections = brief.get("connections", [])
    if connections:
        lines.append("  *연결 신호*")
        for item in connections[:3]:
            lines.append(f"  • {item}")

    inferences = brief.get("inferences", [])
    if inferences:
        lines.append("  *추론/가설*")
        for item in inferences[:2]:
            lines.append(f"  • {item}")

    actions = brief.get("proposed_actions", [])
    if actions:
        lines.append("  *후속 업무*")
        for item in actions[:3]:
            lines.append(f"  • {item}")

    md_path = brief.get("markdown_path")
    if md_path:
        lines.append(f"  전체 파일: `{md_path}`")


def _agent_icon(name: str) -> str:
    icons = {
        "literature": "📚", "teaching": "🎓", "writing": "✍️",
        "presentation": "📽️", "project": "📋", "orchestrator": "🤖",
    }
    return icons.get(name, "🔹")


def _extract_keywords(messages: list[str], min_len: int = 2) -> Counter:
    """Extract Korean/English keywords from messages."""
    all_words: list[str] = []
    stopwords = {
        "것", "수", "있", "하", "되", "이", "대해", "관한", "대한",
        "해줘", "알려줘", "정리해줘", "분석해줘", "작성해줘",
        "the", "and", "for", "with", "this", "that", "from",
    }
    for msg in messages:
        ko_words = re.findall(r"[가-힣]{2,}", msg)
        en_words = re.findall(r"[A-Za-z]{3,}", msg)
        for w in ko_words + en_words:
            w_lower = w.lower()
            if w_lower not in stopwords and len(w_lower) >= min_len:
                all_words.append(w_lower)
    return Counter(all_words)


async def _fetch_scout_papers(start_date: str, end_date: str) -> list[dict]:
    """Fetch papers from Scout DB for date range.

    Returns list of dicts sorted by relevance_score descending.
    Includes analysis_json fields (methodology, key_results, key_contribution, tags).
    """
    import sqlite3
    import json
    from orchestrator.config import SCOUT_DB_PATH

    if not SCOUT_DB_PATH.exists():
        raise FileNotFoundError(f"Scout DB not found: {SCOUT_DB_PATH}")

    conn = sqlite3.connect(str(SCOUT_DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """SELECT title, authors, source, url, venue, year,
                  relevance_score, summary, analysis_json, topics_json,
                  exclude_report
           FROM papers
           WHERE DATE(collected_at) BETWEEN ? AND ?
             AND COALESCE(exclude_report, 0) = 0
           ORDER BY relevance_score DESC""",
        (start_date, end_date),
    ).fetchall()

    conn.close()

    results = []
    for r in rows:
        # Parse analysis_json
        analysis = {}
        try:
            analysis = json.loads(r["analysis_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            pass

        # Parse authors (JSON array or comma-separated)
        authors_raw = r["authors"] or ""
        try:
            authors_list = json.loads(authors_raw)
        except (json.JSONDecodeError, TypeError):
            authors_list = [a.strip() for a in authors_raw.split(",") if a.strip()]

        # First author et al.
        if len(authors_list) > 2:
            authors_short = f"{authors_list[0]} et al."
        elif authors_list:
            authors_short = ", ".join(authors_list)
        else:
            authors_short = ""

        # Tags from analysis_json
        tags = analysis.get("tags", [])

        # Parse topics
        topics = []
        try:
            topics = json.loads(r["topics_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            pass

        results.append({
            "title": r["title"] or "Untitled",
            "authors": authors_short,
            "source": r["source"] or "",
            "url": r["url"] or "",
            "venue": r["venue"] or "",
            "year": r["year"] or "",
            "relevance_score": (r["relevance_score"] or 0) / 100,  # normalize to 0~1
            "summary": analysis.get("summary_kr", "") or r["summary"] or "",
            "key_contribution": analysis.get("key_contribution", ""),
            "methodology": analysis.get("methodology", ""),
            "key_results": analysis.get("key_results", ""),
            "keywords": tags,
            "topics": topics,
        })
    return results


async def generate_project_weekly() -> str:
    """프로젝트 주간 리포트 (#lab-project). 매주 월 09:00 자동 전송.

    project_store API를 통해 프로젝트 데이터를 조회.
    """
    from datetime import date

    lines = [
        "📋 *프로젝트 주간 리포트*",
        f"_{datetime.now().strftime('%Y-%m-%d')}_\n",
        "═" * 30,
    ]

    try:
        from agents.project.project_store import (
            list_projects, get_project, get_all_deadlines,
        )

        projects = list_projects()
        if not projects:
            lines.append("\n_등록된 프로젝트가 없습니다._")
            lines.append("_DM으로 프로젝트를 등록하면 주간 진척 사항이 자동으로 표시됩니다._")
        else:
            lines.append(f"\n*📊 등록 프로젝트: {len(projects)}개*\n")
            for proj_info in projects:
                key = proj_info["key"]
                proj = get_project(key)
                if not proj:
                    continue

                name = proj.get("name", key)
                status = proj.get("status", "in_progress")
                status_icon = {"completed": "✅", "in_progress": "🔄", "blocked": "🚫"}.get(status, "❓")

                lines.append(f"  {status_icon} *{name}*")

                # Milestones with progress
                milestones = proj.get("milestones", [])
                if milestones:
                    completed = sum(1 for m in milestones if m.get("status") == "completed")
                    total = len(milestones)
                    progress = int(completed / total * 100) if total else 0
                    filled = int(progress / 100 * 10)
                    bar = "▓" * filled + "░" * (10 - filled)
                    lines.append(f"    {bar} {progress}% ({completed}/{total} 마일스톤)")

                    # Recently completed milestones
                    recent_done = [m for m in milestones if m.get("status") == "completed"][-3:]
                    for m in recent_done:
                        lines.append(f"    ✓ {m.get('name', '')}")

                    # In-progress milestones
                    in_progress = [m for m in milestones if m.get("status") not in ("completed", "cancelled")]
                    for m in in_progress[:3]:
                        due = m.get("due", "")
                        due_str = ""
                        if due:
                            try:
                                d = datetime.strptime(due, "%Y-%m-%d").date()
                                days_left = (d - date.today()).days
                                if days_left < 0:
                                    due_str = f" 🔴 D+{abs(days_left)}"
                                elif days_left <= 3:
                                    due_str = f" 🟠 D-{days_left}"
                                elif days_left <= 14:
                                    due_str = f" 🟡 D-{days_left}"
                                else:
                                    due_str = f" D-{days_left}"
                            except ValueError:
                                pass
                        prog = m.get("progress", 0)
                        lines.append(f"    → {m.get('name', '')} ({prog}%){due_str}")

                lines.append("")  # blank between projects

            # Upcoming deadlines across all projects
            deadlines = get_all_deadlines()
            upcoming = [d for d in deadlines if 0 <= d["d_day"] <= 14 and d["status"] != "completed"]
            if upcoming:
                lines.append("*⏰ 다가오는 마감*")
                for dl in upcoming[:5]:
                    if dl["d_day"] <= 3:
                        icon = "🔴"
                    elif dl["d_day"] <= 7:
                        icon = "🟠"
                    else:
                        icon = "🟡"
                    lines.append(f"  {icon} D-{dl['d_day']} | {dl['name']} ({dl['project']})")

            # Overdue deadlines
            overdue = [d for d in deadlines if d["d_day"] < 0 and d["status"] != "completed"]
            if overdue:
                lines.append("\n*🚨 기한 초과*")
                for dl in overdue[:5]:
                    lines.append(f"  🔴 D+{abs(dl['d_day'])} | {dl['name']} ({dl['project']})")

    except Exception as e:
        lines.append(f"\n_프로젝트 데이터 로드 실패: {e}_")
        logger.debug(f"Project data load failed: {e}")

    lines.append(f"\n_생성: {datetime.now().strftime('%Y-%m-%d %H:%M KST')}_")
    return "\n".join(lines)
