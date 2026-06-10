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

The next product target is Phase 1 from the ground contract:

```text
Create the research_thread memory spine and seed parallel threads for
materials_ontology_kg and rare_earth_magnets.
```

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
