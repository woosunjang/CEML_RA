# CEML_RA Ground Goal And Phased Rebuild

**Status:** Phase 0 ground contract.
**Date:** 2026-06-11

## Ground Goal

CEML_RA is not an automatic report tool. It is a PhD-level integrated
research colleague with long-term memory.

The system should study the user's research topics every day and every week,
accumulate papers, evidence, ideas, objections, decisions, and next actions,
then reuse that accumulated context when the user asks for research discussion,
idea development, proposal writing, or project management.

The success criterion is not that many jobs ran. The success criterion is that
research context accumulates and becomes useful in the next artifact,
conversation, or research decision.

CEML_RA succeeds when:

- research context accumulates across time;
- accumulated context is reused in later outputs and conversations;
- weakly supported ideas are separated from ideas with real potential;
- at least two ideas advance toward calculation, experiment, or proposal
  review;
- the user feels that the system is thinking with them as a research
  colleague.

## Operating Spirit

CEML_RA must preserve one continuous research mind across automatic and
on-demand work.

Automatic mode:

- quietly reads, compares, and organizes research sources;
- produces weekly research synthesis, evidence briefs, idea candidates, and
  next-action suggestions;
- asks the user only when a research choice, external action, or meaningful
  approval boundary is reached.

On-demand mode:

- discusses research ideas with the user through Slack or UI;
- challenges assumptions and identifies missing evidence;
- reuses prior research threads, KG memory, RAG evidence, and artifacts;
- helps with proposal writing, manuscript planning, and project management
  from the same accumulated research context.

These modes must not become separate products. A weekly report must be able to
feed a later Slack discussion. A Slack discussion must be able to update the
research thread and prepare KG/RAG memory updates. A proposal draft must trace
back to evidence and decisions already accumulated.

## Memory Roles

The rebuild uses three memory surfaces with different responsibilities.

`RA_artifacts` is the durable human-readable record.

- It stores research thread Markdown and JSON, evidence matrices, weekly
  syntheses, proposal seeds, and portable snapshots.
- It is the ground truth for review and handoff.
- It must remain outside live runtime state and should normally live at:

  ```text
  /Users/woosun/Dropbox/Dev/CEML/RA_artifacts
  ```

Neo4j + Graphiti is the canonical knowledge graph memory.

- Neo4j is the graph backend for long-term research memory.
- Graphiti is the temporal/context graph layer for episodes, entities,
  relationships, provenance, and changing facts.
- KG ingest starts as preview first, then explicit approval, then ingest.
- KG memory augments artifacts; it does not replace them.

Qdrant is the document and paper retrieval memory.

- Qdrant stores embedded paper and document chunks for RAG.
- It supports source retrieval and comparison.
- It is not the canonical store for decisions, research state, or provenance.

Legacy code or documents may still mention FalkorDB as an earlier Graphiti
backend. Those references describe historical implementation state and are
migration targets, not the rebuild's canonical KG direction.

## Source, Artifact, And Runtime Boundary

Source code is owned by git and GitHub.

- Keep source code, tests, config templates, and current docs in the
  repository.
- Do not commit local `.env` files, generated outputs, live databases, logs,
  caches, queues, service state, Docker volumes, or Dropbox conflict copies.

Durable research artifacts should use `CEML_RA_ARTIFACTS_DIR` when code writes
portable outputs:

```bash
export CEML_RA_ARTIFACTS_DIR=/Users/woosun/Dropbox/Dev/CEML/RA_artifacts
```

If `CEML_RA_ARTIFACTS_DIR` is unset, code may use the in-repo `generated/`
fallback for local development and tests. `generated/` remains ignored by git.

Live runtime state is host-local.

- SQLite databases, WAL/SHM files, Neo4j volumes, Qdrant volumes, Scout DBs,
  logs, caches, queues, pid files, and local `.env` files must not be moved
  into Dropbox or committed.
- Portable knowledge moves into `RA_artifacts` only through explicit,
  reviewable snapshot/export commands with a manifest.
- Stale runtimes should not be treated as current product evidence just
  because a localhost port is open.

## Research Memory Spine

Before building more features, define how research is remembered.

The standard unit is a `research_thread`.

A research thread accumulates:

- topic;
- research state;
- source signals;
- claims;
- evidence;
- counterarguments;
- idea candidates;
- failure modes;
- decisions;
- next actions;
- KG ingest preview.

The first threads are:

- `materials_ontology_kg`;
- `rare_earth_magnets`.

The first artifact is not a dashboard card or a status report. It is a
human-readable research thread that can be reopened, challenged, extended, and
used as context for later work.

## Coordinator And Subagents

CEML_RA should have one central Research Coordinator.

The Research Coordinator owns:

- active research threads;
- long-term research goals;
- when to call subagents;
- what should be remembered;
- what should be surfaced to the user;
- what should remain unbuilt until value is proven.

The coordinator does not do all work directly. It delegates to subagents such
as:

- Scout for paper discovery and source signals;
- Literature/RAG for paper comparison and retrieval;
- KG Memory for graph episode preview and ingest;
- Evidence Critic for claim, citation, and failure-mode review;
- Writing for proposal, manuscript, and memo drafting;
- Project for milestones, next actions, and deadlines.

Each subagent must update or use the same research thread. Independent agent
outputs that do not feed memory are not product progress.

## Phases

### Phase 0: Spirit And Ground Contract

Create and maintain this ground contract as the first source of product truth.

This phase fixes:

- integrated research colleague identity;
- automatic and on-demand operating modes;
- Neo4j KG, Qdrant RAG, and `RA_artifacts` responsibilities;
- anti-busywork guardrails;
- approval boundaries;
- old-runtime quarantine.

This phase is complete only when future development can use this document as
the first decision filter.

### Phase 1: Research Memory Spine

Define the `research_thread` schema and create the first two topic threads.

The output is a readable artifact, not a UI surface.

The first proof loop uses two parallel topics:

- `materials_ontology_kg`;
- `rare_earth_magnets`.

The loop should produce fresh questions, evidence synthesis, idea candidates,
failure modes, and next actions inside the research thread. It should not
create a competing canonical plan outside this ground contract.

### Phase 2: Coordinator And Subagents

Implement the Research Coordinator as a thin owner of research loops and memory
updates.

The first loop must connect investigation, evidence synthesis, idea
generation, criticism, and next action.

### Phase 3: Memory Infrastructure

Bring up Neo4j + Graphiti as canonical KG memory and Qdrant as RAG memory.

KG writes start as preview, then approval, then ingest. Artifacts remain the
reviewable ground truth.

### Phase 4: User Experience Loop

Slack becomes the discussion surface. UI becomes the research-thread,
evidence, idea, and next-action review surface.

Automatic weekly outputs and interactive discussions must share the same
research memory.

### Phase 5: Automation Only After Proof

Add automation only after the two initial research threads produce useful
research value.

Automation candidates:

- weekly research synthesis;
- evidence matrix generation;
- KG ingest;
- proposal seed generation;
- project next-action management.

Do not prioritize:

- dashboard card expansion;
- status loops;
- approval machinery for its own sake;
- Sprint Executor revival;
- proposal state management unless it directly improves research idea
  development.

## Anti-Busywork Guardrails

Do not count the following as product progress:

- reading runtime state without producing or improving a research artifact;
- adding status pages that do not improve research decisions;
- expanding autonomy loops that only create questions, approvals, or logs;
- implementing old mission, sprint, or proposal machinery by default;
- ingesting into KG/RAG without a useful research thread or evidence artifact;
- building UI before the memory spine is useful.

Every development slice should answer:

```text
Does this make a research thread, KG/RAG memory, or user-facing research
discussion more useful?
```

If the answer is no, do not build it yet.

## Approval Boundaries

Allowed without additional product approval:

- read-only repo inspection;
- writing source code, tests, and docs on an approved branch;
- generating local preview artifacts under the configured artifact root;
- creating KG/RAG ingest previews that do not mutate live stores.

Requires explicit user approval:

- pushing to remote;
- deleting branches, stashes, or runtime state;
- stopping or restarting live services;
- mutating live Neo4j, Qdrant, Scout DB, or other runtime stores;
- sending external Slack messages beyond expected local/dev flows;
- starting long-running missions or autonomous schedules.

## Old Runtime And Historical Material

Previous live APIs, old autonomy endpoints, old mission IDs, Sprint Executor
history, proposal backlog state, old generated ops artifacts, old schedule
plans, and old reset/audit narratives are not product direction.

They may be inspected only when the user asks for a specific artifact or when a
cleanup preview needs to identify what will be removed. They should not be used
as the blueprint for the rebuild.

## Current Development Target

The Phase 1 core memory-spine implementation now exists as durable
`research_thread` JSON and Markdown artifacts seeded for:

```text
materials_ontology_kg and rare_earth_magnets.
```

The Scout evidence adapter now converts read-only Scout paper metadata into
research_thread source signals and evidence previews without mutating Scout DB,
Qdrant, Neo4j, Graphiti, Slack, or runtime services.

The next development target is the Coordinator dry-run loop. That target should
improve the same durable research threads before adding UI, Slack commands,
KG/RAG writes, or automation.
