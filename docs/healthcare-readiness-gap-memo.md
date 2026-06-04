# Ryva Healthcare Readiness Gap Memo

Date: 2026-06-03
Author: Codex assessment based on building and validating `healthcare-ai-audit-demo`

## Executive Summary

Ryva has a strong foundation for becoming a serious engineering framework for governed AI systems:

- repo-native configuration
- prompt hashing and compilation
- lineage with signature verification
- model cards and governance reports
- audit package export

The product already feels more substantial than a lightweight prompt runner or observability wrapper. The core direction is correct.

However, Ryva is not yet ready to be positioned as "`dbt for AI agents`" for healthcare buyers without qualification. The main issue is not lack of ambition. The issue is that several critical product surfaces still require manual stitching, contain brittle behavior, or do not yet map cleanly to enterprise approval workflows.

The most important finding from this assessment is that the product vision is ahead of the current execution in a few key places:

- config-driven governance is not fully reliable without schema fixes
- policy enforcement is too brittle against real model output formatting
- cloud sync does not yet carry the full AI System Record story
- healthcare-grade review workflows are not yet first-class objects

## Assessment Basis

This memo is based on:

- inspecting the Ryva CLI repository and built-in sample project
- building a new end-to-end demo at [healthcare-ai-audit-demo](/Users/allieball/ryva/healthcare-ai-audit-demo)
- compiling and validating the project through the real CLI
- generating governance artifacts, docs, lineage, model card, and audit export
- running live model-backed demo cases and Ryva tests
- identifying what had to be hand-built outside native product support

## What Worked Well

### 1. Repo-native AI system definition is the right foundation

Ryva’s project structure is one of its strongest qualities. Defining agents, prompts, tests, lineage, and docs in-repo is the right mental model for serious engineering teams.

Why it matters for healthcare:

- engineering can version-control the AI system
- compliance can review artifacts tied to code state
- legal can see concrete evidence instead of screenshots or slideware

### 2. Compile plus prompt hashing is genuinely useful

The compile step and prompt hash generation are meaningful primitives. This is one of the closest things Ryva has today to a dbt-like artifact model.

Why it matters:

- prompts become traceable assets instead of hidden app strings
- the prompt hash can anchor change management and review workflows
- governance artifacts can reference a stable prompt version

### 3. Lineage is a real differentiator

The lineage records and `verify --all` signature flow are strong. This was one of the most credible parts of the product during assessment.

Why it matters:

- it supports tamper-evident auditability
- it gives engineering and compliance a shared evidence layer
- it is much easier to defend than vague “observability” claims

### 4. Audit export is commercially strong

The audit package export is practical and easy to explain. It gives a concrete output that buyers can understand immediately.

Why it matters:

- legal/compliance teams want a package, not a dashboard only
- external review workflows usually need portable artifacts
- this makes Ryva easier to position as governance infrastructure

### 5. Governance reporting is directionally credible

The governance report is still generic, but it is more substantial than most early AI tooling. It already shows the right instincts:

- risk scoring
- test coverage awareness
- policy awareness
- documentation and lineage checks

## Must Fix Before Selling To Healthcare

These are not polish items. These affect trust, correctness, and adoption risk.

### 1. Do not silently drop governance config

Observed issue:

- `project.yml` extras such as `pii_masking`, `budget`, and inline `policies` were being dropped during compile because `ProjectSchema` did not preserve unknown keys.

Impact:

- users can believe a governance control is configured when it is not actually present in the compiled manifest
- this is unacceptable in a compliance-oriented product

What I changed:

- I fixed this locally in [ryva/schemas.py](/Users/allieball/ryva/ryva/schemas.py)
- I added coverage in [tests/test_project_manifest_config.py](/Users/allieball/ryva/tests/test_project_manifest_config.py)

Recommendation:

- treat config preservation as a release-blocking reliability requirement
- add tests for every documented `project.yml` feature surface
- fail loudly when config is unrecognized if strict mode is enabled

### 2. Policy checks must operate on structured output, not brittle raw text

Observed issue:

- live model runs returned code-fenced JSON
- Ryva successfully parsed the structured output for traces/logs
- alignment checks still failed because policy evaluation was against raw provider text

Impact:

- false negatives appear as compliance failures
- users cannot distinguish formatting defects from real policy violations
- healthcare teams will lose trust in enforcement very quickly

Recommendation:

- parse once, validate once, and use normalized output for downstream checks
- add a structured-output policy engine that works over parsed JSON objects
- classify failures into:
  - provider formatting failure
  - schema failure
  - policy failure
  - semantic-risk failure

### 3. Add first-class structured output enforcement

Observed issue:

- the prompt asked for strict JSON only, but the model still sometimes returned fenced JSON

Impact:

- prompt-only JSON control is not strong enough for governed production workflows

Recommendation:

- support provider-native JSON mode where available
- add built-in output sanitization for markdown fences and wrappers
- expose a project-level `strict_json_output: true` mode
- optionally refuse to save a run as compliant if structured output recovery was needed

### 4. Improve local developer ergonomics for working from source

Observed issue:

- the installed `ryva` package can diverge from the checked-out repo
- the safest way to run local validation was `python -m ryva.cli` with `PYTHONPATH=..`

Impact:

- slows contributors and internal engineers
- creates ambiguity during product development and demo prep

Recommendation:

- standardize a dev workflow in the README
- provide a `make dev`, `uv run`, or equivalent local execution path
- ensure local source execution is obvious and frictionless

### 5. Ship `--input-file` and batch fixture support

Observed issue:

- the CLI only accepts `--input` JSON strings
- demo runs required shell `cat` substitution

Impact:

- poor ergonomics for real test fixtures
- harder CI scripting
- weaker reproducibility for enterprise teams

Recommendation:

- add `--input-file`
- add `--input-dir` or fixture batch execution
- add first-class named demo/eval fixture support

### 6. Stabilize the full test suite before selling into regulated environments

Observed issue:

- the full suite had 3 existing failures in `tests/test_cost_tracker.py`

Impact:

- healthcare engineering buyers will notice quickly if core repo tests are not green
- this reduces confidence in the product’s own engineering discipline

Recommendation:

- do not sell “engineering discipline for AI” while carrying recurring red tests
- green CI is table stakes here

## Important For Pilot Customers

These are not immediate blockers for a demo, but they will matter quickly in real deployments.

### 1. Make approvals and review state first-class

Observed gap:

- approvals, sign-offs, pending reviews, and audit readiness were not native Ryva objects
- I had to create synthetic fixture files to represent them

Why it matters:

- healthcare adoption depends on cross-functional review
- engineering alone is not the buyer

Recommendation:

- add native objects for:
  - reviewer assignments
  - approval stages
  - approval decisions
  - evidence gaps
  - release readiness

### 2. Expand cloud sync to support the actual AI System Record

Observed gap:

- current cloud sync only covers traces, lineage, one compliance report, model cards, and benchmark results
- it does not natively sync approvals, change history, exceptions, release decisions, or audit package manifests

Why it matters:

- the sales story is “AI System Record”
- the synced domain model does not fully support that yet

Recommendation:

- cloud sync should support:
  - systems
  - prompt versions
  - governance findings
  - evidence inventory
  - approvals
  - change history
  - exceptions
  - remediation tasks
  - audit package metadata

### 3. Improve regression semantics

Observed issue:

- regression currently mixes structure and latency concerns in a narrow way
- the demo surfaced a routine-case latency regression, which was useful, but the semantics are not rich enough yet

Recommendation:

- split regression categories:
  - schema regression
  - key-field regression
  - routing regression
  - latency regression
  - cost regression
  - safety regression

### 4. Add stronger healthcare-specific policy/eval templates

Observed gap:

- I had to manually encode healthcare-safe administrative triage expectations

Recommendation:

- provide built-in healthcare starter packs for:
  - no diagnosis
  - no treatment recommendation
  - mandatory human review on urgent language
  - PHI masking expectations
  - escalation routing enums
  - audit documentation scaffolds

### 5. Make governance reporting more decision-oriented

Observed issue:

- the governance report is useful, but still reads more like a static technical summary than a release-decision artifact

Recommendation:

- add sections for:
  - open risks
  - failed controls
  - review owners
  - last approved prompt hash
  - evidence freshness
  - release recommendation

## Nice To Have Later

These are valuable, but not required before serious pilot work.

### 1. Better diffing of prompts, policies, and artifacts

The lineage and hashes are good, but productized change diff views would make reviews far easier.

### 2. Better fixture management

Named fixture sets, scenario labels, and batch replay would improve usability significantly.

### 3. Richer documentation generation

Generated docs should eventually feel closer to technical documentation suitable for governance review rather than basic file summaries.

### 4. Native offline/mock provider mode

Demo and CI workflows would benefit from a deterministic mock provider that returns schema-conforming outputs for non-live validation.

## What Went Well In This Assessment

- The overall product direction held up well under a realistic healthcare workflow.
- The lineage and audit story are materially stronger than most adjacent tools.
- The CLI surface is understandable and logically organized.
- The demo could be built without rewriting the core architecture.

## What Went Poorly In This Assessment

- Config reliability had a real flaw.
- Structured-output handling is not strict enough for compliance-heavy use cases.
- Policy enforcement produced noisy false failures.
- Cloud support is behind the product narrative.
- Some important governance concepts still require manual fixture construction.

## Difficulty Rating

Building and validating a credible healthcare workflow in Ryva today: `7.5/10`

Reason:

- feasible for a strong engineer
- harder than it should be for a repeatable enterprise pattern
- still too dependent on product intuition and manual stitching

## Recommended Roadmap

### Phase 1: Release Blockers

- make config handling fully reliable
- add `--input-file`
- normalize structured output before alignment checks
- add strict JSON enforcement modes
- get the full test suite green

### Phase 2: Pilot Readiness

- add first-class approvals and review objects
- expand cloud sync domain model
- improve regression semantics
- add healthcare and other regulated-domain starter templates
- improve governance report actionability

### Phase 3: “dbt For AI Agents” Positioning

- artifact graph and lineage as a first-class contract
- environment-aware runs and deployments
- reproducible batch fixture execution
- first-class review/diff flows for prompts and policies
- stronger Cloud as the control plane for AI System Records

## Bottom Line

Ryva is promising enough to justify continued investment and pilot positioning.

It is not yet “dbt for AI agents” in the strong sense that healthcare buyers will infer from that phrase.

Today, the most honest positioning is closer to:

> A serious local-first engineering framework for governed AI workflows, with unusually strong lineage and audit foundations.

That is already a strong product story.

To sell successfully into healthcare, the next step is not a bigger vision. The next step is tightening reliability, structured-output enforcement, and first-class governance workflow objects until the product behavior matches the ambition.
