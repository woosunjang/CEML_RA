# Task Log

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
