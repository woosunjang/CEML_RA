# Handoff

**Updated:** 2026-06-10 KST
**Status:** Same-folder Stage 0 branch is clean and rebuilding from `main`.

This handoff intentionally discards the old autonomy-pulse momentum as an
operating default. Earlier mission IDs, Sprint Executor next actions, proposal
backlogs, generated/ops artifacts, and long runtime narratives are historical
reference only.

## Current Direction

Continue from the current branch:

```text
codex/ceml-ra-stage0-main
```

This branch was created from `main` in the existing CEML_RA folder, because the
user will disable Dropbox sync directly and wants to continue in this same
directory rather than create an external clone/worktree.

Stage 0 comes first:

- Dropbox/GitHub separation
- repository cleanup
- artifact/runtime data boundary setup
- old autonomy-pulse surface audit

Stage 1 applies the separate "CEML_RA 2-Week Research-Value Development Cycle"
plan only after Stage 0 is complete.

## Read First

1. `AGENTS.md`
2. `docs/ceml-ra-main-rebuild-development-goal-2026-06-10.md`
3. `.agents/context/TASK_LOG.md`
4. `git status --short --branch`

## Important Local State

- The old branch `codex/ceml-ra-reset-baseline` remains preserved.
- The old branch had an unpushed local commit:
  `4fd6f46 feat: route research and specialist artifacts`.
- That commit should not be pushed or reused unless explicitly re-approved.
- The previous dirty state was saved in git stash:
  `stage0-context-reset-before-main-switch`.
- A full same-folder snapshot was archived before cleanup:
  `/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/source_archives/CEML_RA_full_with_gitdir_20260610_220548.tar.gz`.
  It includes both `CEML_RA/` and external `git_repo/CEML_RA.git/` metadata.
- The old untracked/runtime leftovers were then removed from the working folder.
  Current Stage 0 source should remain clean and main-derived.
- In-progress Stage 0 work now adds minimal artifact-root support:
  `CEML_RA_ARTIFACTS_DIR`, `ARTIFACTS_DIR`, generated fallback, docs, and tests.

## Guardrails

- Do not restart services during planning.
- Do not mutate live DB/KG/RAG/Scout state during planning.
- Do not run Sprint Executor or active mission next-actions by default.
- Do not push without explicit approval.
- Do not treat read-only observation as research progress.
