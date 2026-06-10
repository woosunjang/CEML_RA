# CEML_RA Main Rebuild Development Goal

**Date:** 2026-06-10
**Purpose:** Split the reset into two stages:

1. Short-term repository/storage cleanup so CEML_RA can leave Dropbox source
   sync and use GitHub as code source of truth.
2. Later application of the separate "CEML_RA 2-Week Research-Value Development
   Cycle" plan from a clean, main-derived baseline.

## Decision

Restart new product development from `main`.

The current Stage 0 branch is:

```text
codex/ceml-ra-stage0-main
```

The old `codex/ceml-ra-reset-baseline` branch is useful as a reference, but it
is not neutral enough for the next product cycle. It descends from the old
autonomy-pulse work and contains artifact-root refactors that begin to
formalize many read-only writers.

Do not push or build on the old local unpushed commit unless explicitly
re-approved:

```text
4fd6f46 feat: route research and specialist artifacts
```

Keep existing autonomy-pulse/reset-baseline branches as archives for selective
reference only.

## Stage 0: Source Migration And Cleanup

Stage 0 is the immediate goal.

Its purpose is to make CEML_RA safe to develop before the two-week feature
cycle begins. This stage is about repository hygiene, storage boundaries, and
removing old-session bias from the live operating context.

### Objectives

- Use GitHub as the source of truth for code.
- Let the user disable Dropbox sync for this CEML_RA source folder manually.
- Keep durable artifacts and portable knowledge snapshots in Dropbox.
- Keep live runtime state host-local.
- Continue from the same-folder, main-derived Stage 0 branch.
- Prevent old autonomy-pulse reports, probes, and mission logs from becoming
  product requirements by accident.

### Artifact Root

Use this Dropbox-synced artifact root:

```bash
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts
```

The rebuild should reintroduce only the minimal code needed for:

- `CEML_RA_ARTIFACTS_DIR`
- internal `ARTIFACTS_DIR`
- fallback to in-repo `generated/` when the environment variable is unset
- a small set of artifact folder constants chosen for the new direction
- docs and tests that protect source/artifact/runtime-data boundaries

Do not carry over all artifact-routing commits wholesale. Reimplement or
cherry-pick only the small, durable pieces.

### Live Data Boundary

Do not place live SQLite, Neo4j, Qdrant, Scout DBs, command queues, logs, or
service state inside Dropbox.

Dropbox-syncable knowledge should be exported snapshots, for example:

- Scout SQLite backup or JSONL export
- orchestrator mission/job/KG queue backups
- Qdrant collection snapshot/export after explicit approval
- Neo4j dump/export after explicit approval
- manifest rows describing what was exported, when, from which host, and from
  which source path

### Same-Folder Cleanup Caveat

Because the user chose to continue in the same folder, switching from the old
branch to `main` can leave old-branch-only files as untracked leftovers.

Before deleting anything:

```bash
git clean -fd -n
```

Delete only after explicit approval. Runtime data, conflict copies, caches, and
old generated artifacts should not be committed.

### Stage 0 Done Criteria

Stage 0 is complete when:

- current branch is main-derived
- GitHub remote and branch flow are clear
- source tree Dropbox sync can be disabled without losing artifacts
- `CEML_RA_ARTIFACTS_DIR` can point to
  `/Users/woosun/Dropbox/Dev/CEML/RA_artifacts`
- in-repo `generated/` fallback still works for local development/tests
- live DB defaults do not point into Dropbox
- `.gitignore` covers runtime artifacts, logs, DBs, caches, command queues, and
  conflict copies
- a short artifact/runtime boundary doc exists
- focused path-resolution tests pass
- no broad old-writer migration has been introduced

## Stage 1: Two-Week Research-Value Development Cycle

Stage 1 starts only after Stage 0 is complete.

The separate two-week development plan should be applied to the clean
main-derived branch, not to `codex/mission-autonomy-pulse` or
`codex/ceml-ra-reset-baseline`.

### Product Goal

Build CEML_RA as a research-value system, not a self-observing autonomy demo.

The system should help the user make real research progress through:

- clear mission intake and research goals
- source-grounded evidence collection and review
- explicit user questions when scientific judgment is needed
- durable research artifacts that are useful outside the app
- synchronized knowledge snapshots, not synced live databases
- a minimal operator surface that shows the next important action

The loop should prefer one useful artifact over many status reports.

## Old Surface Audit Before Reuse

Before Stage 1 reuses old autonomy-pulse functionality, classify old read-only
writers and product surfaces as:

- `core`: keep for the rebuild
- `merge`: fold into one smaller operator surface
- `dev-diagnostic`: keep only as developer tooling
- `remove-candidate`: do not carry forward unless a future need proves it

Do not automatically carry forward:

- many separate `autonomy_*_report`, `*_packet`, `*_board`, `*_standup`, and
  `*_probe` writers
- Sprint Executor mutation lanes from autonomy-pulse
- self-answering behavior
- proposal promotion logic
- source-review question machinery
- specialist work-order ledgers
- synthetic benchmark and quality packet surfaces
- read-only smoke/probe artifacts as product outputs

## Features Worth Selectively Salvaging

These ideas are likely worth reimplementing or cherry-picking in small pieces:

- GitHub as code source of truth
- Dropbox artifact root through `CEML_RA_ARTIFACTS_DIR`
- generated fallback for local development
- host-local runtime data boundary
- portable knowledge snapshot/export concept
- artifact/knowledge snapshot manifests
- bounded previews before runtime mutation
- explicit user questions when scientific judgment is genuinely required
- tests that protect path resolution and non-mutation behavior

## Hard Guardrails

- Do not push without explicit approval.
- Do not restart services during planning or baseline setup.
- Do not mutate live DB/KG/RAG/Scout state during rebuild planning.
- Do not sync live DBs through Dropbox.
- Do not treat prior autonomy-pulse momentum as product direction.
- Do not add a new report surface unless it replaces or consolidates an older
  one.
- Do not count read-only observation as research progress.

## Handoff Prompt For The Next Session

Use this prompt before continuing Stage 0:

```text
We are on the same-folder, main-derived Stage 0 branch:
codex/ceml-ra-stage0-main.

Short-term goal: complete Dropbox/GitHub separation and repository cleanup.
This comes before the separate "CEML_RA 2-Week Research-Value Development
Cycle" feature plan.

The user will disable Dropbox sync for the source folder manually. Do not create
an external clone/worktree unless explicitly asked.

Before feature work:
1. Confirm current branch is codex/ceml-ra-stage0-main and main-derived.
2. Preview old untracked leftovers before deleting anything.
3. Keep GitHub as source of truth for code.
4. Implement only minimal Dropbox artifact-root support:
   CEML_RA_ARTIFACTS_DIR, ARTIFACTS_DIR, generated fallback, docs, tests.
5. Keep live DBs host-local; sync only exported snapshots/manifests.
6. Audit old read-only writers before reusing them.

Do not mutate runtime services, DB/KG/RAG/Scout state, launchd, or command
queues unless explicitly approved.
```
