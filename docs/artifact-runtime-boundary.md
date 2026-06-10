# Artifact And Runtime Boundary

**Status:** Stage 0 baseline contract.

This repository treats source code, durable artifacts, and live runtime state as
separate storage classes.

## Source Code

Source code is owned by git and GitHub.

- Keep code, tests, docs, and config templates in the repository.
- Do not commit local `.env` files, generated outputs, databases, logs, caches,
  command queues, or Dropbox conflict copies.
- The local folder may live under Dropbox temporarily, but Dropbox is not the
  code source of truth.

## Durable Artifacts

Durable artifacts are research outputs that should survive source-folder
cleanup and can be synced or moved between machines.

Set this environment variable when artifacts should be written outside the
source tree:

```bash
export CEML_RA_ARTIFACTS_DIR=/Users/woosun/Dropbox/Dev/CEML/RA_artifacts
```

When `CEML_RA_ARTIFACTS_DIR` is set, orchestrator artifact constants resolve
under that directory:

| Constant | Path |
| --- | --- |
| `ARTIFACTS_DIR` | `$CEML_RA_ARTIFACTS_DIR` |
| `GENERATED_PROJECT_DIR` | `$CEML_RA_ARTIFACTS_DIR/project` |
| `GENERATED_WRITING_DIR` | `$CEML_RA_ARTIFACTS_DIR/writing` |
| `GENERATED_TEACHING_DIR` | `$CEML_RA_ARTIFACTS_DIR/teaching` |
| `GENERATED_PRESENTATION_DIR` | `$CEML_RA_ARTIFACTS_DIR/presentation` |
| `GENERATED_REPORTS_DIR` | `$CEML_RA_ARTIFACTS_DIR/reports` |

If the env var is unset, these constants fall back to in-repo `generated/` for
local development and tests. `generated/` remains ignored by git.

The Scout report path also honors `CEML_RA_ARTIFACTS_DIR` for Markdown reports.
Scout live inputs, processed state, and SQLite DBs remain under
`lab-paper-scout/data/` unless a separate, explicit export flow is added.

## Live Runtime State

Live runtime state is host-local and should not be synced through Dropbox or
committed to git.

Examples:

- SQLite databases and WAL/SHM files
- Qdrant and FalkorDB/Neo4j volumes
- Scout live DBs, processed queue state, daemon pid/restart markers
- Orchestrator command queues
- Logs, caches, `.next/`, `node_modules/`, Python caches
- Local `.env` files and process pid files

Portable knowledge should be copied into `CEML_RA_ARTIFACTS_DIR` only through an
explicit snapshot/export command with a manifest describing source path, host,
timestamp, and export type. Do not move live DB files into Dropbox as a default
runtime path.

## Current Stage 0 Archive

The pre-cleanup same-folder snapshot is stored outside the source tree:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/source_archives/CEML_RA_full_with_gitdir_20260610_220548.tar.gz
```

It includes both the `CEML_RA/` working folder and the external
`git_repo/CEML_RA.git/` metadata needed to recover local branches and stashes.
