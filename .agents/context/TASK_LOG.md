# Task Log

## 2026-06-11 — Collapsed docs to the ground contract

**Status:** Complete on `codex/ceml-ra-ground-contract`.

After the hard reset, the user asked to remove confusing old documentation and
stop treating stale local runtime surfaces as product truth.

The `docs/` directory now keeps only:

```text
docs/README.md
docs/ceml-ra-ground-goal-and-phases.md
```

The standalone operational planning documents were removed. Their
still-current source, artifact, and runtime rules were folded into the ground
contract.

## 2026-06-11 — Stopped stale Mac Mini runtime

**Status:** Complete.

Runtime cleanup completed:

- stale `uvicorn api.server:app` on `127.0.0.1:8000` was terminated;
- no CEML_RA launchd labels were loaded at cleanup time;
- CEML_RA-related local service ports `3000`, `8000`, `6333`, `6379`, `7474`,
  and `7687` were verified closed;
- Apple `/usr/libexec/watchdogd` was left alone because it is an OS process,
  not a CEML_RA runtime.

Do not restart the stopped Mac Mini runtime unless the user explicitly asks.

## 2026-06-11 — Added ground goal and phased rebuild contract

**Status:** Complete.

The Phase 0 ground contract is:

```text
docs/ceml-ra-ground-goal-and-phases.md
```

It defines CEML_RA as a PhD-level integrated research colleague with long-term
memory, not an automatic report tool. It fixes the role split between
`RA_artifacts`, Neo4j + Graphiti, and Qdrant, and makes `research_thread` the
next memory-spine target.

## 2026-06-10 to 2026-06-11 — Source reset and artifact preservation

**Status:** Complete.

Source was reset onto clean `main`, old live context was purged, and the
current source tree uses an internal `.git/` directory.

The pre-cleanup source archive remains under the durable artifact root:

```text
/Users/woosun/Dropbox/Dev/CEML/RA_artifacts/source_archives/CEML_RA_full_with_gitdir_20260610_220548.tar.gz
```

Keep `/Users/woosun/Dropbox/Dev/CEML/RA_artifacts` as the durable artifact
location. Live DBs, logs, caches, command queues, service state, and local
`.env` files stay host-local and out of git.
