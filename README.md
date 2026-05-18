# Ryva

> The engineering framework for agentic AI.

Ryva is an opinionated, open-source framework that brings structure, testing, and documentation to the way engineers build and deploy AI agents.

---

## Why Ryva?

Building production AI agents today means managing scattered prompt files, undocumented tool logic, no test coverage, and zero visibility into how agents depend on each other. Ryva fixes that.

With Ryva, every agent is a versioned, testable, documented file. Dependencies are explicit. Tests are built in. Docs generate automatically. And your whole project compiles before it runs.

---

## Features

- **Structured projects** — agents, prompts, tools, and pipelines as first-class files
- **`ref()` system** — explicit dependency resolution between agents, prompts, and tools
- **Built-in testing** — schema, latency, and behavioral tests out of the box
- **Auto-generated docs** — always up to date, always shipped with your project
- **DAG visualization** — see exactly how your agents depend on each other
- **Provider agnostic** — Anthropic and OpenAI supported today, more coming
- **Local first** — works entirely offline, cloud deployment coming in a future release

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

### Run tests

```bash
ryva test
```

### Generate docs

```bash
ryva docs generate
```

---

## Project Structure

```
my-ai-project/
├── agents/               # Agent definitions (.yml)
├── prompts/              # Prompt templates (.j2)
├── tools/                # Tool definitions (.yml) + implementations (.py)
├── pipelines/            # Multi-agent pipelines (.yml)
├── tests/                # Behavioral test cases (.yml)
├── evals/                # Custom eval scorers (.py)
├── macros/               # Reusable Jinja2 prompt macros
├── target/               # Compiled output (gitignored)
├── logs/                 # Run history (gitignored)
└── project.yml           # Project config
```

---

## Defining an Agent

```yaml
# agents/summarizer_agent.yml
name: summarizer_agent
version: "1.0.0"
description: "Summarizes a given piece of text into a concise output."

prompt: ref(prompts/summarizer)
tools: []

input:
  schema:
    text:
      type: str
      required: true
    max_sentences:
      type: int
      default: 3

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

## Writing a Prompt

```jinja2
{# prompts/summarizer.j2 #}
You are a precise summarization assistant.

Summarize the following text in {{ input.max_sentences }} sentences or fewer.

Text:
{{ input.text }}

Respond with a JSON object:
{
  "summary": "your summary here",
  "word_count": <integer>
}
```

---

## Writing Tests

```yaml
# tests/summarizer_agent/test_schema.yml
agent: ref(agents/summarizer_agent)
type: schema

cases:
  - name: "basic summarization"
    input:
      text: "Ryva brings engineering discipline to agentic AI."
      max_sentences: 2
    expect:
      output.summary:
        type: str
        min_length: 10
      output.word_count:
        type: int
        range: [1, 500]
```

---

## CLI Reference

```bash
ryva init <name>                        # Initialize a new project
ryva compile                            # Validate and compile the project
ryva run --agent <name> --input '{}'    # Run an agent locally
ryva test                               # Run all tests
ryva test --agent <name>                # Run tests for a specific agent
ryva dag                                # Show the full dependency graph
ryva dag --agent <name>                 # Show DAG for a specific agent
ryva docs generate                      # Generate markdown documentation
ryva check                              # Lint without writing output
ryva list agents                        # List all agents
ryva list tools                         # List all tools
ryva list prompts                       # List all prompts
ryva history                            # Show recent run history
```

---

## Supported Providers

| Provider | Status |
|---|---|
| Anthropic (Claude) | ✅ Supported |
| OpenAI (GPT) | ✅ Supported |
| Ollama (local models) | 🔜 Coming in Phase 2 |
| Google Gemini | 🔜 Coming in Phase 2 |
| AWS Bedrock | 🔜 Coming in Phase 2 |

---
## CI/CD Integration

Add Ryva to your GitHub Actions pipeline in seconds. Create `.github/workflows/ryva.yml`:

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

Add `ANTHROPIC_API_KEY` to your GitHub repo secrets and you're done. Ryva will validate and test your agents on every pull request.

A full template with docs generation is available at [`templates/ryva-ci.yml`](templates/ryva-ci.yml).

## Roadmap

- **Phase 1** ✅ — Core CLI: init, compile, run, test, docs, dag
- **Phase 2** 🔜 — Eval framework, more providers, plugin system, interactive docs
- **Phase 3** 🔜 — Ryva Cloud: hosted runtime, team dashboards, CI integration
- **Phase 4** 🔜 — Enterprise: SSO, governance, self-hosted, compliance

---

## Contributing

Ryva is in early development and contributions are very welcome.

```bash
git clone https://github.com/ryva-dev/ryva.git
cd ryva
uv sync
uv pip install -e .
ryva --help
```

Please open an issue before submitting a large PR so we can discuss the approach.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

<p align="center">Built with 🤍 for AI engineers tired of building in the dark.</p>
