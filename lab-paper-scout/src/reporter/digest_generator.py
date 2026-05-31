"""
lab-paper-scout: Weekly digest report generator
Creates structured Markdown reports and rich Slack messages.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from src.processor.document_store import DocumentStore

logger = logging.getLogger(__name__)

# Relevance tiers
TIER_SPOTLIGHT = 90  # Full detail
TIER_NOTABLE = 70    # Table + one-liner
# Below 70: full list only


class DigestGenerator:
    """Generates weekly digest Markdown reports and Slack messages."""

    def __init__(self, reports_dir: Path, store: DocumentStore, topics: list = None):
        self.reports_dir = reports_dir
        self.store = store
        self.topics = topics or []

    # ─── Public API ────────────────────────────────────────────

    def generate(self, days: int = 7) -> str:
        """Generate a digest for the past N days. Returns filepath."""
        data = self._gather_data(days)
        report = self._build_report(data)

        filename = f"digest_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = self.reports_dir / filename
        filepath.write_text(report, encoding="utf-8")

        logger.info(f"Digest generated: {filepath}")
        return str(filepath)

    def generate_daily(self) -> str:
        """Generate a lightweight daily digest (past 24h). Returns filepath."""
        data = self._gather_data(days=1)
        report = self._build_daily_report(data)

        filename = f"daily_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = self.reports_dir / filename
        filepath.write_text(report, encoding="utf-8")

        logger.info(f"Daily digest generated: {filepath}")
        return str(filepath)

    def generate_summary_text(self, days: int = 7) -> str:
        """Generate rich Slack message for weekly digest."""
        data = self._gather_data(days)
        return self._build_slack_message(data)

    def generate_daily_summary_text(self) -> str:
        """Generate Slack message for daily digest."""
        data = self._gather_data(days=1)
        return self._build_daily_slack(data)

    def generate_survey(self, days: int = 1, min_score: int = 50) -> str:
        """Generate a survey report of backfill/citation papers. Returns filepath."""
        data = self._gather_survey_data(days, min_score)
        report = self._build_survey_report(data)

        filename = f"survey_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = self.reports_dir / filename
        filepath.write_text(report, encoding="utf-8")

        logger.info(f"Survey report generated: {filepath}")
        return str(filepath)

    def generate_survey_slack(self, days: int = 1, min_score: int = 50) -> str:
        """Generate Slack message for survey report."""
        data = self._gather_survey_data(days, min_score)
        return self._build_survey_slack(data)

    # ─── Data gathering ────────────────────────────────────────

    def _gather_data(self, days: int) -> Dict:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        all_papers = self.store.get_papers_since(since)
        # Only include reportable papers (exclude silent inbox)
        # Use analyzed_at for daily to get accurate "today's" count
        analyzed = self.store.get_reportable_papers_since(since, by_analyzed=(days <= 1))

        # Parse analysis JSON for each paper
        for p in analyzed:
            p["_analysis"] = json.loads(p.get("analysis_json") or "{}")

        # Filter out MDPI papers
        analyzed = [p for p in analyzed if not self._is_mdpi(p)]

        # Tier split
        spotlight = [p for p in analyzed if (p.get("relevance_score") or 0) >= TIER_SPOTLIGHT]
        notable = [p for p in analyzed if TIER_NOTABLE <= (p.get("relevance_score") or 0) < TIER_SPOTLIGHT]

        # Source counts
        sources = Counter(p.get("source", "unknown") for p in all_papers)

        # Tag trends
        all_tags = []
        for p in analyzed:
            all_tags.extend(p["_analysis"].get("tags", []))
        tag_counts = Counter(all_tags).most_common(10)

        # Topic grouping
        topic_groups = self._group_by_topic(analyzed)

        now = datetime.now()
        return {
            "period_start": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "all_papers": all_papers,
            "analyzed": analyzed,
            "spotlight": spotlight,
            "notable": notable,
            "sources": sources,
            "tag_counts": tag_counts,
            "topic_groups": topic_groups,
        }

    def _group_by_topic(self, papers: List[Dict]) -> List[Tuple[str, List[Dict]]]:
        """Group papers by matching tags/title against config topic keywords."""
        groups: Dict[str, List[Dict]] = {}

        # Build matching rules from config topics
        topic_rules = []
        for t in self.topics:
            display = t.get("display_name", t.get("name", "Unknown"))
            # Extract short matching tokens from keywords
            match_tokens = []
            for kw in t.get("keywords", []):
                # Split compound keywords into individual tokens
                for word in kw.lower().replace("-", " ").split():
                    if len(word) > 3:  # skip short words
                        match_tokens.append(word)
            topic_rules.append((display, match_tokens))

        for p in papers:
            tags = p["_analysis"].get("tags", [])
            title = p.get("title", "")
            searchable = " ".join(tags + [title]).lower()

            assigned = False
            for display_name, tokens in topic_rules:
                # Match if at least 2 tokens hit, or 1 token for short keyword lists
                hits = sum(1 for tok in tokens if tok in searchable)
                threshold = 2 if len(tokens) > 4 else 1
                if hits >= threshold:
                    groups.setdefault(display_name, []).append(p)
                    assigned = True
                    break

            if not assigned:
                groups.setdefault("기타", []).append(p)

        # Sort groups by priority (lower = higher priority), 기타 last
        priority_map = {
            t.get("display_name", t.get("name")): t.get("priority", 99)
            for t in self.topics
        }
        def sort_key(item):
            name = item[0]
            if name == "기타":
                return (999, 0)
            return (priority_map.get(name, 98), 0)
        return sorted(groups.items(), key=sort_key)

    # ─── Markdown report ───────────────────────────────────────

    def _build_report(self, data: Dict) -> str:
        lines = []

        # Header
        lines.append(f"# 📊 주간 연구 다이제스트 ({data['period_start']} ~ {data['period_end']})")
        lines.append("")

        # Overview
        sources = data["sources"]
        lines.append("## 한눈에 보기")
        lines.append(
            f"- 📥 수집: **{len(data['all_papers'])}편** "
            f"(ArXiv: {sources.get('arxiv', 0)}, "
            f"S2: {sources.get('semantic_scholar', 0)}, "
            f"인박스: {sources.get('manual_inbox', 0)})"
        )
        lines.append(f"- 🔍 분석: **{len(data['analyzed'])}편**")
        lines.append(f"- 🔥 주목 논문 (90+): **{len(data['spotlight'])}편**")
        lines.append(f"- 📌 관심 논문 (70-89): **{len(data['notable'])}편**")
        lines.append("")

        # Tag trends
        if data["tag_counts"]:
            tags_str = " · ".join(f"`{tag}` ({cnt}회)" for tag, cnt in data["tag_counts"][:8])
            lines.append("## 🏷️ 이번 주 키워드 트렌드")
            lines.append(tags_str)
            lines.append("")

        lines.append("---")
        lines.append("")

        # Topic-based sections
        lines.append("## 🔬 토픽별 분석")
        lines.append("")

        for topic_name, papers in data["topic_groups"]:
            papers_sorted = sorted(papers, key=lambda p: -(p.get("relevance_score") or 0))
            lines.append(f"### {topic_name} ({len(papers)}편)")
            lines.append("")

            # Top pick
            top = papers_sorted[0]
            top_a = top["_analysis"]
            top_score = top.get("relevance_score", 0)
            top_authors = self._format_authors(top)

            lines.append(f"#### ⭐ Top Pick: {top['title']}")
            author_line = f"{top_authors} " if top_authors else ""
            year_part = f"({top.get('year', '')})" if top.get("year") else ""
            lines.append(f"> {author_line}{year_part} | 관련도: {top_score:.0f}")
            lines.append(">")
            # One-line summary
            summary = top_a.get("summary_kr", "")
            if summary:
                first_sentence = summary.split(".", 1)[0] + "." if "." in summary else summary[:120]
                lines.append(f"> {first_sentence}")
            lines.append("")

            # Spotlight papers (90+) — list with full contribution
            spotlight_in_topic = [p for p in papers_sorted if (p.get("relevance_score") or 0) >= TIER_SPOTLIGHT]
            if len(spotlight_in_topic) > 1:
                lines.append("#### 🔥 주목할 논문")
                lines.append("")
                for p in spotlight_in_topic[1:]:  # skip top pick
                    pa = p["_analysis"]
                    title = p.get("title", "")
                    score = p.get("relevance_score", 0)
                    url = p.get("url", "")
                    venue = p.get("venue", "") or ""
                    contrib = pa.get("key_contribution", "")
                    if not contrib:
                        contrib = pa.get("summary_kr", "") or ""
                    oneliner = contrib.split(".", 1)[0] + "." if "." in contrib else contrib
                    venue_str = f" · 📰 {venue}" if venue else ""

                    if url:
                        lines.append(f"- **[{title}]({url})** `{score:.0f}`{venue_str}")
                    else:
                        lines.append(f"- **{title}** `{score:.0f}`{venue_str}")
                    lines.append(f"  {oneliner}")
                lines.append("")

            # Notable papers (70-89) — compact list
            notable_in_topic = [p for p in papers_sorted if TIER_NOTABLE <= (p.get("relevance_score") or 0) < TIER_SPOTLIGHT]
            if notable_in_topic:
                lines.append("#### 📌 관심 논문")
                lines.append("")
                for p in notable_in_topic:
                    pa = p["_analysis"]
                    tags = ", ".join(pa.get("tags", [])[:3])
                    title = p.get("title", "")
                    score = p.get("relevance_score", 0)
                    url = p.get("url", "")
                    venue = p.get("venue", "") or ""
                    venue_str = f" · 📰 {venue}" if venue else ""
                    if url:
                        lines.append(f"- [{title}]({url}) `{score:.0f}`{venue_str} — {tags}")
                    else:
                        lines.append(f"- {title} `{score:.0f}`{venue_str} — {tags}")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Full list
        lines.append("## 📋 전체 목록 (관련도순)")
        lines.append("")
        all_sorted = sorted(data["all_papers"], key=lambda p: -(p.get("relevance_score") or 0))
        for i, p in enumerate(all_sorted[:50], 1):
            title = p.get("title", "")
            source = p.get("source", "")
            score = p.get("relevance_score") or 0
            url = p.get("url", "")
            venue = p.get("venue", "") or ""
            venue_str = f" · 📰 {venue}" if venue else ""
            if url:
                lines.append(f"{i}. [{title}]({url}) — {source} `{score:.0f}`{venue_str}")
            else:
                lines.append(f"{i}. {title} — {source} `{score:.0f}`{venue_str}")
        lines.append("")

        return "\n".join(lines)

    def _append_compact_detail(self, lines: list, paper: dict):
        """Add a compact but informative paper entry."""
        a = paper["_analysis"]
        score = paper.get("relevance_score", 0)
        authors = self._format_authors(paper)
        url = paper.get("url", "")
        venue = paper.get("venue", "") or ""
        year = paper.get("year", "")

        title = self._sanitize_title(paper.get("title", "Untitled"))

        # Line 1: Title (with link)
        if url:
            lines.append(f"### [{title}]({url})")
        else:
            lines.append(f"### {title}")

        # Line 2: Metadata bar
        meta = f"**관련도: {score:.0f}**"
        if venue:
            meta += f" · 📰 {venue}"
        if year:
            meta += f" · {year}"
        lines.append(meta)

        # Line 3: Authors
        if authors:
            lines.append(f"✍️ _{authors}_")

        # Line 4: Key contribution
        lines.append("")
        contribution = a.get("key_contribution", "")
        if contribution:
            lines.append(f"> {contribution}")
        else:
            summary = a.get("summary_kr", "")
            if summary:
                lines.append(f"> {summary}")

        # Line 5: Tags
        tags = a.get("tags", [])
        if tags:
            lines.append(f"")
            lines.append(f"🏷️ `{'` `'.join(tags)}`")

        lines.append("")
        lines.append("---")
        lines.append("")

    def _is_mdpi(self, paper: dict) -> bool:
        """Return True if paper is from MDPI (DOI prefix 10.3390 is MDPI-exclusive)."""
        venue = (paper.get("venue") or "").lower()
        url = (paper.get("url") or "").lower()
        return "mdpi" in venue or "mdpi.com" in url or "10.3390/" in url

    @staticmethod
    def _sanitize_title(title: str) -> str:
        """Clean up problematic patterns in titles for Markdown rendering."""
        import re
        # Remove [Formula: see text] and similar LaTeX placeholders
        title = re.sub(r'\[Formula:\s*see\s*text\]', '', title, flags=re.IGNORECASE)
        # Remove dangling brackets/parens at start
        title = re.sub(r'^[\[\(]\s*', '', title)
        # Collapse extra whitespace
        title = re.sub(r'\s+', ' ', title).strip()
        # Escape bare [ ] that aren't part of a link (Markdown link confusion)
        title = title.replace('[', '\u27e6').replace(']', '\u27e7')
        return title

    def _format_authors(self, paper: dict) -> str:
        authors_raw = paper.get("authors", "[]")
        try:
            authors = json.loads(authors_raw) if isinstance(authors_raw, str) else authors_raw
        except json.JSONDecodeError:
            return ""
        if not authors:
            return ""
        if len(authors) <= 3:
            return ", ".join(authors)
        # First 2 + last (corresponding) author — no count
        return f"{authors[0]}, {authors[1]}, ... {authors[-1]} et al."

    # ─── Slack message ─────────────────────────────────────────

    def _build_slack_message(self, data: Dict) -> str:
        sources = data["sources"]
        lines = []

        lines.append(f"📊 *주간 연구 다이제스트* — {data['period_end']}")
        lines.append("")
        lines.append(
            f"📥 수집 *{len(data['all_papers'])}편* "
            f"(ArXiv {sources.get('arxiv', 0)} · S2 {sources.get('semantic_scholar', 0)} · "
            f"인박스 {sources.get('manual_inbox', 0)})"
        )
        lines.append(
            f"🔍 분석 *{len(data['analyzed'])}편* · "
            f"🔥 주목 *{len(data['spotlight'])}편* · "
            f"📌 관심 *{len(data['notable'])}편*"
        )
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━")

        # Trends
        if data["tag_counts"]:
            tags_str = " · ".join(f"`{tag}`" for tag, _ in data["tag_counts"][:6])
            lines.append(f"🏷️ 트렌드: {tags_str}")
            lines.append("━━━━━━━━━━━━━━━━━━━")

        # Top 3
        if data["spotlight"]:
            lines.append("")
            lines.append("⭐ *Top 논문*")
            lines.append("")

            top3 = sorted(data["spotlight"], key=lambda p: -(p.get("relevance_score") or 0))[:3]
            for i, p in enumerate(top3, 1):
                a = p["_analysis"]
                score = p.get("relevance_score", 0)
                title = p.get("title", "Untitled")
                url = p.get("url", "")
                venue = p.get("venue", "") or ""
                authors = self._format_authors(p)

                lines.append(f"{i}️⃣ *{title}*")
                meta = f"    관련도: `{score:.0f}`"
                if venue:
                    meta += f" · 📰 {venue}"
                lines.append(meta)
                if authors:
                    lines.append(f"    ✍️ {authors}")

                contrib = a.get("key_contribution", "")
                if contrib:
                    first = contrib.split(".", 1)[0] + "." if "." in contrib else contrib
                    lines.append(f"    {first}")
                elif a.get("summary_kr"):
                    first = a["summary_kr"].split(".", 1)[0] + "."
                    lines.append(f"    {first}")

                if url:
                    lines.append(f"    <{url}|📄 논문 보기>")
                lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.append("📄 전체 보고서: Dropbox > lab-paper-scout > data/reports/")

        return "\n".join(lines)

    # ─── Daily digest ──────────────────────────────────────────

    def _build_daily_report(self, data: Dict) -> str:
        """Build lightweight daily Markdown report."""
        lines = []
        date = data["period_end"]
        sources = data["sources"]

        lines.append(f"# 📬 일간 논문 브리핑 ({date})")
        lines.append("")

        total = len(data["all_papers"])
        if total == 0:
            lines.append("오늘 새로 수집된 논문이 없습니다.")
            return "\n".join(lines)

        lines.append(
            f"📥 **{total}편** 수집 "
            f"(ArXiv {sources.get('arxiv', 0)} · "
            f"S2 {sources.get('semantic_scholar', 0)} · "
            f"인박스 {sources.get('manual_inbox', 0)})"
        )
        lines.append("")

        # Spotlight papers — full detail
        if data["spotlight"]:
            lines.append("## 🔥 주목할 논문")
            lines.append("")
            for p in data["spotlight"]:
                a = p["_analysis"]
                raw_title = p.get("title", "")
                title = self._sanitize_title(raw_title)
                score = p.get("relevance_score", 0)
                url = p.get("url", "")
                venue = p.get("venue", "") or ""
                authors = self._format_authors(p)
                contrib = a.get("key_contribution", "")
                if not contrib:
                    contrib = a.get("summary_kr", "") or ""
                oneliner = contrib.split(".", 1)[0] + "." if "." in contrib else contrib

                # Title line
                if url:
                    lines.append(f"### [{title}]({url})")
                else:
                    lines.append(f"### {title}")

                # Meta line
                meta = f"**관련도: {score:.0f}**"
                if venue:
                    meta += f" · 📰 {venue}"
                lines.append(meta)

                # Authors
                if authors:
                    lines.append(f"✍️ _{authors}_")

                # Contribution
                lines.append("")
                lines.append(f"> {oneliner}")

                # Tags
                tags = a.get("tags", [])
                if tags:
                    lines.append("")
                    lines.append(f"🏷️ `{'` `'.join(tags)}`")

                lines.append("")
                lines.append("---")
                lines.append("")

        # Other papers — compact with link and venue
        others = [p for p in data["analyzed"]
                  if (p.get("relevance_score") or 0) < TIER_SPOTLIGHT]
        if others:
            lines.append("## 📋 기타 수집 논문")
            lines.append("")
            for p in others:
                raw_title = p.get("title", "")
                title = self._sanitize_title(raw_title)
                score = p.get("relevance_score") or 0
                url = p.get("url", "")
                venue = p.get("venue", "") or ""
                authors = self._format_authors(p)
                venue_str = f" · 📰 {venue}" if venue else ""
                author_str = f" · ✍️ {authors}" if authors else ""
                if url:
                    lines.append(f"- [{title}]({url}) `{score:.0f}`{venue_str}{author_str}")
                else:
                    lines.append(f"- {title} `{score:.0f}`{venue_str}{author_str}")
            lines.append("")

        return "\n".join(lines)

    def _build_daily_slack(self, data: Dict) -> str:
        """Build lightweight daily Slack notification."""
        lines = []
        date = data["period_end"]
        sources = data["sources"]
        total = len(data["all_papers"])

        lines.append(f"📬 *일간 논문 브리핑* — {date}")
        lines.append("")

        if total == 0:
            lines.append("오늘 새로 수집된 논문이 없습니다.")
            return "\n".join(lines)

        lines.append(
            f"📥 *{total}편* 수집 "
            f"(ArXiv {sources.get('arxiv', 0)} · "
            f"S2 {sources.get('semantic_scholar', 0)} · "
            f"인박스 {sources.get('manual_inbox', 0)})"
        )

        if data["spotlight"]:
            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━")
            lines.append(f"🔥 주목 논문 *{len(data['spotlight'])}편*")
            lines.append("")
            for p in data["spotlight"][:5]:
                a = p["_analysis"]
                title = p.get("title", "")
                score = p.get("relevance_score", 0)
                url = p.get("url", "")
                venue = p.get("venue", "") or ""
                authors = self._format_authors(p)
                contrib = a.get("key_contribution", "")
                if not contrib:
                    contrib = a.get("summary_kr", "") or ""
                oneliner = contrib.split(".", 1)[0] + "." if "." in contrib else contrib

                lines.append(f"• *{title}*")
                meta = f"    `{score:.0f}`"
                if venue:
                    meta += f" · 📰 {venue}"
                lines.append(meta)
                if authors:
                    lines.append(f"    ✍️ {authors}")
                lines.append(f"    {oneliner}")
                if url:
                    lines.append(f"    <{url}|📄 보기>")
                lines.append("")

        return "\n".join(lines)

    # ─── Survey report (backfill + citation chase) ─────────────

    def _gather_survey_data(self, days: int, min_score: int) -> Dict:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        papers = self.store.get_survey_papers_since(since, min_score)

        for p in papers:
            p["_analysis"] = json.loads(p.get("analysis_json") or "{}")

        # Split by source
        backfill = [p for p in papers if p.get("source") == "backfill"]
        citation = [p for p in papers if p.get("source") == "citation_chase"]

        return {
            "period_days": days,
            "min_score": min_score,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "papers": papers,
            "backfill": backfill,
            "citation": citation,
        }

    def _build_survey_report(self, data: Dict) -> str:
        lines = []
        papers = data["papers"]

        lines.append(f"# 🔭 서베이 리포트 — {data['date']}")
        lines.append(f"최근 {data['period_days']}일 · 관련도 {data['min_score']}+ · "
                      f"총 {len(papers)}편 (백필 {len(data['backfill'])}편, 인용추적 {len(data['citation'])}편)")
        lines.append("")

        if not papers:
            lines.append("해당 기간 내 기준을 충족하는 서베이 논문이 없습니다.")
            return "\n".join(lines)

        # Group by source
        for label, group in [("📚 백필 (과거 논문)", data["backfill"]),
                              ("🔗 인용 추적", data["citation"])]:
            if not group:
                continue
            lines.append(f"## {label} ({len(group)}편)")
            lines.append("")

            sorted_group = sorted(group, key=lambda p: -(p.get("relevance_score") or 0))
            for p in sorted_group:
                self._append_compact_detail(lines, p)

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _build_survey_slack(self, data: Dict) -> str:
        papers = data["papers"]
        lines = [
            f"🔭 *서베이 리포트* — {data['date']}",
            f"최근 {data['period_days']}일 · 관련도 {data['min_score']}+ · "
            f"총 {len(papers)}편",
            "",
        ]

        if not papers:
            lines.append("해당 기간 내 기준을 충족하는 서베이 논문이 없습니다.")
            return "\n".join(lines)

        lines.append("━━━━━━━━━━━━━━━━━━━")
        sorted_papers = sorted(papers, key=lambda p: -(p.get("relevance_score") or 0))
        for p in sorted_papers[:15]:
            a = p.get("_analysis", {})
            title = p.get("title", "")
            score = p.get("relevance_score") or 0
            source = "📚" if p.get("source") == "backfill" else "🔗"
            url = p.get("url", "")
            venue = p.get("venue", "") or ""
            authors = self._format_authors(p)

            contrib = a.get("key_contribution") or a.get("summary_kr", "") or ""
            oneliner = contrib.split(".", 1)[0] + "." if "." in contrib else contrib

            lines.append(f"{source} *{title}*")
            meta = f"    `{score:.0f}`"
            if venue:
                meta += f" · 📰 {venue}"
            lines.append(meta)
            if authors:
                lines.append(f"    ✍️ {authors}")
            lines.append(f"    {oneliner}")
            if url:
                lines.append(f"    <{url}|📄 보기>")
            lines.append("")

        if len(papers) > 15:
            lines.append(f"_...외 {len(papers)-15}편 (전체 리포트 참조)_")

        return "\n".join(lines)
