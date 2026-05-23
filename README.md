# Ryva

> The engineering framework for agentic AI.

Ryva is an opinionated, open-source framework that brings structure, testing, and documentation to the way engineers build and deploy AI systems.

---

## Why Ryva?

Building production AI systems today means managing scattered prompt files, undocumented agents, no test coverage, and zero visibility into how components depend on each other. Ryva fixes that.

With Ryva, every agent, model, pipeline, and vector store is a versioned, testable, documented file. Dependencies are explicit. Tests are built in. Docs generate automatically. And your whole project compiles before it runs.

---

## Features

- **Structured projects** — agents, prompts, tools, pipelines, ML models, and vector stores as first-class files
- **`ref()` system** — explicit dependency resolution between all components
- **Universal testing** — LLM agents, pipelines, ML models, vector stores, and multimodal models
- **LLM-as-judge evals** — automated quality scoring for agent outputs
- **Auto-generated docs** — always up to date, always shipped with your project
- **DAG visualization** — see exactly how your components depend on each other
- **Provider agnostic** — Anthropic, OpenAI, Ollama, Gemini supported today
- **Plugin system** — extend Ryva with custom test types and providers
- **Macro system** — reusable Jinja2 prompt components
- **Local first** — works entirely offline, cloud deployment optional

---

## Quickstart

### Install

```bash
pip install ryva
```

### Initialize a project

```bash
ryva init my-ai-project
cd my-ai-project
```

### Set your API key

```bash
export ANTHROPIC_API_KEY=your_key_here
```

### Compile

```bash
ryva compile
```

### Run an agent

```bash
ryva run --agent summarizer_agent --input '{"text": "Your text here"}'
```

### Run a pipeline

```bash
ryva run --pipeline summarize_pipeline --input '{"text": "Your text here"}'
```

### Run all tests

```bash
ryva test
```

### Generate docs

```bash
ryva docs generate
ryva docs serve
```

---

## What Ryva Can Test

```bash
ryva test                              # Run everything
ryva test --agent my_agent             # LLM agent tests
ryva test --pipeline my_pipeline       # Multi-step pipeline tests
ryva test --model my_model             # ML model tests (accuracy, drift, latency)
ryva test --vector my_store            # Vector store tests (relevance, recall)
ryva test --multimodal my_model        # Vision, document, audio model tests
ryva test --adversarial                # Adversarial and security tests
ryva test --adversarial --categories prompt_injection,edge_cases,schema_breaking
ryva eval --agent my_agent             # LLM-as-judge quality scoring
```

### Adversarial Test Categories

| Category | What It Tests |
|---|---|
| `prompt_injection` | Instruction override, system prompt leak, role switching |
| `edge_cases` | Empty input, very long input, special characters, unicode, null bytes |
| `schema_breaking` | Requests to change output format or inject extra fields |

---

## Cost Intelligence

```bash
ryva cost                              # Show cost report for this month
ryva cost --month 2026-04              # Show cost for a specific month
ryva compare my_agent --providers anthropic,openai,gemini,ollama
ryva compat --agent my_agent           # Find cheapest model that passes all tests
```

Set budget limits in `project.yml`:

```yaml
budget:
  monthly_limit_usd: 10.00
  alert_threshold: 0.8
  agents:
    my_agent: 2.00
```

Ryva warns you when approaching your limit and blocks runs when exceeded.

---

## Project Structure

```
my-ai-project/
├── agents/               # LLM agent definitions (.yml)
├── prompts/              # Prompt templates (.j2)
├── tools/                # Tool definitions (.yml) + implementations (.py)
├── pipelines/            # Multi-agent pipelines (.yml)
├── models/               # ML model definitions (.yml) + implementations (.py)
├── vector_stores/        # Vector store definitions (.yml) + implementations (.py)
├── multimodal/           # Vision/audio/document model definitions
├── tests/                # All test cases
│   ├── agents/
│   ├── pipelines/
│   ├── models/
│   ├── vector_stores/
│   └── multimodal/
├── evals/                # LLM-as-judge eval scorers
├── macros/               # Reusable Jinja2 prompt macros
├── target/               # Compiled output (gitignored)
├── logs/                 # Run history (gitignored)
└── project.yml           # Project config
```

---

## Defining an Agent

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
tags:
  - text
  - summarization
```

---

## Testing an Agent

```yaml
agent: ref(agents/summarizer_agent)
type: schema
cases:
  - name: basic summarization
    input:
      text: "Ryva brings engineering discipline to agentic AI."
      max_sentences: 2
    expect:
      output.summary:
        type: str
        min_length: 10
```

---

## Testing an ML Model

```yaml
model: my_model
type: accuracy
cases:
  - name: classification accuracy
    inputs: ["short text", "a much longer piece of text here"]
    expected: ["short", "long"]
    threshold: 0.9
```

---

## Testing a Vector Store

```yaml
store: my_store
type: relevance
cases:
  - name: semantic search relevance
    query: "agentic AI framework"
    threshold: 0.3
    top_k: 5
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
      - run: ryva test
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

---

## CLI Reference

```bash
ryva init <name>                          # Initialize a new project
ryva compile                              # Validate and compile
ryva run --agent <name> --input '{}'      # Run an agent
ryva run --pipeline <name> --input '{}'   # Run a pipeline
ryva test                                 # Run all tests
ryva test --agent <name>                  # Test a specific agent
ryva test --pipeline <name>               # Test a specific pipeline
ryva test --model <name>                  # Test an ML model
ryva test --vector <name>                 # Test a vector store
ryva test --multimodal <name>             # Test a multimodal model
ryva test --adversarial                   # Run adversarial and security tests
ryva eval --agent <name>                  # Run LLM-as-judge evals
ryva cost                                 # Show cost report
ryva compare <agent> --providers a,b,c    # Compare across providers
ryva compat --agent <name>                # Find cheapest compatible model
ryva dag                                  # Show dependency graph
ryva docs generate                        # Generate documentation
ryva docs serve                           # Serve docs in browser
ryva check                                # Lint without output
ryva list agents                          # List all agents
ryva list tools                           # List all tools
ryva list prompts                         # List all prompts
ryva history                              # Show run history
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
- **Phase 2** ✅ — Evals, multi-provider, plugins, macros, VS Code extension
- **Phase 3** ✅ — Ryva Cloud: hosted runtime, team dashboards, observability
- **Phase 4** ✅ — Enterprise: teams, RBAC, audit logs, self-hosted, compliance
- **Phase 5** ✅ — Pipeline, ML model, vector store, and multimodal testing
- **Phase 6** ✅ — Cost intelligence, provider comparison, adversarial testing
- **Phase 7** 🔜 — RAG pipeline testing, fine-tune evaluation, model registry

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

<p align="center">Built with 🤍 for AI engineers tired of building in the dark.</p>