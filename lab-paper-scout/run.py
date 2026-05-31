"""
lab-paper-scout: Main entry point
Supports running the full pipeline, individual steps, or the scheduler.
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.pipeline import Pipeline


def setup_logging(log_dir: Path):
    """Configure logging to both console and date-rotating file.

    Log files rotate at midnight, producing one file per day:
        scout_hostname_20260520.log
        scout_hostname_20260521.log
        ...
    Up to 30 days of logs are retained automatically.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    import socket
    from logging.handlers import TimedRotatingFileHandler

    hostname = socket.gethostname().split(".")[0].lower()
    # Base log file — TimedRotatingFileHandler will append date suffixes
    log_file = log_dir / f"scout_{hostname}.log"

    # Custom namer: rename rotated files to scout_hostname_YYYYMMDD.log
    def _log_namer(default_name: str) -> str:
        """Convert 'scout_host.log.2026-05-20' → 'scout_host_20260520.log'."""
        # default_name looks like: /path/to/scout_hostname.log.2026-05-20
        base, _, date_suffix = default_name.rpartition(".log.")
        if date_suffix:
            date_compact = date_suffix.replace("-", "")
            return f"{base}_{date_compact}.log"
        return default_name

    file_handler = TimedRotatingFileHandler(
        str(log_file),
        when="midnight",
        interval=1,
        backupCount=30,    # keep 30 days
        encoding="utf-8",
    )
    file_handler.namer = _log_namer
    file_handler.suffix = "%Y-%m-%d"  # suffix format for rotation

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            file_handler,
        ],
    )

    # Suppress noisy third-party loggers
    for noisy in [
        "httpx",
        "httpcore",
        "google_genai.models",
        "google.ai.generativelanguage",
        "apscheduler.executors.default",
        "apscheduler.scheduler",
    ]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── PID file guard ──────────────────────────────────────────

def _acquire_pid_lock(pid_file: Path, logger) -> bool:
    """Try to acquire a PID lock.  Returns True if acquired, False if
    another daemon is already running."""
    import os

    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            # Check if the process is still alive
            os.kill(old_pid, 0)  # signal 0 = existence check only
            logger.error(
                f"⛔ Another daemon is already running (PID {old_pid}). "
                f"Use 'python run.py reload' to restart it."
            )
            return False
        except (ProcessLookupError, ValueError):
            # Process is dead or PID file is corrupt — safe to reclaim
            logger.warning(f"Stale PID file found (cleaned up): {pid_file}")
        except PermissionError:
            # Process exists but owned by another user
            logger.error(f"⛔ Daemon PID file exists and process is running (permission denied).")
            return False

    # Write our PID
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))
    return True


def _release_pid_lock(pid_file: Path, logger):
    """Remove the PID lock file."""
    try:
        pid_file.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f"Failed to remove PID file: {e}")


def cmd_status(pipeline: Pipeline, args):
    """Show comprehensive system and DB status dashboard."""
    import os
    config = pipeline.config
    W = 60  # dashboard width

    def header(title):
        print(f"\n{'━'*W}")
        print(f"  {title}")
        print(f"{'━'*W}")

    def row(label, value, indent=2):
        print(f"{' '*indent}{label:<24} {value}")

    print(f"\n{'━'*W}")
    print(f"  📊 lab-paper-scout 현황 대시보드")
    print(f"{'━'*W}")

    # ── 1. Daemon status ──
    header("🔧 데몬 상태")
    pid_file = config.project_root / "data" / ".daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            row("데몬", f"✅ 실행 중 (PID {pid})")
        except (ProcessLookupError, ValueError):
            row("데몬", "⚠️  PID 파일 있지만 프로세스 없음 (stale)")
        except PermissionError:
            row("데몬", f"✅ 실행 중 (PID, permission denied)")
    else:
        row("데몬", "❌ 실행되지 않음")

    # ── 2. DB stats ──
    header("📦 데이터베이스")
    stats = pipeline.store.get_stats()
    row("DB 파일", f"{config.project_root / 'data' / 'paper_scout.db'}")
    row("DB 크기", f"{stats.get('db_size_mb', 0):.1f} MB")
    row("총 논문 수", f"{stats['total']}편")
    row("오늘 수집", f"{stats['today_collected']}편")
    row("오늘 분석", f"{stats['today_analyzed']}편")

    # Status breakdown
    header("📋 상태별")
    for status, cnt in stats["by_status"].items():
        icon = {"analyzed": "✅", "collected": "📥", "processed": "⚙️", "failed": "❌"}.get(status, "❓")
        row(f"{icon} {status}", f"{cnt}편")

    # Source breakdown
    header("📡 소스별")
    source_icons = {
        "arxiv": "📄", "semantic_scholar": "🔬",
        "manual_inbox": "📂", "backfill": "📚",
        "citation_chase": "🔗",
    }
    for source, cnt in stats["by_source"].items():
        icon = source_icons.get(source, "❓")
        row(f"{icon} {source}", f"{cnt}편")

    # Relevance distribution
    header("📊 관련도 분포")
    dist = stats.get("score_dist", {})
    for label in ["90+", "70-89", "50-69", "<50"]:
        cnt = dist.get(label, 0)
        bar = "█" * min(cnt, 40)
        row(f"{label:>6}", f"{cnt:>4}편  {bar}")

    # Failed papers
    if stats["failed"] > 0:
        print(f"\n  ⚠️  실패한 논문 {stats['failed']}편 — 'python run.py analyze'로 재시도 가능")

    # Timestamps
    header("🕐 최근 활동")
    lc = stats.get("latest_collected")
    la = stats.get("latest_analyzed")
    row("마지막 수집", lc[:19] if lc else "없음")
    row("마지막 분석", la[:19] if la else "없음")

    # ── 3. Inbox / Archive ──
    header("📂 파일 현황")
    inbox_dir = config.project_root / "data" / "inbox"
    archive_dir = config.project_root / "data" / "archive"
    inbox_pdfs = list(inbox_dir.glob("*.pdf")) if inbox_dir.exists() else []
    archive_pdfs = list(archive_dir.glob("*.pdf")) if archive_dir.exists() else []
    row("인박스 대기", f"{len(inbox_pdfs)}건")
    if inbox_pdfs:
        for f in inbox_pdfs[:5]:
            print(f"      📄 {f.name}")
        if len(inbox_pdfs) > 5:
            print(f"      ... 외 {len(inbox_pdfs)-5}건")
    row("아카이브 보관", f"{len(archive_pdfs)}건")

    # ── 4. Reports ──
    header("📝 리포트")
    reports_dir = config.project_root / "data" / "reports"
    if reports_dir.exists():
        reports = sorted(reports_dir.glob("*.md"), reverse=True)
        for r in reports[:5]:
            size = r.stat().st_size / 1024
            row(r.name, f"{size:.0f} KB")
        if not reports:
            row("리포트", "없음")
    else:
        row("리포트", "디렉토리 없음")

    # ── 5. Logs ──
    header("📜 로그")
    logs_dir = config.project_root / "logs"
    if logs_dir.exists():
        logs = sorted(logs_dir.glob("scout_*.log"), reverse=True)
        for lf in logs[:3]:
            size = lf.stat().st_size / 1024
            row(lf.name, f"{size:.0f} KB")
        if not logs:
            row("로그", "없음")

    print(f"\n{'━'*W}\n")


def cmd_collect(pipeline: Pipeline, args):
    """Run collection only."""
    pipeline.run_collection()


def cmd_process(pipeline: Pipeline, args):
    """Run processing only."""
    pipeline.run_processing()


def cmd_analyze(pipeline: Pipeline, args):
    """Run analysis only."""
    pipeline.run_analysis()


def cmd_digest(pipeline: Pipeline, args):
    """Generate weekly digest report."""
    days = args.days if hasattr(args, "days") else 7
    filepath = pipeline.run_digest(days=days)
    print(f"Weekly digest saved to: {filepath}")


def cmd_daily(pipeline: Pipeline, args):
    """Generate daily digest report."""
    filepath = pipeline.run_daily_digest()
    print(f"Daily digest saved to: {filepath}")


def cmd_survey(pipeline: Pipeline, args):
    """Generate survey report of backfill/citation papers."""
    filepath = pipeline.run_survey(days=args.days, min_score=args.min_score)
    print(f"Survey report saved to: {filepath}")


def cmd_run(pipeline: Pipeline, args):
    """Run full pipeline: collect → process → analyze."""
    pipeline.run_full()


def cmd_inbox(pipeline: Pipeline, args):
    """Check inbox for new PDFs and process them."""
    pipeline.check_inbox_only()


def cmd_inbox_list(pipeline: Pipeline, args):
    """List all inbox papers currently stored in the DB."""
    papers = pipeline.store.get_inbox_papers()
    if not papers:
        print("인박스에 등록된 논문이 없습니다.")
        return

    print(f"\n{'─'*80}")
    print(f"  인박스 논문 목록 ({len(papers)}편)")
    print(f"{'─'*80}")
    for p in papers:
        score = p.get('relevance_score') or 0
        status = p.get('status', '?')
        date = (p.get('collected_at') or '')[:10]
        print(f"  ID    : {p['id']}")
        print(f"  제목  : {p['title']}")
        print(f"  상태  : {status}  |  관련도: {score:.0f}  |  수집일: {date}")
        print(f"{'─'*80}")
    print(f"\n수정 방법: python run.py fix-inbox <paper_id> \"올바른 제목\"\n")


def cmd_fix_inbox(pipeline: Pipeline, args):
    """Fix a manually ingested paper's title (and recalculate its paper_id)."""
    logger = logging.getLogger(__name__)
    paper_id = args.paper_id
    new_title = args.new_title.strip()

    if not new_title:
        print("❌ 제목이 비어있습니다.")
        return

    # Show current state
    paper = pipeline.store.get_paper_by_id(paper_id)
    if paper is None:
        print(f"❌ paper_id를 찾을 수 없습니다: {paper_id}")
        print("   'python run.py inbox-list' 로 현재 ID를 확인하세요.")
        return

    old_title = paper['title']
    print(f"\n변경 전: {old_title}")
    print(f"변경 후: {new_title}")
    confirm = input("변경하시겠습니까? [y/N] ").strip().lower()
    if confirm != 'y':
        print("취소되었습니다.")
        return

    try:
        new_id = pipeline.store.fix_paper_title(paper_id, new_title)
        print(f"\n✅ 업데이트 완료")
        print(f"   paper_id: {paper_id} → {new_id}")
        print(f"   title   : {old_title}")
        print(f"           → {new_title}")
        if paper.get('status') == 'analyzed':
            print(f"\n⚠️  이 논문은 이미 분석되었습니다.")
            print(f"   제목이 수정되었지만 analysis_json 내용은 그대로입니다.")
            print(f"   재분석하려면: python run.py analyze")
        logger.info(f"fix-inbox: '{old_title}' → '{new_title}' (id: {paper_id} → {new_id})")
    except ValueError as e:
        print(f"❌ 오류: {e}")


def cmd_backfill(pipeline: Pipeline, args):
    """Run one backfill batch (older papers)."""
    pipeline.run_backfill_only()


def cmd_chase(pipeline: Pipeline, args):
    """Chase citations for high-relevance papers."""
    pipeline.run_citation_chase()


def cmd_smoketest(pipeline: Pipeline, args):
    """Run a full daemon cycle simulation using an isolated test DB."""
    import concurrent.futures
    import shutil
    logger = logging.getLogger(__name__)

    # ── Create isolated test pipeline ──
    test_db = "data/.test_scout.db"
    test_reports = "data/reports/_test"
    test_config = Config(args.config)
    test_config.override_paths(db=test_db, reports=test_reports)
    test_pipeline = Pipeline(test_config)
    test_pipeline.slack_prefix = "[🧪 TEST] "

    logger.info("=" * 60)
    logger.info("SMOKE TEST: isolated pipeline (test DB, Slack marked [🧪 TEST])")
    logger.info("=" * 60)

    # Each step with its own timeout (seconds)
    tests = [
        ("Collect",      test_pipeline.run_collection,      600),   # 10분
        ("Process",      test_pipeline.run_processing,       120),   # 2분
        ("Analyze",      test_pipeline.run_analysis,        1800),  # 30분
        ("Chase",        test_pipeline.run_citation_chase,   600),  # 10분
        ("Daily Digest", test_pipeline.run_daily_digest,     120),  # 2분
    ]

    results = []
    for name, func, timeout in tests:
        logger.info(f"\n--- {name} ---")
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                future.result(timeout=timeout)
                results.append((name, "✅ OK"))
                logger.info(f"{name}: ✅ OK")
            except concurrent.futures.TimeoutError:
                results.append((name, f"❌ TIMEOUT (>{timeout}s)"))
                logger.error(f"{name}: ❌ TIMEOUT — 허용시간 {timeout}초 초과")
            except Exception as e:
                err_msg = str(e) or type(e).__name__
                results.append((name, f"❌ FAIL: {err_msg}"))
                logger.error(f"{name}: ❌ FAIL: {err_msg}", exc_info=True)

    logger.info("\n" + "=" * 60)
    logger.info("SMOKE TEST RESULTS:")
    for name, status in results:
        logger.info(f"  {name}: {status}")
    logger.info("=" * 60)

    print("\n🧪 Smoke Test Results:")
    for name, status in results:
        print(f"  {name}: {status}")

    # ── Cleanup test artifacts ──
    test_pipeline.close()
    test_db_path = test_config.get_path("db")
    test_reports_path = test_config.get_path("reports")
    if test_db_path.exists():
        test_db_path.unlink()
        logger.info(f"🗑️ Test DB deleted: {test_db_path}")
    if test_reports_path.exists():
        shutil.rmtree(test_reports_path)
        logger.info(f"🗑️ Test reports deleted: {test_reports_path}")


def cmd_daemon(pipeline: Pipeline, args):
    """Run as a background daemon with scheduled jobs."""
    import os
    from apscheduler.schedulers.blocking import BlockingScheduler

    config = pipeline.config
    logger = logging.getLogger(__name__)

    # ── PID file guard: prevent duplicate daemons ────────────
    pid_file = config.project_root / "data" / ".daemon.pid"
    if not _acquire_pid_lock(pid_file, logger):
        sys.exit(1)

    scheduler = BlockingScheduler()

    # Restart marker path
    restart_marker = config.project_root / "data" / ".restart"

    def _check_restart():
        """Check for restart marker file — exit gracefully if found."""
        if restart_marker.exists():
            restart_marker.unlink()
            logger.info("🔄 Restart marker detected — shutting down for reload...")
            scheduler.shutdown(wait=False)

    def _collect_and_analyze():
        """Collect + process + analyze (no chase, no backfill)."""
        try:
            pipeline.run_collection()
            pipeline.run_processing()
            pipeline.run_analysis()
        except Exception as e:
            logger.error(f"Collection cycle failed: {e}")

    # Restart marker check (every 30 seconds)
    scheduler.add_job(
        _check_restart,
        "interval",
        seconds=30,
        id="restart_check",
        name="Restart marker check",
    )

    # Collect + Analyze every N hours (default 8h)
    collect_interval = config.schedule.get("collection_interval_hours", 8)
    scheduler.add_job(
        _collect_and_analyze,
        "interval",
        hours=collect_interval,
        id="collect_cycle",
        name=f"Collect+Analyze (every {collect_interval}h)",
    )

    # Citation chase (daily, separate time slot)
    chase_hour = config.schedule.get("chase_hour", 3)
    scheduler.add_job(
        pipeline.run_citation_chase,
        "cron",
        hour=chase_hour,
        id="citation_chase",
        name=f"Citation chase (daily {chase_hour}:00)",
    )

    # Backfill (daily, separate time slot)
    backfill_hour = config.schedule.get("backfill_hour", 4)
    scheduler.add_job(
        pipeline.run_backfill_only,
        "cron",
        hour=backfill_hour,
        id="backfill",
        name=f"Backfill (daily {backfill_hour}:00)",
    )

    # Daily digest
    daily_hour = config.schedule.get("daily_digest_hour", 8)
    scheduler.add_job(
        pipeline.run_daily_digest,
        "cron",
        hour=daily_hour,
        id="daily_digest",
        name=f"Daily digest ({daily_hour}:00)",
    )

    # Weekly digest
    weekly_day = config.schedule.get("weekly_digest_day", "monday")
    weekly_hour = config.schedule.get("weekly_digest_hour", 7)
    scheduler.add_job(
        lambda: pipeline.run_digest(days=7),
        "cron",
        day_of_week=weekly_day[:3].lower(),
        hour=weekly_hour,
        id="weekly_digest",
        name=f"Weekly digest ({weekly_day} {weekly_hour}:00)",
    )

    logger.info("=" * 60)
    logger.info("lab-paper-scout daemon started")
    logger.info(f"  PID: {os.getpid()} (lock: {pid_file})")
    logger.info(f"  Collect+Analyze: every {collect_interval}h")
    logger.info(f"  Citation chase: daily {chase_hour}:00")
    logger.info(f"  Backfill: daily {backfill_hour}:00")
    logger.info(f"  Daily digest: {daily_hour}:00")
    logger.info(f"  Weekly digest: {weekly_day} {weekly_hour}:00")
    logger.info(f"  Restart watch: data/.restart (every 30s)")
    logger.info("=" * 60)

    # Run initial collection on start
    logger.info("Running initial collection+analyze...")
    try:
        _collect_and_analyze()
    except Exception as e:
        logger.error(f"Initial run failed: {e}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Daemon stopped.")
    finally:
        _release_pid_lock(pid_file, logger)
        pipeline.close()
        logger.info("Daemon exited — launchd will restart if configured.")


def cmd_reload(pipeline: Pipeline, args):
    """Signal the running daemon to restart by creating a marker file."""
    marker = pipeline.config.project_root / "data" / ".restart"
    marker.touch()
    print(f"✅ Restart marker created: {marker}")
    print("   The daemon will restart within 30 seconds.")


def _create_backup(data_dir: Path) -> Path | None:
    """Back up DB and backfill state to data/backups/. Returns backup dir."""
    import shutil
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = data_dir / "backups" / ts
    backup_dir.mkdir(parents=True, exist_ok=True)

    backed_up = []
    for name in ["paper_scout.db", "backfill_state.json"]:
        src = data_dir / name
        if src.exists():
            shutil.copy2(src, backup_dir / name)
            backed_up.append(name)

    # Also back up reports
    reports_dir = data_dir / "reports"
    if reports_dir.exists() and any(reports_dir.iterdir()):
        shutil.copytree(reports_dir, backup_dir / "reports")
        backed_up.append("reports/")

    if backed_up:
        print(f"📦 백업 완료: {backup_dir}")
        for f in backed_up:
            print(f"   - {f}")
        return backup_dir
    else:
        print("백업할 데이터가 없습니다.")
        return None


def cmd_backup(pipeline: Pipeline, args):
    """Create a backup of current data."""
    data_dir = pipeline.config.project_root / "data"
    _create_backup(data_dir)


def cmd_reset(pipeline: Pipeline, args):
    """Reset all collected data for a fresh start (with auto-backup)."""
    import shutil
    data_dir = pipeline.config.project_root / "data"

    targets = [
        ("DB", data_dir / "paper_scout.db"),
        ("백필 상태", data_dir / "backfill_state.json"),
    ]
    dirs = [
        ("처리 파일", data_dir / "processed"),
        ("리포트", data_dir / "reports"),
    ]

    print("⚠️  다음 데이터를 삭제합니다:")
    for name, path in targets:
        print(f"  - {name}: {path}")
    for name, path in dirs:
        print(f"  - {name}: {path}")

    confirm = input("\n정말 초기화하시겠습니까? (yes/no): ")
    if confirm.strip().lower() != "yes":
        print("취소되었습니다.")
        return

    # Auto-backup before reset
    print("\n--- 자동 백업 ---")
    _create_backup(data_dir)
    print()

    pipeline.close()

    for name, path in targets:
        if path.exists():
            path.unlink()
            print(f"  🗑️  {name} 삭제됨")
    for name, path in dirs:
        if path.exists():
            shutil.rmtree(path)
            path.mkdir(parents=True)
            print(f"  🗑️  {name} 초기화됨")

    print("\n✅ 데이터 초기화 완료. python run.py run 으로 새로 수집을 시작하세요.")


def main():
    parser = argparse.ArgumentParser(
        description="lab-paper-scout: Automated research paper collection & analysis"
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to config.yaml (default: config/config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Sub-commands
    subparsers.add_parser("status", help="Show system and DB status dashboard")
    subparsers.add_parser("collect", help="Run collection only")
    subparsers.add_parser("process", help="Run processing only")
    subparsers.add_parser("analyze", help="Run analysis only")

    digest_parser = subparsers.add_parser("digest", help="Generate weekly digest report")
    digest_parser.add_argument("--days", type=int, default=7, help="Days to cover")

    subparsers.add_parser("daily", help="Generate daily digest report")

    survey_parser = subparsers.add_parser("survey", help="Generate survey report (backfill + citation chase papers)")
    survey_parser.add_argument("--days", type=int, default=1, help="Days to look back (default: 1)")
    survey_parser.add_argument("--min-score", type=int, default=50, help="Minimum relevance score (default: 50)")
    subparsers.add_parser("run", help="Run full pipeline (collect+process+analyze)")
    subparsers.add_parser("inbox", help="Check inbox and process new PDFs")
    subparsers.add_parser("inbox-list", help="List all inbox papers stored in DB")
    fix_inbox_parser = subparsers.add_parser(
        "fix-inbox", help="Fix a manually ingested paper's title in DB"
    )
    fix_inbox_parser.add_argument("paper_id", help="paper_id to fix (from inbox-list)")
    fix_inbox_parser.add_argument("new_title", help="Correct title to set")
    subparsers.add_parser("backfill", help="Run one backfill batch (older papers)")
    subparsers.add_parser("chase", help="Chase citations for high-relevance papers")
    subparsers.add_parser("daemon", help="Run as background daemon with scheduler")
    subparsers.add_parser("reload", help="Signal running daemon to restart (creates .restart marker)")
    subparsers.add_parser("smoketest", help="Run full daemon cycle simulation (thread-safe test)")
    subparsers.add_parser("backup", help="Create a backup of current data")
    subparsers.add_parser("reset", help="Reset all data with auto-backup")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize
    config = Config(args.config)
    setup_logging(config.get_path("logs"))
    pipeline = Pipeline(config)

    # Dispatch
    commands = {
        "status": cmd_status,
        "collect": cmd_collect,
        "process": cmd_process,
        "analyze": cmd_analyze,
        "digest": cmd_digest,
        "daily": cmd_daily,
        "survey": cmd_survey,
        "run": cmd_run,
        "inbox": cmd_inbox,
        "inbox-list": cmd_inbox_list,
        "fix-inbox": cmd_fix_inbox,
        "backfill": cmd_backfill,
        "chase": cmd_chase,
        "daemon": cmd_daemon,
        "reload": cmd_reload,
        "smoketest": cmd_smoketest,
        "backup": cmd_backup,
        "reset": cmd_reset,
    }

    # Warn if daemon is running and user tries a write command manually
    write_commands = {"collect", "process", "analyze", "run", "inbox", "backfill", "chase"}
    if args.command in write_commands:
        pid_file = config.project_root / "data" / ".daemon.pid"
        if pid_file.exists():
            try:
                import os
                old_pid = int(pid_file.read_text().strip())
                os.kill(old_pid, 0)
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"⚠️  데몬이 실행 중입니다 (PID {old_pid}). "
                    f"DB 동시 접근으로 lock 에러가 발생할 수 있습니다."
                )
            except (ProcessLookupError, ValueError, PermissionError):
                pass

    try:
        commands[args.command](pipeline, args)
    finally:
        if args.command != "daemon":
            pipeline.close()


if __name__ == "__main__":
    main()
