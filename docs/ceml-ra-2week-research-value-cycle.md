# CEML_RA 2-Week Research-Value Development Cycle

## Summary

Validate CEML_RA as an evidence-centered, PhD-level research partner by
producing useful research artifacts before deciding what to automate.

This cycle is intentionally not a code-first plan. Code changes should follow
only after a manual or semi-manual artifact proves real research value and makes
the needed system friction clear.

Initial validation topics:

- `materials_ontology_kg`
- `rare_earth_magnets`

Success unit:

- fresh research questions
- evidence briefs
- evidence matrices
- one improved interactive research discussion
- a development backlog based on observed research value

## Research Question Factory

Before any report or implementation work, generate fresh research questions.

Required behavior:

- Generate 8-12 candidate questions per topic.
- Do not reuse wording, framing, or topic structure from examples in planning
  discussions.
- Treat examples as forbidden seed examples, not templates.
- Each question must come from one of these mechanisms:
  - evidence gap
  - contradiction between papers
  - method bottleneck
  - missing benchmark
  - translation from literature trend to calculation or experiment
  - KG/ontology representation problem
  - materials design tradeoff
  - proposal opportunity
- Each candidate must include:
  - why the question matters
  - what evidence would answer it
  - what would make it fail
  - likely output type: brief, evidence matrix, idea memo, debate memo, or
    proposal seed

Guardrails against example copying:

- Maintain a do-not-copy list containing examples from planning discussions.
- Reject questions that only paraphrase examples.
- Require at least two concrete source signals or domain reasons for each
  selected question.
- Ask the user to pick 1-2 questions only after presenting genuinely different
  candidates.

## Days 1-2: Question Discovery

Goal:

- Produce a question menu for both selected topics.

Outputs:

- `materials_ontology_kg` question candidates.
- `rare_earth_magnets` question candidates.
- Top 2 recommended questions per topic with rationale.

Success:

- The user can tell the questions were generated from the research domain, not
  copied from examples.
- At least one question feels worth discussing with a PhD-level collaborator.

## Days 3-5: Concierge Evidence Briefs

Goal:

- Produce one high-quality evidence brief per selected topic.

Each brief must include:

- core question
- 5-8 important papers or source clusters
- claims
- evidence quality
- limitations and counterarguments
- unresolved questions
- 2-3 idea candidates
- recommended next research action

Success:

- The user would actually read the brief.
- The brief separates strong ideas from weak or unsupported ones.

## Days 6-8: Idea Selection And Evidence Matrix

Goal:

- Turn the best ideas into concrete review candidates.

Outputs:

- 2-3 selected ideas total.
- Evidence matrix for each idea:
  - supporting evidence
  - missing evidence
  - assumptions
  - failure modes
  - calculation or experiment path
  - relevance to Scout/RAG/KG memory

Success:

- At least one idea is ready for calculation, experiment, or
  proposal-development review.

## Days 9-11: Interactive Research Partner Test

Goal:

- Test whether CEML_RA can act as a research discussion partner.

Workflow:

- Pick one selected idea.
- Run a Slack-style research discussion.
- CEML_RA must challenge assumptions, reuse evidence, identify weak points, and
  suggest next actions.

Success:

- The discussion improves the idea beyond the static report.
- The user feels the system behaved closer to a PhD-level collaborator than a
  generic chatbot.

## Days 12-14: Automation And Development Backlog

Goal:

- Decide what should be automated only after seeing what was valuable.

Outputs:

- Ranked automation backlog.
- First implementation slice recommendation.
- Explicit list of things not to build yet.

Likely implementation candidates:

- research question generation workflow
- evidence brief template
- evidence matrix generator
- source provenance retrieval
- artifact storage under `RA_artifacts`
- minimal UI surface for selected reports and ideas

Do not prioritize:

- sprint executor expansion
- more dashboard cards
- approval/status loops
- internal objective proof machinery
- proposal state management unless it directly improves idea development

## Goal-Mode Operation

Use one Codex goal as coordinator for the 2-week validation.

Goal objective:

```text
Validate CEML_RA as an evidence-centered PhD-level research partner by producing
fresh research questions, useful evidence briefs, idea matrices, and one
interactive research discussion for materials_ontology_kg and rare_earth_magnets.
```

The goal thread coordinates:

- question generation
- artifact review
- user feedback
- decision on what to automate

Implementation threads are spawned only when:

- a manual artifact proves value
- friction is clear
- the needed system change is small and directly tied to better research output

## Acceptance Criteria

The 2-week cycle succeeds if:

- fresh, non-template research questions are generated
- two evidence briefs are produced
- at least two ideas are evaluated with evidence matrices
- at least one idea advances toward calculation, experiment, or proposal review
- one interactive discussion improves a selected idea
- the resulting development backlog is based on observed research value, not
  prior autonomy momentum

It fails if:

- questions copy examples
- outputs are generic literature summaries
- the work mostly produces status, approvals, or dashboard state
- no idea becomes more actionable
- code work starts before the useful research artifact is clear

## Assumptions

- First topics are `materials_ontology_kg` and `rare_earth_magnets`.
- Cycle duration is 2 weeks.
- Manual-concierge research artifacts come before automation.
- Examples in planning discussions are illustrative only and must not become
  default questions.
- Artifact-root support is infrastructure, not the product validation itself.
