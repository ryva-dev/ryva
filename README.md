# Ryva

Local-first testing, lineage, and cost controls for AI agents.

Ryva lets you define agents, prompts, tools, pipelines, tests, evals, and policies in your repo, then run them through a CLI workflow that feels closer to pytest/dbt than a hosted observability dashboard.

Use it to:
- catch prompt, model, tool, and pipeline regressions before deploy
- hash and track prompt versions
- compare outputs against baselines
- trace every run with inputs, outputs, retrieval chunks, tool calls, tokens, and cost
- enforce business rules as code
- export lineage and governance artifacts when something needs to be explained

---

## Why Ryva?

Building production AI today means wrestling with scattered prompt files, undocumented agents, no test coverage, no cost visibility, and zero traceability when something goes wrong. Ryva fixes all of it.

- Every component is a **typed, versioned file** — no more prompt sprawl
- **Tests are built in** — schema, latency, adversarial, RAG, fine-tune, regression, and more
- Every run writes a **cryptographically signed lineage record** you can audit
- **EU AI Act compliance** is a single command, not a consulting engagement
- Works entirely **offline and local-first** — cloud is optional

---

## Install

```bash
pip install ryva
```

---

## Quickstart

```bash
ryva init my-ai-project
cd my-ai-project
export ANTHROPIC_API_KEY=your_key_here
ryva compile
ryva run --agent summarizer_agent --input '{"text": "Your text here"}'
ryva test
ryva docs generate
```

---

## What Ryva Covers

### Agents, Pipelines & Tools
Define every AI component as a structured YAML file with explicit inputs, outputs, and dependencies. Compile validates the whole project before anything runs.

```yaml
name: summarizer_agent
version: "1.0.0"
description: "Summarizes text into a concise output."
prompt: ref(prompts/summarizer)
tools: []
input:
  schema:
    text:
      type: str
      required: true
output:
  schema:
    summary:
      type: str
    word_count:
      type: int
```

### Testing
Run tests in parallel across agents, pipelines, ML models, vector stores, and multimodal models.

```bash
ryva test                                              # Run everything (parallel, default 10 workers)
ryva test --concurrency 5                              # Tune parallelism
ryva test --agent my_agent                             # Single agent
ryva test --adversarial                                # Adversarial + security
ryva test --rag                                        # RAG pipeline evaluation
ryva test --finetune                                   # Fine-tune evaluation
ryva test --regression                                 # Regression against baseline
ryva test --hallucination                              # Hallucination detection
ryva test --memory                                     # Memory and context retention
ryva test --fuzz                                       # Fuzz testing
ryva eval --agent my_agent                             # LLM-as-judge quality scoring
```

Built-in test types for agents:

| Type | What It Checks |
|---|---|
| `schema` | Field presence, types, ranges, minimum lengths |
| `returns_non_empty` | Output is non-empty |
| `contains_key` | Required keys are present |
| `latency_under_ms` | Response time within threshold |

### Semantic Similarity
All RAG, fine-tune, and hallucination scoring uses **local semantic embeddings** (`all-MiniLM-L6-v2`) for meaningful quality scores — no external API calls required. Falls back to token-overlap F1 when the model is unavailable.

---

## Tamper-Evident Lineage

Every production run writes a cryptographically signed lineage record. Signatures use HMAC-SHA256 over canonical record fields — any field tampering is immediately detectable.

```bash
ryva lineage show <run-id>           # Full chain with token counts, costs, prompt hashes
ryva lineage search --agent my_agent --since 2026-05-01
ryva lineage verify <run-id>         # Verify HMAC signature
ryva lineage verify --all            # Audit every record in the project
ryva lineage export <run-id> --out compliance.json
ryva diff <run-id-a> <run-id-b>      # Compare two runs side by side
```

Configure the signing secret:

```bash
export RYVA_SECRET=your-secret-key
# or place it in .ryva_secret (automatically gitignored)
```

Lineage records capture: agent, model, provider, prompt template, prompt hash, input hash, output hash, token counts, cost, latency, retrieval chunks, tool calls, and parent run linkage for multi-agent chains.

---

## PII Masking

Automatically detect and redact sensitive data before it reaches prompts or is written to logs.

```yaml
# project.yml
project:
  pii_masking:
    enabled: true
    entities: [ssn, credit_card, email, phone, ip_address]
    mask: "[REDACTED]"
```

Supported patterns: SSN, credit card, email, phone, IP address, passport number. Masking runs on both **input** (before prompt rendering) and **output** (before saving to logs).

---

## Alignment Policies

Define output rules in `project.yml` or `policies.yml` — Ryva checks every agent output automatically.

```yaml
policies:
  - name: no-profanity
    check: keyword_forbidden
    keywords: [badword1, badword2]
    severity: error

  - name: must-be-json
    check: json_field_required
    field: summary
    severity: error

  - name: length-check
    check: max_length
    max: 2000
    severity: warning
```

```bash
ryva align                    # Check all agents against policies
ryva align --agent my_agent   # Check a specific agent
```

Rule types: `keyword_forbidden`, `must_contain`, `must_contain_pattern`, `max_length`, `min_length`, `json_field_required`, `json_field_forbidden`.

---

## AI Governance & EU AI Act Compliance

```bash
ryva governance report                     # Full compliance report
ryva governance report --out report.json   # Save machine-readable output
```

Always writes `target/governance_report.json` and `target/governance_report.md`. Exit codes suitable for CI gating:

| Exit Code | Meaning |
|---|---|
| `0` | No high-risk systems — all clear |
| `1` | High-risk systems exist but are tested |
| `2` | High-risk systems exist that are **untested** — critical |

The report includes:
- **EU AI Act checklist** (Articles 9–15): risk management, data provenance, audit logs, documentation, human oversight, adversarial testing, explainability, feedback monitoring, bias testing, policy enforcement
- **AI Bill of Materials**: every agent and pipeline with risk level, test coverage, production run count, and prompt hash
- **Risk distribution**: HIGH / MEDIUM / LOW classification based on domain keywords (medical, financial, legal, biometric, etc.)

---

## Outcome Feedback

Close the loop between production runs and model quality.

```bash
ryva feedback record --run-id abc123 --outcome correct --note "nailed it" --annotator alice
ryva feedback report                     # Accuracy metrics by agent
ryva feedback report --agent my_agent
```

Outcomes: `correct`, `incorrect`, `partial`, `unknown`.

---

## Drift Monitoring & Retraining

Track output quality over time and detect when a model starts degrading.

```bash
ryva retrain drift my_agent              # Analyse quality score drift
ryva retrain drift my_agent --threshold 0.10
ryva retrain trigger my_agent --trigger drift --reason "score drop detected"
ryva retrain history                     # All retraining jobs
ryva retrain history --agent my_agent
```

`DriftMonitor` compares recent scores to a baseline window using a sliding-window mean. The `drift` command exits `1` when drift is detected — wire it directly into CI.

Trigger types: `manual`, `drift`, `feedback`, `scheduled`.

---

## Edge Telemetry

Collect inference telemetry from edge devices for fleet-wide monitoring.

```bash
ryva edge status                         # All devices
ryva edge status --device device-01      # Single device
ryva edge report                         # Aggregate fleet report
ryva edge report --out edge.json
ryva edge flush device-01                # Clear local cache after upload
```

Each device tracks: latency, token counts, error rate, agent breakdown, and timestamps.

---

## Vision Lineage

Record and audit vision model inference results alongside human annotations.

```bash
ryva vision lineage show sha256:abc123   # All records for an image hash
ryva vision lineage report               # Fleet-wide vision summary
ryva vision lineage report --out vision.json
```

`compute_agreement()` scores inference vs. annotation label alignment using semantic similarity, enabling automated QA for labeling pipelines.

---

## State Backends

Ryva stores runs, lineage, and feedback as local JSON files by default. Swap in Postgres or S3 for team deployments:

```python
from ryva.backends import get_backend

# Local (default)
backend = get_backend({"type": "local"}, root=project_root)

# Postgres
backend = get_backend({"type": "postgres", "dsn": "postgresql://user:pass@host/db"})

# S3
backend = get_backend({"type": "s3", "bucket": "my-bucket", "region": "us-east-1"})
```

All backends implement the same `StateBackend` interface: `write`, `read`, `list_keys`, `delete`, `exists`.

---

## Cost Intelligence

```bash
ryva cost                                   # This month
ryva cost --month 2026-04                   # Specific month
ryva forecast                               # Budget projection
ryva compare my_agent --providers anthropic,openai,gemini,ollama
ryva compat --agent my_agent                # Find cheapest model that passes tests
```

Set budget limits in `project.yml`:

```yaml
budget:
  monthly_limit_usd: 10.00
  alert_threshold: 0.8
  agents:
    my_agent: 2.00
```

Ryva warns when approaching limits and blocks runs when exceeded.

---

## Project Structure

```
my-ai-project/
├── agents/               # LLM agent definitions (.yml)
├── prompts/              # Jinja2 prompt templates (.j2)
├── macros/               # Reusable prompt macros (.j2)
├── tools/                # Tool definitions (.yml) + implementations (.py)
├── pipelines/            # Multi-agent pipeline definitions (.yml)
├── models/               # ML model definitions (.yml) + implementations (.py)
├── vector_stores/        # Vector store definitions (.yml) + implementations (.py)
├── multimodal/           # Vision/audio/document model definitions
├── tests/                # All test cases (.yml)
├── evals/                # LLM-as-judge eval scorers
├── policies.yml          # Output alignment policies (optional)
├── lineage/              # Signed run records (gitignored)
├── retraining/           # Drift scores and retraining jobs
├── edge_telemetry/       # Edge device telemetry
├── vision_lineage/       # Vision inference and annotation records
├── target/               # Compiled output (gitignored)
├── logs/                 # Run history and feedback (gitignored)
└── project.yml           # Project config
```

---

## CI/CD Integration

```yaml
name: Ryva CI
on: [push, pull_request]
jobs:
  ryva:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ryva
      - run: ryva compile
      - run: ryva test --concurrency 10
      - run: ryva governance report      # exits 2 if high-risk systems are untested
      - run: ryva align
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          RYVA_SECRET: ${{ secrets.RYVA_SECRET }}
```

---

## Full CLI Reference

```bash
# Core
ryva init <name>                              # Initialize a new project
ryva compile                                  # Validate and compile
ryva run --agent <name> --input '{}'          # Run an agent
ryva run --pipeline <name> --input '{}'       # Run a pipeline
ryva check                                    # Lint without output
ryva dag                                      # Show dependency graph

# Testing
ryva test                                     # Run all tests (parallel)
ryva test --concurrency <n>                   # Set worker count (1–20)
ryva test --agent <name>
ryva test --pipeline <name>
ryva test --model <name>
ryva test --vector <name>
ryva test --multimodal <name>
ryva test --adversarial [--categories a,b]
ryva test --hallucination
ryva test --rag
ryva test --regression
ryva test --memory
ryva test --finetune
ryva test --fuzz
ryva eval --agent <name>
ryva baseline <agent>                         # Snapshot baseline for regression

# Lineage & Audit
ryva lineage show <run-id>
ryva lineage search [--agent] [--since] [--status] [--limit]
ryva lineage verify [run-id | --all]
ryva lineage export <run-id> [--out file]
ryva diff <run-id-a> <run-id-b>
ryva traces list
ryva traces show <run-id>
ryva history

# Alignment & Governance
ryva align [--agent <name>]
ryva governance report [--out file]

# Feedback
ryva feedback record --run-id <id> --outcome <correct|incorrect|partial|unknown>
ryva feedback report [--agent <name>]

# Drift & Retraining
ryva retrain trigger <agent> [--trigger type] [--reason text]
ryva retrain history [--agent <name>]
ryva retrain drift <agent> [--threshold 0.15]

# Edge Telemetry
ryva edge status [--device <id>]
ryva edge flush <device-id>
ryva edge report [--out file]

# Vision
ryva vision lineage show <image-hash>
ryva vision lineage report [--out file]

# Cost
ryva cost [--month YYYY-MM]
ryva forecast
ryva compare <agent> --providers a,b,c [--runs n]
ryva compat --agent <name> [--provider name]

# Registry & Docs
ryva registry list / add / info / remove
ryva docs generate
ryva docs serve [--port 8080]
ryva list agents / tools / prompts
ryva benchmark [name] [--model] [--provider]
```

---

## Supported Providers

| Provider | Status |
|---|---|
| Anthropic (Claude) | ✅ Supported |
| OpenAI (GPT) | ✅ Supported |
| Ollama (local models) | ✅ Supported |
| Google Gemini | ✅ Supported |
| AWS Bedrock | 🔜 Coming soon |

---

## Ryva Cloud

[Ryva Cloud](https://ryva-dashboard.vercel.app) provides hosted infrastructure for teams:

- Run history and observability dashboard
- Team management with RBAC (Owner, Admin, Member, Viewer)
- Audit logs and cost tracking
- Bring your own API key or use Ryva-hosted execution
- Self-hosted deployment available

---

## Roadmap

- **Phase 1** ✅ — Core CLI: init, compile, run, test, docs, dag
- **Phase 2** ✅ — Evals, multi-provider, plugins, macros
- **Phase 3** ✅ — Ryva Cloud: hosted runtime, team dashboards, observability
- **Phase 4** ✅ — Enterprise: teams, RBAC, audit logs, self-hosted, compliance
- **Phase 5** ✅ — Pipeline, ML model, vector store, and multimodal testing
- **Phase 6** ✅ — Cost intelligence, provider comparison, adversarial testing
- **Phase 7** ✅ — Parallel test execution, PII masking, HMAC lineage, semantic embeddings, state backends, governance exit codes, edge telemetry, drift monitoring, vision lineage
- **Phase 8** 🔜 — Fine-tune pipeline automation, online learning hooks, multi-tenant edge fleet management

---

## Contributing

```bash
git clone https://github.com/ryva-dev/ryva.git
cd ryva
uv sync
uv pip install -e .
ryva --help
```

Please open an issue before submitting a large PR.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

<p align="center">Built with &#x1F90D; for AI engineers tired of building in the dark.</p>
