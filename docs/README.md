# CEML_RA Docs

This directory is a small index for current repo-local project truth.

Read first:

1. [CEML_RA Ground Goal And Phased Rebuild](ceml-ra-ground-goal-and-phases.md)
2. [Repo operating instructions](../AGENTS.md)
3. [Current handoff](../.agents/context/HANDOFF.md)
4. [Task log](../.agents/context/TASK_LOG.md)

## Direction Boundary

CEML_RA is being rebuilt as a PhD-level integrated research colleague with
long-term memory. It is not defined by old local runtimes, old Slack command
surfaces, old launchd services, old API references, old autonomy mission flows,
or stale Codex global memory.

Recent research artifacts, proposal artifacts, and planner outputs are
available context only. They are not an implied roadmap. Choose the next product
step from the current repo-local files and the user's latest instruction.

## Storage Boundary

- Source code belongs in git and GitHub.
- Durable research artifacts belong under `CEML_RA_ARTIFACTS_DIR`, normally:

  ```text
  /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
  ```

- Live runtime state, local databases, logs, caches, queues, volumes, and
  `.env` files stay host-local and out of git.

## Runtime Boundary

Do not assume a local service is current just because a port is open. Stale
runtimes and watchdogs are not product evidence.
