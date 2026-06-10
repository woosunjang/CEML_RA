"""Tests for explicit Stage 0 portable snapshot exports."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ORCH_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ORCH_ROOT))

from integrations.export_manifest import (  # noqa: E402
    execute_snapshot_export,
    latest_manifest_records,
    plan_snapshot_export,
    sha256_file,
)


class ExportManifestTests(unittest.TestCase):
    def test_plan_preview_does_not_write_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "scout.jsonl"
            source.write_text('{"title": "paper"}\n', encoding="utf-8")
            artifacts = root / "artifacts"

            plan = plan_snapshot_export(
                source,
                kind="scout_jsonl",
                label="Daily Scout Export",
                artifacts_dir=artifacts,
                created_at="2026-06-10T12:00:00Z",
            )
            preview = plan.preview_record()

            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["label"], "Daily_Scout_Export")
            self.assertFalse(plan.destination_path.exists())
            self.assertFalse(plan.manifest_path.exists())
            self.assertIn("20260610T120000Z", plan.destination_path.name)

    def test_execute_copies_file_and_appends_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paper_scout.db"
            source.write_bytes(b"sqlite bytes")
            artifacts = root / "artifacts"

            plan = plan_snapshot_export(
                source,
                kind="scout_sqlite",
                label="scout-db",
                artifacts_dir=artifacts,
                created_at="2026-06-10T12:00:00Z",
            )
            record = execute_snapshot_export(plan, actor="test", note="unit test")

            self.assertTrue(plan.destination_path.exists())
            self.assertEqual(plan.destination_path.read_bytes(), b"sqlite bytes")
            self.assertTrue(plan.manifest_path.exists())
            self.assertEqual(record["actor"], "test")
            self.assertEqual(record["note"], "unit test")
            self.assertEqual(record["file"]["sha256"], sha256_file(source))
            self.assertEqual(record["file"]["destination_path"], str(plan.destination_path))

            records = latest_manifest_records(plan.manifest_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["kind"], "scout_sqlite")

    def test_execute_can_include_sqlite_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paper_scout.db"
            wal = root / "paper_scout.db-wal"
            shm = root / "paper_scout.db-shm"
            source.write_bytes(b"db")
            wal.write_bytes(b"wal")
            shm.write_bytes(b"shm")

            plan = plan_snapshot_export(
                source,
                kind="scout_sqlite",
                artifacts_dir=root / "artifacts",
                include_sidecars=True,
                created_at="2026-06-10T12:00:00Z",
            )
            record = execute_snapshot_export(plan)

            self.assertEqual(len(record["sidecars"]), 2)
            self.assertTrue(Path(f"{plan.destination_path}-wal").exists())
            self.assertTrue(Path(f"{plan.destination_path}-shm").exists())

    def test_cli_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "export.jsonl"
            artifacts = root / "artifacts"
            source.write_text("{}\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ORCH_ROOT / "tools" / "export_snapshot.py"),
                    "--source",
                    str(source),
                    "--kind",
                    "scout_jsonl",
                    "--artifacts-dir",
                    str(artifacts),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertFalse((artifacts / "manifests" / "knowledge_snapshots.jsonl").exists())
            self.assertFalse((artifacts / "snapshots").exists())
