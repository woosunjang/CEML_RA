"""
Knowledge Brief generation for Scout/Knowledge autonomy.

The brief is intentionally deterministic for v1: it uses Scout's analyzed
paper metadata as evidence, keeps model-style inferences in a separate
section, writes both Markdown and JSON artifacts, and optionally promotes
high-confidence paper facts into the archival Graphiti queue.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Any

from integrations.autonomy import log_autonomy_action
from integrations.sqlite_snapshot import sqlite_snapshot
from orchestrator.config import (
    ARCHIVAL_QUEUE_DIR,
    DATA_DIR,
    GENERATED_REPORTS_DIR,
    SCOUT_DB_PATH,
)


BRIEF_DATA_DIR = DATA_DIR / "knowledge_briefs"
PROMOTION_STATE_PATH = DATA_DIR / "scout_graph_promotion_state.json"
DEFAULT_MIN_SCORE = 70.0
GRAPH_PROMOTION_SCORE = 90.0
MAX_EVIDENCE_ITEMS = 12
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BriefPeriod:
    start_date: str
    end_date: str

    @property
    def label(self) -> str:
        if self.start_date == self.end_date:
            return self.end_date
        return f"{self.start_date} ~ {self.end_date}"


def _today_kst() -> Date:
    # The Mac Mini and current workspace are configured for KST. Keeping this
    # local avoids adding a runtime dependency solely for timezone handling.
    return datetime.now().date()


def _period(end_date: str | None = None, days: int = 1) -> BriefPeriod:
    days = max(1, int(days or 1))
    end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else _today_kst()
    start = end - timedelta(days=days - 1)
    return BriefPeriod(start.isoformat(), end.isoformat())


def _safe_slug(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", text).strip("_")
    return (slug[:max_len] or "all").strip("_")


def _parse_json(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _authors_short(raw: str | None) -> str:
    authors = _parse_json(raw, None)
    if not isinstance(authors, list):
        authors = [a.strip() for a in (raw or "").split(",") if a.strip()]
    if len(authors) > 2:
        return f"{authors[0]} et al."
    return ", ".join(authors)


def _matches_query(paper: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        str(paper.get(k, ""))
        for k in (
            "title",
            "abstract",
            "summary",
            "key_contribution",
            "methodology",
            "key_results",
        )
    ).lower()
    tags = " ".join(paper.get("keywords", []) + paper.get("topics", [])).lower()
    tokens = [t for t in re.split(r"\s+", query.lower()) if t]
    return all(t in haystack or t in tags for t in tokens)


def _query_scout_rows(db_path: Path, period: BriefPeriod) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """SELECT id, title, authors, source, url, venue, year, abstract,
                      relevance_score, summary, analysis_json, topics_json,
                      collected_at, analyzed_at, COALESCE(exclude_report, 0) as exclude_report
               FROM papers
               WHERE DATE(collected_at) BETWEEN ? AND ?
                 AND status = 'analyzed'
               ORDER BY relevance_score DESC, collected_at DESC""",
            (period.start_date, period.end_date),
        ).fetchall()
    finally:
        conn.close()


def fetch_scout_evidence(
    *,
    end_date: str | None = None,
    days: int = 1,
    query: str = "",
    min_score: float = DEFAULT_MIN_SCORE,
    db_path: Path = SCOUT_DB_PATH,
) -> tuple[BriefPeriod, list[dict[str, Any]]]:
    """Fetch analyzed Scout papers for a period and convert them to evidence."""
    period = _period(end_date, days)
    if not db_path.exists():
        return period, []

    try:
        rows = _query_scout_rows(db_path, period)
    except sqlite3.OperationalError as exc:
        if "disk I/O error" not in str(exc):
            raise
        logger.warning("Scout DB direct read failed; using temporary snapshot: %s", exc)
        with sqlite_snapshot(db_path) as snapshot:
            rows = _query_scout_rows(snapshot, period)

    papers: list[dict[str, Any]] = []
    for row in rows:
        analysis = _parse_json(row["analysis_json"], {})
        topics = _parse_json(row["topics_json"], [])
        tags = analysis.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        if not isinstance(topics, list):
            topics = [str(topics)]

        score = float(row["relevance_score"] or 0)
        paper = {
            "paper_id": row["id"],
            "title": row["title"] or "Untitled",
            "authors": _authors_short(row["authors"]),
            "source": row["source"] or "",
            "url": row["url"] or "",
            "venue": row["venue"] or "",
            "year": row["year"] or "",
            "abstract": row["abstract"] or "",
            "relevance_score": score,
            "summary": analysis.get("summary_kr") or row["summary"] or "",
            "key_contribution": analysis.get("key_contribution", ""),
            "methodology": analysis.get("methodology", ""),
            "key_results": analysis.get("key_results", ""),
            "keywords": tags,
            "topics": topics,
            "collected_at": row["collected_at"],
            "analyzed_at": row["analyzed_at"],
            "exclude_report": int(row["exclude_report"] or 0),
        }
        if score >= min_score and _matches_query(paper, query):
            papers.append(paper)

    return period, papers


def _build_connections(papers: list[dict[str, Any]]) -> list[str]:
    tags = Counter()
    topics = Counter()
    sources = Counter()
    for p in papers:
        tags.update(p.get("keywords", []))
        topics.update(p.get("topics", []))
        if p.get("source"):
            sources[p["source"]] += 1

    connections: list[str] = []
    for tag, count in tags.most_common(5):
        if count >= 2:
            connections.append(f"`{tag}` 키워드가 {count}편에서 반복되어, 단일 논문보다 방법론/응용 축으로 묶어 볼 가치가 있습니다.")
    for topic, count in topics.most_common(3):
        if count >= 2:
            connections.append(f"`{topic}` 토픽에서 {count}편이 모여 있어 해당 주제의 최근 흐름을 별도 mini-review로 정리할 수 있습니다.")
    if len(sources) >= 2:
        source_text = ", ".join(f"{k} {v}편" for k, v in sources.most_common())
        connections.append(f"수집 출처가 {source_text}로 분산되어 있어, Scout/인용추적/백필 결과를 구분해 해석해야 합니다.")

    if not connections and papers:
        connections.append("오늘 근거는 아직 뚜렷한 클러스터보다 개별 논문 신호가 강합니다. 다음 수집 주기까지 같은 키워드가 반복되는지 추적하는 편이 좋습니다.")
    return connections


def _build_inferences(papers: list[dict[str, Any]]) -> list[str]:
    if not papers:
        return []

    top_tags = [tag for tag, _ in Counter(t for p in papers for t in p.get("keywords", [])).most_common(4)]
    high = [p for p in papers if p["relevance_score"] >= GRAPH_PROMOTION_SCORE]

    inferences = []
    if high:
        inferences.append(f"관련도 90점 이상 논문이 {len(high)}편 있어, 단순 모니터링보다 지식베이스 승격과 후속 비교 분석을 자동 수행할 만합니다.")
    if top_tags:
        inferences.append(f"반복 키워드({', '.join(top_tags)})는 다음 주 문헌 비교표의 축으로 쓰기 좋습니다.")
    inferences.append("이 해석은 Scout 분석 메타데이터 기반의 모델 추론이며, 실제 연구 채택 전에는 원문 PDF와 실험/계산 조건을 확인해야 합니다.")
    return inferences


def _build_actions(papers: list[dict[str, Any]]) -> list[str]:
    if not papers:
        return ["수집 논문이 없으므로 Scout rate limit, topic query, collection schedule을 점검합니다."]

    actions = [
        "상위 논문 3~5편을 대상으로 Literature Agent 비교표 생성을 예약합니다.",
        "관련도 90점 이상 논문은 Graphiti 장기 기억과 Qdrant RAG 인덱스에 우선 반영합니다.",
    ]
    tags = [tag for tag, _ in Counter(t for p in papers for t in p.get("keywords", [])).most_common(3)]
    if tags:
        actions.append(f"다음 Scout query 후보로 {', '.join(tags)} 조합을 별도 추적합니다.")
    return actions


def _build_cautions(papers: list[dict[str, Any]], total_seen: int) -> list[str]:
    cautions = []
    if total_seen == 0:
        cautions.append("해당 기간에 Scout DB 근거가 없습니다. 수집 데몬, API rate limit, 날짜 범위를 먼저 확인해야 합니다.")
    elif not papers:
        cautions.append("논문은 수집되었지만 relevance threshold를 넘은 근거가 없습니다. threshold 또는 topic 설정 점검이 필요합니다.")
    if any(p.get("source") == "backfill" for p in papers):
        cautions.append("backfill 논문은 최신 신규 논문이 아니라 과거 구간 보강분일 수 있으므로 trend 해석에서 분리해야 합니다.")
    if papers and all(p.get("exclude_report") for p in papers):
        cautions.append("이 기간의 근거는 기존 daily report에서는 제외 표시된 논문입니다. 지식베이스 후보로는 보되 일반 리포트 수집량과는 구분해야 합니다.")
    if len(papers) > MAX_EVIDENCE_ITEMS:
        cautions.append(f"표시 근거는 상위 {MAX_EVIDENCE_ITEMS}편으로 제한했습니다. 전체 JSON 파일에서 나머지 근거를 확인할 수 있습니다.")
    return cautions


def _citation_line(idx: int, paper: dict[str, Any]) -> str:
    score = paper["relevance_score"]
    authors = f" — {paper['authors']}" if paper.get("authors") else ""
    venue = f", {paper['venue']}" if paper.get("venue") else ""
    url = f" ({paper['url']})" if paper.get("url") else ""
    return f"[{idx}] {paper['title']}{authors}{venue}, {paper.get('year', '')}. relevance={score:.0f}.{url}"


def brief_to_markdown(brief: dict[str, Any]) -> str:
    """Render a KnowledgeBrief dict as Markdown suitable for Slack/files."""
    lines = [
        f"# Proactive Research Brief — {brief['period_label']}",
        "",
        f"- 근거 논문: {len(brief['papers'])}편",
        f"- Query: `{brief['query'] or 'all topics'}`",
        f"- Evidence policy: 근거와 추론을 분리",
        "",
        "## 새 근거",
    ]

    if not brief["evidence_items"]:
        lines.append("- 해당 기간/조건에서 표시할 근거가 없습니다.")
    else:
        for item in brief["evidence_items"]:
            lines.append(
                f"- [{item['citation_number']}] **{item['title']}** "
                f"({item['relevance_score']:.0f}) — {item['evidence_text']}"
            )

    lines.extend(["", "## 논문 간 연결"])
    lines.extend(f"- {c}" for c in brief["connections"])

    lines.extend(["", "## 모델 추론/가설"])
    lines.extend(f"- {i}" for i in brief["inferences"])

    lines.extend(["", "## 후속 업무 제안"])
    lines.extend(f"- {a}" for a in brief["proposed_actions"])

    lines.extend(["", "## 주의할 점"])
    if brief["cautions"]:
        lines.extend(f"- {c}" for c in brief["cautions"])
    else:
        lines.append("- 특이 주의사항 없음.")

    lines.extend(["", "## 인용 논문 목록"])
    if brief["citations"]:
        lines.extend(f"- {c}" for c in brief["citations"])
    else:
        lines.append("- 없음")

    lines.append("")
    lines.append(f"_Generated: {brief['generated_at']}_")
    return "\n".join(lines)


def _artifact_stem(period: BriefPeriod, query: str) -> str:
    if period.start_date == period.end_date:
        stem = f"brief_{period.end_date.replace('-', '')}"
    else:
        stem = f"brief_{period.start_date.replace('-', '')}_{period.end_date.replace('-', '')}"
    if query:
        stem += f"_{_safe_slug(query)}"
    return stem


def _current_markdown_path(
    json_path: Path,
    data: dict[str, Any],
    report_dir: Path | None = None,
) -> str:
    report_dir = report_dir or GENERATED_REPORTS_DIR
    stored_path = str(data.get("markdown_path") or "")
    stored_name = Path(stored_path).name if stored_path else ""
    markdown_name = stored_name if stored_name.endswith(".md") else f"{json_path.stem}.md"
    return str(report_dir / markdown_name)


def _normalize_artifact_paths(
    data: dict[str, Any],
    json_path: Path,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    normalized = dict(data)
    normalized["json_path"] = str(json_path)
    normalized["markdown_path"] = _current_markdown_path(json_path, data, report_dir)
    return normalized


def _load_existing_brief_artifact(
    *,
    data_dir: Path,
    report_dir: Path,
    period: BriefPeriod,
    query: str,
) -> dict[str, Any] | None:
    path = data_dir / f"{_artifact_stem(period, query)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return _normalize_artifact_paths(data, path, report_dir)


def _promote_to_graph_queue(brief: dict[str, Any], papers: list[dict[str, Any]]) -> list[str]:
    ARCHIVAL_QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    state_file_existed = PROMOTION_STATE_PATH.exists()
    state = _load_promotion_state()
    promoted_state = state.setdefault("promoted_papers", {})
    queued_files: list[str] = []
    changed_files: list[str] = []
    now = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")

    for idx, paper in enumerate(papers):
        if paper["relevance_score"] < GRAPH_PROMOTION_SCORE:
            continue
        paper_id = paper["paper_id"]
        if paper_id in promoted_state:
            continue
        facts = [
            f"Title: {paper['title']}",
            f"Topics: {', '.join(paper.get('topics', []))}",
            f"Keywords: {', '.join(paper.get('keywords', []))}",
            f"Contribution: {paper.get('key_contribution') or paper.get('summary')}",
            f"Methodology: {paper.get('methodology')}",
            f"Key results: {paper.get('key_results')}",
            f"URL: {paper.get('url')}",
        ]
        job = {
            "conversation_id": f"scout-{paper_id}",
            "user_message": "Promote high-relevance Scout paper into archival research memory.",
            "assistant_message": "\n".join(f for f in facts if f and not f.endswith(": ")),
            "agent_name": "knowledge_brief",
            "timestamp": datetime.utcnow().isoformat(),
        }
        filename = ARCHIVAL_QUEUE_DIR / f"{now}_{idx:03d}_scout.json"
        filename.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        promoted_state[paper_id] = {
            "title": paper["title"],
            "relevance_score": paper["relevance_score"],
            "queued_at": job["timestamp"],
            "queue_file": str(filename),
            "analyzed_at": paper.get("analyzed_at", ""),
        }
        queued_files.append(str(filename))
        changed_files.append(str(filename))

    if queued_files or (not state_file_existed and promoted_state):
        _save_promotion_state(state)
        changed_files.append(str(PROMOTION_STATE_PATH))
    if queued_files:
        brief["metadata"]["graph_queue_files"] = queued_files
    return changed_files


def _load_promotion_state() -> dict[str, Any]:
    state: dict[str, Any] = {"promoted_papers": {}}
    if PROMOTION_STATE_PATH.exists():
        try:
            state = json.loads(PROMOTION_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {"promoted_papers": {}}

    promoted = state.setdefault("promoted_papers", {})
    # Bootstrap from already queued jobs so a freshly introduced state file
    # does not duplicate jobs that are waiting for the worker.
    for queue_file in ARCHIVAL_QUEUE_DIR.glob("*_scout.json"):
        try:
            job = json.loads(queue_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        conv_id = job.get("conversation_id", "")
        if conv_id.startswith("scout-"):
            paper_id = conv_id[len("scout-"):]
            promoted.setdefault(paper_id, {
                "title": "",
                "relevance_score": None,
                "queued_at": job.get("timestamp", ""),
                "queue_file": str(queue_file),
                "analyzed_at": "",
            })
    return state


def _save_promotion_state(state: dict[str, Any]):
    PROMOTION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMOTION_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generate_knowledge_brief(
    *,
    date: str | None = None,
    days: int = 1,
    query: str = "",
    min_score: float = DEFAULT_MIN_SCORE,
    promote: bool = True,
    write_files: bool = True,
    log_action: bool = True,
    db_path: Path = SCOUT_DB_PATH,
    data_dir: Path = BRIEF_DATA_DIR,
    report_dir: Path = GENERATED_REPORTS_DIR,
) -> dict[str, Any]:
    """Generate, persist, and optionally promote a proactive knowledge brief."""
    period, papers = fetch_scout_evidence(
        end_date=date,
        days=days,
        query=query,
        min_score=min_score,
        db_path=db_path,
    )
    _, all_seen = fetch_scout_evidence(
        end_date=date,
        days=days,
        query=query,
        min_score=0,
        db_path=db_path,
    )

    if not papers and not all_seen:
        existing = _load_existing_brief_artifact(
            data_dir=data_dir,
            report_dir=report_dir,
            period=period,
            query=query,
        )
        if existing and existing.get("evidence_items"):
            metadata = dict(existing.get("metadata") or {})
            metadata["reused_existing_due_to_empty_source"] = True
            existing["metadata"] = metadata
            if log_action:
                log_autonomy_action(
                    "knowledge_brief.reuse_existing",
                    "Existing brief was returned because Scout DB had no rows for the requested period.",
                    inputs={
                        "date": date,
                        "days": days,
                        "query": query,
                        "min_score": min_score,
                    },
                    files_changed=[
                        existing.get("json_path", ""),
                        existing.get("markdown_path", ""),
                    ],
                )
            return existing

    evidence_papers = papers[:MAX_EVIDENCE_ITEMS]
    evidence_items = []
    citations = []
    for idx, paper in enumerate(evidence_papers, 1):
        evidence_text = (
            paper.get("key_contribution")
            or paper.get("key_results")
            or paper.get("summary")
            or paper.get("abstract", "")[:240]
        )
        evidence_items.append({
            "paper_id": paper["paper_id"],
            "title": paper["title"],
            "url": paper.get("url", ""),
            "relevance_score": paper["relevance_score"],
            "evidence_text": evidence_text,
            "citation_number": idx,
        })
        citations.append(_citation_line(idx, paper))

    now = datetime.now().isoformat()
    brief: dict[str, Any] = {
        "date": period.end_date,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "period_label": period.label,
        "query": query,
        "min_score": min_score,
        "generated_at": now,
        "papers": papers,
        "evidence_items": evidence_items,
        "connections": _build_connections(papers),
        "inferences": _build_inferences(papers),
        "proposed_actions": _build_actions(papers),
        "cautions": _build_cautions(papers, len(all_seen)),
        "citations": citations,
        "metadata": {
            "total_seen": len(all_seen),
            "evidence_count": len(evidence_items),
            "graph_promotion_threshold": GRAPH_PROMOTION_SCORE,
        },
    }

    markdown = brief_to_markdown(brief)
    brief["markdown"] = markdown

    changed_files: list[str] = []
    if promote:
        promoted = _promote_to_graph_queue(brief, papers)
        changed_files.extend(promoted)

    if write_files:
        data_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        stem = _artifact_stem(period, query)
        json_path = data_dir / f"{stem}.json"
        md_path = report_dir / f"{stem}.md"

        brief["json_path"] = str(json_path)
        brief["markdown_path"] = str(md_path)
        json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        changed_files.extend([str(json_path), str(md_path)])

    if log_action and (write_files or promote):
        log_autonomy_action(
            "knowledge_brief.generate",
            "Scout evidence was summarized into a proactive research brief.",
            inputs={
                "date": date,
                "days": days,
                "query": query,
                "min_score": min_score,
                "promote": promote,
            },
            files_changed=changed_files,
        )

    return brief


def list_knowledge_briefs(limit: int = 30) -> list[dict[str, Any]]:
    """List persisted brief metadata, newest first."""
    if not BRIEF_DATA_DIR.exists():
        return []
    items = []
    for path in sorted(BRIEF_DATA_DIR.glob("brief_*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        data = _normalize_artifact_paths(data, path)
        items.append({
            "date": data.get("date"),
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "period_label": data.get("period_label"),
            "query": data.get("query", ""),
            "evidence_count": len(data.get("evidence_items", [])),
            "json_path": str(path),
            "markdown_path": data.get("markdown_path", ""),
            "generated_at": data.get("generated_at"),
        })
    return items


def load_latest_brief() -> dict[str, Any] | None:
    """Load the newest persisted brief."""
    briefs = list_knowledge_briefs(limit=1)
    if not briefs:
        return None
    path = Path(briefs[0]["json_path"])
    data = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_artifact_paths(data, path)


async def search_knowledge(query: str, limit: int = 5) -> dict[str, Any]:
    """Search Scout, RAG, and archival memory for one query."""
    from integrations.hybrid_retriever import hybrid_search
    from integrations.scout_reader import ScoutReader
    from orchestrator.archival import archival_memory

    errors = []
    scout_results = []
    try:
        scout_results = ScoutReader().search_papers(query, limit=limit)
    except Exception as exc:
        logger.warning("Scout search failed: %s", exc)
        errors.append({"source": "scout", "error": str(exc)})

    rag_results = []
    try:
        for r in hybrid_search(query, limit=limit):
            rag_results.append({
                "score": r.score,
                "title": r.payload.get("title", ""),
                "document_type": r.payload.get("document_type", ""),
                "source": r.payload.get("source", ""),
                "text": (r.payload.get("text", "") or "")[:600],
            })
    except Exception as exc:
        logger.warning("RAG search failed: %s", exc)
        errors.append({"source": "rag", "error": str(exc)})

    archival_results = []
    try:
        archival_results = await archival_memory.search(query, limit=limit)
    except Exception as exc:
        logger.warning("Archival search failed: %s", exc)
        errors.append({"source": "archival", "error": str(exc)})

    return {
        "query": query,
        "scout": scout_results,
        "rag": rag_results,
        "archival": archival_results,
        "errors": errors,
    }
