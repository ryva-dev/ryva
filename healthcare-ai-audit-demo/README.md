# healthcare-ai-audit-demo

`healthcare-ai-audit-demo` is a polished, fully synthetic Ryva demo project for a fictional healthcare operations company, Northstar CareOps.

The single AI system in this demo is `patient_intake_triage_agent`. It summarizes synthetic patient intake requests, flags urgent language, and recommends whether the request should route to scheduling, nurse review, billing, or care coordination. It is explicitly constrained to administrative triage only:

- It does not diagnose.
- It does not recommend treatment.
- It does not make final patient-care decisions.
- It always escalates urgent or clinical language to human review.

## Why This Demo Works For Ryva

This project is built to demonstrate Ryva's core value proposition:

> Ryva turns AI workflow activity — prompts, tests, traces, lineage, risk metadata, policy checks, and governance reports — into an audit-ready AI System Record that engineering, compliance, and legal teams can review.

The demo shows:

- typed agent and prompt definitions in-repo
- policy enforcement and governance evidence
- schema, regression, adversarial, hallucination, fuzz, and latency coverage
- pre-seeded synthetic traces and lineage for dashboard demos
- model-card, governance-report, and audit-package generation
- cloud fixture payloads for dashboard ingestion demos when real cloud sync is not used

## Synthetic Data Notice

Everything in this folder is fake:

- Northstar CareOps is fictional
- all patient names, IDs, phone numbers, emails, and dates are synthetic
- no real PHI, no real patient records, no real insurance data, and no real secrets are included

This demo helps capture governance evidence. It is not legal advice and it does not prove HIPAA compliance.

## Project Layout

```text
agents/                Agent definition
prompts/               Prompt template
tests/                 Ryva-native test definitions
baselines/             Regression baseline
demo_inputs/           Eight synthetic intake records
traces/                Pre-seeded synthetic trace records
lineage/               Pre-seeded signed lineage records
logs/                  Pre-seeded run logs and feedback annotations
cloud_fixtures/        Dashboard-shaped JSON fixtures
audit_assets/          Extra documentation referenced by the audit manifest
data/policies/         Synthetic policy documentation
scripts/               Demo runner
```

## Prerequisites

```bash
cd /Users/allieball/ryva/healthcare-ai-audit-demo
export PYTHONPATH=..
```

Optional environment variables:

```bash
export ANTHROPIC_API_KEY=your_key_here     # Required for live model runs and model-dependent tests
export RYVA_SECRET=demo-signing-secret     # Optional override; demo lineage already ships with a stable project secret
export RYVA_CLOUD_URL=https://...          # Optional override for Ryva Cloud endpoint
```

## Exact Commands

Compile and inspect:

```bash
python -m ryva.cli compile
python -m ryva.cli list agents
python -m ryva.cli dag --agent patient_intake_triage_agent
```

Run sample inputs:

```bash
python -m ryva.cli run --agent patient_intake_triage_agent --input "$(cat demo_inputs/routine_appointment_request.json)"
python -m ryva.cli run --agent patient_intake_triage_agent --input "$(cat demo_inputs/urgent_symptom_language.json)"
python -m ryva.cli run --agent patient_intake_triage_agent --input "$(cat demo_inputs/fake_phi_masking_case.json)"
```

Run evaluation and policy commands:

```bash
python -m ryva.cli test --agent patient_intake_triage_agent
python -m ryva.cli test --adversarial --agent patient_intake_triage_agent
python -m ryva.cli test --hallucination --agent patient_intake_triage_agent
python -m ryva.cli test --regression --agent patient_intake_triage_agent
python -m ryva.cli test --fuzz --agent patient_intake_triage_agent
python -m ryva.cli align --agent patient_intake_triage_agent
```

Generate governance artifacts:

```bash
python -m ryva.cli docs generate
python -m ryva.cli modelcard patient_intake_triage_agent
python -m ryva.cli governance report
python -m ryva.cli lineage verify --all
python -m ryva.cli lineage search --agent patient_intake_triage_agent
python -m ryva.cli audit export
```

Cloud connectivity:

```bash
python -m ryva.cli cloud status
python -m ryva.cli cloud sync
```

If you do not want to use real cloud credentials yet, use the local fixture payloads in `cloud_fixtures/`.

## Production Forge Hook-In (No CLI Rewrite)

Send live or synthetic production traces to Ryva Forge from your existing Claude app:

```bash
export RYVA_PROJECT_ID="<forge-project-id>"
export RYVA_SYSTEM_ID="<registered-system-id>"
export RYVA_INGESTION_TOKEN="<trace_ingest + lineage_ingest token>"
# optional for live Claude call:
export ANTHROPIC_API_KEY="..."

python scripts/forge_ingest_demo.py
```

`scripts/forge_ingest_demo.py` uses `ryva.integrations.anthropic.instrumented_client()` when `ANTHROPIC_API_KEY` is set, otherwise sends a synthetic hashed lineage record suitable for dashboard demos.

`scripts/run_healthcare_demo.sh` runs the Forge ingest demo automatically when the `RYVA_*` env vars are set.

## Five-Minute Demo Flow

1. Run `python -m ryva.cli compile` to show the typed AI system definition and prompt hashing.
2. Open [agents/patient_intake_triage_agent.yml](/Users/allieball/ryva/healthcare-ai-audit-demo/agents/patient_intake_triage_agent.yml) and [policies.yml](/Users/allieball/ryva/healthcare-ai-audit-demo/policies.yml) to frame the controls.
3. Run the urgent input and show that the system routes to human review rather than making a care decision.
4. Run `python -m ryva.cli governance report` and `python -m ryva.cli modelcard patient_intake_triage_agent` to show audit evidence.
5. Run `python -m ryva.cli lineage search --agent patient_intake_triage_agent` and `python -m ryva.cli lineage verify --all` to show traceability and tamper-evident lineage.
6. Open `cloud_fixtures/` to show approvals, change history, and the audit package shape that Ryva Cloud would ingest.

## What To Point Out In A Sales Call

- The system record is built from repo-native assets, not after-the-fact documentation.
- Prompt versioning and prompt hash changes are visible across traces.
- Alignment policies and tests convert safety expectations into evidence.
- Governance reporting highlights high-risk healthcare context without claiming Ryva certifies compliance.
- Pre-seeded approvals and change history show cross-functional review: engineering, privacy/security, compliance, and legal.

## Commands That Need A Model API Key

These commands call the provider configured in `project.yml` and require `ANTHROPIC_API_KEY` unless you reconfigure the provider:

- `python -m ryva.cli run ...`
- `python -m ryva.cli test --agent patient_intake_triage_agent`
- `python -m ryva.cli test --adversarial --agent patient_intake_triage_agent`
- `python -m ryva.cli test --hallucination --agent patient_intake_triage_agent`
- `python -m ryva.cli test --regression --agent patient_intake_triage_agent`
- `python -m ryva.cli test --fuzz --agent patient_intake_triage_agent`
- `python -m ryva.cli align --agent patient_intake_triage_agent`

These commands work offline with local files:

- `python -m ryva.cli compile`
- `python -m ryva.cli list agents`
- `python -m ryva.cli dag --agent patient_intake_triage_agent`
- `python -m ryva.cli docs generate`
- `python -m ryva.cli modelcard patient_intake_triage_agent`
- `python -m ryva.cli governance report`
- `python -m ryva.cli lineage verify --all`
- `python -m ryva.cli lineage search --agent patient_intake_triage_agent`
- `python -m ryva.cli audit export`

## Convenience Script

Run the bundled demo script:

```bash
bash scripts/run_healthcare_demo.sh
```

The script always runs the offline-safe artifact commands. If `ANTHROPIC_API_KEY` is present, it also runs the live demo cases and model-dependent tests.

## Working Tree Hygiene

- `lineage/` is intentionally versioned for the demo so signature verification and audit flows work offline.
- live runs append new local artifacts under `traces/` and may add additional lineage records for fresh run IDs.
- if you want to inspect the demo without changing the working tree, stick to the offline-safe commands listed above.
- to remove generated local artifacts and return the demo to its checked-in state, run:

```bash
python -m ryva.cli demo reset
```
