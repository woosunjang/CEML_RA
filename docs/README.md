# CEML_RA Docs

This directory now contains only the current rebuild contract. Older
operational and planning documents were removed after the hard reset because
they described or reintroduced stale runtime/product surfaces.

## Current Truth Hierarchy

Read this first:

1. [CEML_RA Ground Goal And Phased Rebuild](ceml-ra-ground-goal-and-phases.md)

## Direction

CEML_RA is being rebuilt as a PhD-level integrated research colleague with
long-term memory. It is not currently defined by any old local runtime, old
Slack command surface, old launchd service, old API reference, or old autonomy
mission flow.

The Phase 1 core memory-spine target is implemented as a local artifact
contract:

```text
research_thread JSON + Markdown artifacts under
${CEML_RA_ARTIFACTS_DIR:-generated}/research_threads/
```

The Scout evidence adapter now converts read-only Scout paper metadata into
research_thread source signals and evidence previews without mutating Scout DB,
Qdrant, Neo4j, Graphiti, or Slack.

The Coordinator dry-run loop now updates research_thread artifacts through
Scout, evidence synthesis, idea candidate, critique, and next-action stages
using local artifacts only.

The read-only review API now exposes research_thread artifacts so UI and Slack
can later share the same memory spine.

The next product target is a KG ingest preview artifact generated from
research_thread evidence, decisions, and next actions. It must not write to
Neo4j, Graphiti, Qdrant, Scout DB, Slack, or runtime services.

## Storage Boundary

- Source code belongs in git and GitHub.
- Durable research artifacts belong under `CEML_RA_ARTIFACTS_DIR`, normally:

  ```text
  /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
  ```

- Live runtime state, local databases, logs, caches, queues, volumes, and
  `.env` files stay host-local and out of git.
- The relevant source, artifact, and runtime rules now live in the ground
  contract.

## Runtime State

Do not assume a local service is current just because a port is open. After the
hard reset, stale runtimes and watchdogs should be stopped before new baseline
work begins.
