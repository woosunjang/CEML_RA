# Task Log

## 2026-06-11 — Purged old live context from the repo

**Status:** In progress in this commit.

**Why:** The main-derived reset was still carrying old planning and audit
surfaces that made Codex drift back toward prior autonomy-pulse development
habits. The user approved purging live context items 1-6 while leaving local
branch/stash deletion for a separate preview and approval.

**Scope approved now:**

1. Remove old tracked schedule plans under `development/schedule_plan/`.
2. Remove `docs/old-surface-audit-2026-06-10.md`.
3. Remove `docs/stage0-next-chat-prompt-2026-06-10.md`.
4. Rewrite `HANDOFF.md` and this `TASK_LOG.md` as short current-state files.
5. Shrink the main rebuild goal into current source/artifact boundary and next
   cycle entry guidance.
6. Add a canonical 2-week research-value cycle document.

**Not yet approved:** Deleting local old branches or the preserved stash. A
preview should be shown before any branch or stash deletion.

**Canonical next product step:**

```text
Research Question Factory for materials_ontology_kg and rare_earth_magnets
```

## 2026-06-10 — Completed source/artifact separation

**Status:** Complete.

Completed Stage 0 infrastructure:

- Source folder cleaned and reset onto `codex/ceml-ra-stage0-main`.
- Full pre-cleanup archive preserved at:

  ```text
  /Users/woosun/Dropbox/Dev/CEML/RA_artifacts/source_archives/CEML_RA_full_with_gitdir_20260610_220548.tar.gz
  ```

- Minimal artifact-root support committed:
  `CEML_RA_ARTIFACTS_DIR`, `ARTIFACTS_DIR`, generated fallback, docs, and
  focused tests.
- Explicit snapshot export helper committed.
- Git metadata moved into the source folder as internal `.git/`.
- External gitdir path removed.
- `core.worktree` absolute-path setting removed.
- Git GC warning resolved.

**Operational note:** The user may disable Dropbox sync for
`/Users/woosun/Dropbox/Dev/CEML_RA`. Keep
`/Users/woosun/Dropbox/Dev/CEML/RA_artifacts` Dropbox-synced.
