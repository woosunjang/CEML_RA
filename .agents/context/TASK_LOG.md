# Task Log

## 2026-06-10 — Added explicit portable snapshot export helper

**Status:** Export helper implemented locally and not yet committed.

**What changed:** Added a narrow Stage 0 export lane for portable knowledge
snapshots:

- `lab-orchestrator/integrations/export_manifest.py` plans and executes
  explicit one-file exports into `ARTIFACTS_DIR/snapshots/<kind>/`.
- `lab-orchestrator/tools/export_snapshot.py` exposes the helper as a CLI.
- The CLI is dry-run by default; `--execute` is required before any file is
  copied or any manifest row is appended.
- Executed exports append JSONL rows to
  `ARTIFACTS_DIR/manifests/knowledge_snapshots.jsonl`.
- SQLite `-wal`/`-shm` sidecars are copied only when `--include-sidecars` is
  provided.
- Directories are rejected so live runtime trees cannot be swept into Dropbox
  by accident.

**Verification:**

```text
python3 -m py_compile lab-orchestrator/integrations/export_manifest.py lab-orchestrator/tools/export_snapshot.py lab-orchestrator/tests/test_export_manifest.py
python3 -m unittest discover -s lab-orchestrator/tests -p 'test_export_manifest.py'
python3 -m unittest discover -s lab-orchestrator/tests -p 'test_config_paths.py'
python3 -m unittest discover -s lab-orchestrator/tests -p 'test_knowledge_brief.py'
git diff --check
```

All focused checks passed. `test_knowledge_brief.py` still emits the existing
LibreSSL/urllib3 warning and expected disk-I/O fallback warning.

**Next recommended actions for Stage 0:**

1. Commit the export helper.
2. Add a small old-surface audit index before selectively reusing any
   autonomy-pulse writer/report/probe code.
3. Keep actual live DB/Qdrant/Neo4j exports manual and explicit.

## 2026-06-10 — Archived old folder state and added Stage 0 artifact boundary

**Status:** Source folder cleanup completed; minimal artifact-root contract is
implemented locally and not yet committed.

**What changed:** Before deleting old same-folder leftovers, the full current
folder state was archived at:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/source_archives/CEML_RA_full_with_gitdir_20260610_220548.tar.gz
```

The archive includes both the `CEML_RA/` working folder and external
`git_repo/CEML_RA.git/` metadata. It passed gzip integrity checking and a small
member-list spot check.

After the archive was verified, old untracked/runtime leftovers were removed
from the working folder. `git status --short --branch` returned clean on
`codex/ceml-ra-stage0-main`.

**Current Stage 0 implementation:** Minimal artifact-root support is being
reintroduced without carrying forward the old broad writer migration:

- `CEML_RA_ARTIFACTS_DIR` is honored by orchestrator config.
- `ARTIFACTS_DIR` falls back to in-repo `generated/` when the env var is unset.
- Existing `GENERATED_*` constants now alias the artifact root subdirectories.
- Scout Markdown reports honor `CEML_RA_ARTIFACTS_DIR/reports`; Scout live DB
  and processed state remain host-local.
- `.gitignore` now covers more DB/cache/log/queue/conflict-copy runtime
  surfaces.
- `docs/artifact-runtime-boundary.md` documents source vs durable artifact vs
  live runtime state.

**Verification:**

```text
python3 -m py_compile lab-orchestrator/orchestrator/config.py lab-paper-scout/src/config.py lab-orchestrator/tests/test_config_paths.py
python3 -m unittest discover -s lab-orchestrator/tests -p 'test_config_paths.py'
python3 -m unittest discover -s lab-orchestrator/tests -p 'test_knowledge_brief.py'
```

All focused checks passed. `test_knowledge_brief.py` emitted an existing
LibreSSL/urllib3 warning and an expected disk-I/O fallback warning.

**Next recommended actions for Stage 0:**

1. Review and commit the minimal artifact-boundary changes.
2. Decide whether to create a small export-manifest command for portable
   knowledge snapshots.
3. Audit old read-only writer/report/probe surfaces only after this boundary is
   committed.

## 2026-06-10 — Created same-folder Stage 0 branch from main

**Status:** Stage 0 branch started; cleanup not yet committed.

**What changed:** The current working folder was switched from
`codex/ceml-ra-reset-baseline` to a new `main`-derived branch:

```text
codex/ceml-ra-stage0-main
```

The user explicitly chose to continue in the same folder and disable Dropbox
sync manually, instead of creating an external clone or worktree.

**Why:** New development should not inherit the old autonomy-pulse branch as
its baseline. Stage 0 should first complete Dropbox/GitHub separation,
repository cleanup, and source/artifact/runtime-data boundary setup. The
separate two-week research-value feature plan should start only after Stage 0.

**Preserved state:** Before switching branches, the prior dirty state was saved
in git stash:

```text
stage0-context-reset-before-main-switch
```

The old `codex/ceml-ra-reset-baseline` branch remains preserved, including the
unpushed local commit:

```text
4fd6f46 feat: route research and specialist artifacts
```

Do not push or build on that commit unless explicitly re-approved.

**Observed Stage 0 issue:** Because `main` is much smaller than the old branch,
many old-branch files now appear as untracked leftovers in the same folder.
These should be cleaned only after a dry-run preview and explicit approval.

**Next recommended actions for Stage 0:**

1. Restore and commit the minimal Stage 0 context files.
2. Preview untracked leftovers with `git clean -fd -n`.
3. Decide which untracked files to delete, keep, or move.
4. Add `.gitignore` coverage for runtime artifacts, DBs, logs, caches, command
   queues, and conflict copies.
5. Reimplement minimal `CEML_RA_ARTIFACTS_DIR` / `ARTIFACTS_DIR` support from
   `main`.
6. Add focused path-resolution tests.

**Guardrails:**

- Do not mutate runtime services, DB/KG/RAG/Scout state, launchd, or command
  queues during Stage 0.
- Do not use old active mission IDs, proposal backlog pressure, or Sprint
  Executor next-actions as current work.
- Do not count read-only observation as product progress.
- Do not push without explicit approval.
