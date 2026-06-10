# Handoff

**Updated:** 2026-06-11 KST
**Status:** `main` is the clean ground for the 2-week research-value cycle.

## Current Ground

```text
main
```

The repo now uses an internal `.git/` directory. The user may disable Dropbox
sync for the source folder:

```text
/Users/woosun/Dropbox/Dev/CEML_RA
```

Keep this artifact root Dropbox-synced:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts
```

## Read First

1. `AGENTS.md`
2. `docs/ceml-ra-2week-research-value-cycle.md`
3. `docs/artifact-runtime-boundary.md`
4. `.agents/context/TASK_LOG.md`
5. `git status --short --branch`

## Live Direction

Use the 2-week research-value cycle as the canonical product plan. The next
product step is:

```text
Days 1-2: Research Question Factory
```

Start by generating fresh, non-template research questions for:

- `materials_ontology_kg`
- `rare_earth_magnets`

Do not begin with internal autonomy machinery, old audit findings, old schedule
plans, or code implementation slices unless the user explicitly redirects.

## Sealed Historical Material

Old branches, old stashes, old autonomy-pulse artifacts, old schedule plans,
old generated/ops reports, and old reset/audit narratives are historical only.
They should not be read or used as default context.

The old local branches and preserved stash were deleted after explicit user
approval. Historical material remains only in the full archive and Git history.

## Guardrails

- Do not push without explicit approval.
- Do not delete local branches or stashes without explicit approval.
- Do not mutate live DB/KG/RAG/Scout state during planning.
- Do not restart services during planning or cleanup.
- Do not run Sprint Executor, active mission next-actions, or backlog mutation
  commands by default.
- Do not count read-only observation as research progress.
