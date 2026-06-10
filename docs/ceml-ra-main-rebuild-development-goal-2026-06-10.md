# CEML_RA Main Rebuild Goal

**Date:** 2026-06-11

## Current State

CEML_RA has been reset onto a clean source branch:

```text
main
```

Stage 0 source/artifact separation is complete enough for the user to disable
Dropbox sync on the source folder:

```text
/Users/woosun/Dropbox/Dev/CEML_RA
```

Durable artifacts and portable knowledge snapshots should remain under the
Dropbox-synced artifact root:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts
```

Live databases, logs, caches, command queues, Docker volumes, service state, and
local `.env` files must remain host-local and out of git.

## Canonical Product Plan

The next product plan is the 2-week research-value validation cycle:

```text
docs/ceml-ra-2week-research-value-cycle.md
```

That plan starts with fresh research-question generation, not with code work or
old autonomy machinery.

The immediate next product step is:

```text
Days 1-2: Research Question Factory
```

Initial topics:

- `materials_ontology_kg`
- `rare_earth_magnets`

## What To Ignore By Default

Old autonomy-pulse branches, old mission IDs, old Sprint Executor behavior, old
proposal backlog pressure, old generated/ops reports, old schedule plans, old
surface audits, and old reset narratives are historical only.

Do not inspect, summarize, restore, cherry-pick, or use them as planning context
unless the user explicitly asks for a specific artifact.

## Storage Contract

- Source code: Git/GitHub.
- Durable user-facing artifacts: `CEML_RA_ARTIFACTS_DIR`, normally
  `/Users/woosun/Dropbox/Dev/CEML/RA_artifacts`.
- Local fallback artifacts for tests/development: in-repo `generated/`.
- Live runtime state: host-local paths outside Dropbox sync and outside git.
- Exports/snapshots: explicit, reviewable, non-destructive commands only.

## Hard Guardrails

- Do not push without explicit approval.
- Do not delete local branches or stashes without explicit approval.
- Do not restart services during planning or cleanup.
- Do not mutate live DB/KG/RAG/Scout state during planning.
- Do not sync live DBs through Dropbox.
- Do not treat old autonomy-pulse material as product direction.
- Do not count read-only observation as research progress.

## Next Action

Start the 2-week cycle by producing a question menu for
`materials_ontology_kg` and `rare_earth_magnets` according to
`docs/ceml-ra-2week-research-value-cycle.md`.
