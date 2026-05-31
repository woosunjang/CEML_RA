"""
lab-paper-scout: Pipeline orchestrator
Connects all modules and runs the full collection → process → analyze → report pipeline.
"""
import json
import logging
from pathlib import Path

from src.config import Config
from src.collector.arxiv_collector import ArxivCollector
from src.collector.semantic_scholar import SemanticScholarCollector
from src.collector.backfill_collector import BackfillCollector
from src.collector.citation_chaser import CitationChaser
from src.collector.inbox_watcher import InboxWatcher
from src.processor.document_store import DocumentStore
from src.processor.pdf_extractor import PDFExtractor
from src.analyzer.summarizer import Summarizer
from src.reporter.digest_generator import DigestGenerator
from src.notifier.slack_notifier import SlackNotifier
from src.integrations.rag_bridge import RAGBridge

logger = logging.getLogger(__name__)


class Pipeline:
    """Main pipeline orchestrator."""

    def __init__(self, config: Config):
        self.config = config
        self.store = DocumentStore(config.get_path("db"))
        self.extractor = PDFExtractor()
        self.digest = DigestGenerator(config.get_path("reports"), self.store, topics=config.topics)
        self.slack = SlackNotifier(config.slack_webhook_url)
        self.slack_prefix = ""  # Set to "[🧪 TEST] " for smoketest

        # Collectors
        self.arxiv = ArxivCollector(config._data, self.store)
        self.s2 = SemanticScholarCollector(config._data, self.store)
        self.inbox = InboxWatcher(
            config.get_path("inbox"),
            config.get_path("archive"),
            self.store,
        )
        self.backfill = BackfillCollector(
            config._data, self.store, config.project_root / "data"
        )
        self.citation_chaser = CitationChaser(config._data, self.store)

        # Analyzer (lazy init — needs API key)
        self._summarizer = None

        # RAG bridge (Phase 3 — sync to Qdrant)
        rag_config = config._data.get("rag", {})
        self.rag_bridge = RAGBridge(rag_config) if rag_config.get("enabled") else None

    @property
    def summarizer(self) -> Summarizer:
        if self._summarizer is None:
            self._summarizer = Summarizer(self.config._data)
        return self._summarizer

    def _send_slack(self, message: str):
        """Send Slack message with optional prefix (e.g. test marker)."""
        self.slack.send(f"{self.slack_prefix}{message}")

    def run_collection(self):
        """Run all collection sources."""
        logger.info("=" * 60)
        logger.info("Starting collection run...")

        topics = self.config.topics
        new_papers = []

        # ArXiv
        try:
            new_papers.extend(self.arxiv.collect(topics))
        except Exception as e:
            logger.error(f"ArXiv collection failed: {e}")

        # Semantic Scholar
        try:
            new_papers.extend(self.s2.collect(topics))
        except Exception as e:
            logger.error(f"Semantic Scholar collection failed: {e}")

        # Inbox
        try:
            new_papers.extend(self.inbox.check_inbox())
        except Exception as e:
            logger.error(f"Inbox check failed: {e}")

        # Backfill (older papers)
        try:
            new_papers.extend(self.backfill.collect(topics))
        except Exception as e:
            logger.error(f"Backfill collection failed: {e}")

        logger.info(f"Collection complete: {len(new_papers)} new papers total.")
        return new_papers

    def run_processing(self):
        """Process all collected (unprocessed) papers."""
        logger.info("Starting processing run...")

        papers = self.store.get_papers_by_status("collected")
        processed_count = 0

        for paper in papers:
            pdf_url = paper.get("pdf_url", "")
            if not pdf_url:
                # No PDF available — skip processing, go straight to analysis with abstract
                self.store.mark_processed(paper["id"], "")
                processed_count += 1
                continue

            pdf_path = pdf_url
            # For arxiv papers, download first if needed
            if paper.get("source") == "arxiv" and pdf_url.startswith("http"):
                downloaded = self.arxiv.download_pdf(
                    paper, str(self.config.get_path("archive"))
                )
                if downloaded:
                    pdf_path = downloaded
                else:
                    self.store.mark_processed(paper["id"], "")
                    processed_count += 1
                    continue

            # Extract text
            if Path(pdf_path).exists():
                self.extractor.extract(
                    pdf_path, self.config.get_path("processed"), paper["id"]
                )

            self.store.mark_processed(paper["id"], pdf_path)
            processed_count += 1

        logger.info(f"Processing complete: {processed_count} papers.")

    def run_analysis(self):
        """Analyze all processed (unanalyzed) papers, with retry for failures."""
        logger.info("Starting analysis run...")

        # Retry previously failed papers (up to 3 attempts)
        retryable = self.store.get_retryable_papers(max_retries=3)
        if retryable:
            logger.info(f"Retrying {len(retryable)} previously failed paper(s)...")
            for paper in retryable:
                self.store.reset_for_retry(paper["id"])

        papers = self.store.get_papers_by_status("processed")
        analyzed_count = 0
        failed_count = 0

        for paper in papers:
            # Skip MDPI publisher
            venue = (paper.get("venue") or "").lower()
            url_lower = (paper.get("url") or "").lower()
            if "mdpi" in venue or "mdpi.com" in url_lower or "10.3390/" in url_lower:
                logger.info(f"  Skipping MDPI: {paper['title'][:60]}")
                self.store.mark_analyzed(paper["id"], "", {
                    "relevance_score": 0, "tags": [],
                    "summary_kr": "", "key_contribution": "",
                    "tldr": "", "lab_relevance": "",
                })
                continue

            try:
                # Load extracted data if available
                extracted = None
                extracted_path = self.config.get_path("processed") / f"{paper['id']}.json"
                if extracted_path.exists():
                    with open(extracted_path, "r", encoding="utf-8") as f:
                        extracted = json.load(f)

                analysis = self.summarizer.analyze(
                    paper, extracted, self.config.topics
                )

                if analysis:
                    summary = analysis.get("summary_kr", "")
                    self.store.mark_analyzed(paper["id"], summary, analysis)

                    # Check for important paper notification
                    score = analysis.get("relevance_score", 0)
                    threshold = self.config.slack.get("importance_threshold", 80)
                    if score >= threshold and self.config.slack.get("notify_on_important"):
                        self._send_slack(
                            f"🔥 *중요 논문 발견!* (관련도: {score})\n"
                            f"*{paper['title']}*\n"
                            f"_{summary[:200]}_"
                        )

                    analyzed_count += 1

            except Exception as e:
                fail_count = (paper.get("fail_count") or 0) + 1
                logger.error(
                    f"Analysis failed for '{paper['title'][:60]}...' "
                    f"(attempt {fail_count}/3): {e}"
                )
                self.store.mark_failed(paper["id"], str(e))
                failed_count += 1

        logger.info(
            f"Analysis complete: {analyzed_count} analyzed, "
            f"{failed_count} failed."
        )

        # Sync to RAG (Qdrant)
        if self.rag_bridge:
            try:
                synced = self.rag_bridge.sync_all_pending(
                    self.store, self.config.get_path("processed")
                )
                if synced:
                    logger.info(f"RAG sync complete: {synced} chunks.")
            except Exception as e:
                logger.error(f"RAG sync failed: {e}")

    def _analyze_papers(self, papers: list):
        """Analyze a specific list of papers (by id). Used after citation chase."""
        if not papers:
            return

        # Build id set for filtering
        paper_ids = {p["id"] for p in papers}
        candidates = self.store.get_papers_by_status("processed")
        to_analyze = [p for p in candidates if p["id"] in paper_ids]

        if not to_analyze:
            logger.info("Citation chase: no new papers need analysis.")
            return

        logger.info(f"Citation chase: analyzing {len(to_analyze)} new papers...")
        analyzed_count = 0

        for paper in to_analyze:
            # Skip MDPI
            venue = (paper.get("venue") or "").lower()
            url = (paper.get("url") or "").lower()
            if "mdpi" in venue or "mdpi.com" in url or "10.3390/" in url:
                logger.info(f"  Skipping MDPI paper: {paper['title'][:60]}")
                self.store.mark_analyzed(paper["id"], "", {"relevance_score": 0, "tags": [], "summary_kr": "", "key_contribution": "", "tldr": "", "lab_relevance": ""})
                continue

            try:
                extracted = None
                extracted_path = self.config.get_path("processed") / f"{paper['id']}.json"
                if extracted_path.exists():
                    with open(extracted_path, "r", encoding="utf-8") as f:
                        extracted = json.load(f)

                analysis = self.summarizer.analyze(paper, extracted, self.config.topics)
                if analysis:
                    summary = analysis.get("summary_kr", "")
                    self.store.mark_analyzed(paper["id"], summary, analysis)
                    analyzed_count += 1

            except Exception as e:
                logger.error(f"  Analysis failed for '{paper['title'][:50]}': {e}")
                self.store.mark_failed(paper["id"], str(e))

        logger.info(f"Citation chase analysis complete: {analyzed_count} papers.")

    def run_digest(self, days: int = 7):
        """Generate and optionally send weekly digest."""
        logger.info("Generating weekly digest...")

        filepath = self.digest.generate(days=days)

        if self.config.slack.get("enabled") and self.config.slack.get("notify_on_digest"):
            summary_text = self.digest.generate_summary_text(days=days)
            self._send_slack(summary_text)

        logger.info(f"Weekly digest saved to: {filepath}")
        return filepath

    def run_daily_digest(self):
        """Generate and optionally send daily digest."""
        logger.info("Generating daily digest...")

        filepath = self.digest.generate_daily()

        if self.config.slack.get("enabled") and self.config.slack.get("notify_on_digest"):
            summary_text = self.digest.generate_daily_summary_text()
            self._send_slack(summary_text)

        logger.info(f"Daily digest saved to: {filepath}")
        return filepath

    def run_survey(self, days: int = 1, min_score: int = 50):
        """Generate survey report of backfill/citation papers."""
        logger.info(f"Generating survey report (last {days} days, score >= {min_score})...")

        filepath = self.digest.generate_survey(days=days, min_score=min_score)

        if self.config.slack.get("enabled"):
            summary_text = self.digest.generate_survey_slack(days=days, min_score=min_score)
            self._send_slack(summary_text)

        logger.info(f"Survey report saved to: {filepath}")
        return filepath

    def run_full(self):
        """Run the full pipeline: collect → process → analyze → chase."""
        self.run_collection()
        self.run_processing()
        self.run_analysis()
        self.run_citation_chase()

    def run_backfill_only(self):
        """Run backfill collection only, then process + analyze."""
        topics = self.config.topics
        try:
            new = self.backfill.collect(topics)
            if new:
                logger.info(f"Backfill: {len(new)} new papers, processing...")
                self.run_processing()
                self.run_analysis()
        except Exception as e:
            logger.error(f"Backfill failed: {e}")

    def run_citation_chase(self):
        """Chase citations for high-relevance papers, then analyze new ones."""
        try:
            new = self.citation_chaser.chase()
            if new:
                logger.info(f"Citation chase: {len(new)} new papers, processing...")
                self.run_processing()
                # Analyze only the newly chased papers — do NOT re-chase
                self._analyze_papers(new)
        except Exception as e:
            logger.error(f"Citation chase failed: {e}")

    def check_inbox_only(self):
        """Quick inbox check — for frequent polling."""
        new = self.inbox.check_inbox()
        if new:
            self.run_processing()
            self.run_analysis()

    def close(self):
        self.store.close()
