# Stage 0 Next Chat Prompt

Use this prompt to start the next CEML_RA Stage 0 chat.

```text
We are continuing CEML_RA Stage 0 in the same local folder:
/Users/woosun/Dropbox/Dev/CEML_RA

Current branch should be:
codex/ceml-ra-stage0-main

This branch was created from main. The user will disable Dropbox sync for the
source folder manually, so do not create an external clone or worktree unless
explicitly asked.

Short-term Stage 0 goal:
1. Complete Dropbox/GitHub separation for code vs artifacts.
2. Keep GitHub as source of truth for source code.
3. Keep durable artifacts and portable knowledge snapshots under:
   /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
4. Keep live DBs, logs, caches, command queues, and service state host-local.
5. Clean old branch leftovers from the same folder only after preview and
   explicit approval.

Read first:
1. AGENTS.md
2. .agents/context/HANDOFF.md
3. .agents/context/TASK_LOG.md
4. docs/ceml-ra-main-rebuild-development-goal-2026-06-10.md
5. git status --short --branch

Important current state:
- The old codex/ceml-ra-reset-baseline branch is preserved.
- Its unpushed local commit 4fd6f46 should not be pushed or used unless
  explicitly re-approved.
- Previous dirty state was preserved in git stash:
  stage0-context-reset-before-main-switch
- Because we switched from an old large branch to main in the same folder, many
  files now appear as untracked leftovers. Preview cleanup with:
  git clean -fd -n
  Do not run destructive cleanup without explicit approval.

Do not mutate runtime services, DB/KG/RAG/Scout state, launchd, or command
queues during Stage 0.

First useful action:
- Commit the staged Stage 0 context files if approved.
- Then review the git clean dry-run output and decide which untracked leftovers
  to delete, keep, or migrate.
```
