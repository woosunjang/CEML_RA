# Handoff

**Updated:** 2026-06-11 KST
**Status:** Stage 0 source/artifact separation is complete; old live context is
being purged so the next work starts from the 2-week research-value cycle.

## Current Branch

```text
codex/ceml-ra-stage0-main
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

Local old branches and stash still exist for now and require a separate explicit
approval before deletion.

## Guardrails

- Do not push without explicit approval.
- Do not delete local branches or stashes without explicit approval.
- Do not mutate live DB/KG/RAG/Scout state during planning.
- Do not restart services during planning or cleanup.
- Do not run Sprint Executor, active mission next-actions, or backlog mutation
  commands by default.
- Do not count read-only observation as research progress.
