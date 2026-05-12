# my-first-project

> Built with [Ryva](https://github.com/ryva-dev/ryva) — the engineering framework for agentic AI.

## Getting Started

```bash
# Set your API key
export ANTHROPIC_API_KEY=your_key_here

# Compile the project
ryva compile

# Run the example agent
ryva run --agent summarizer_agent --input '{"text": "Your text here"}'

# Run tests
ryva test

# Generate docs
ryva docs generate
```

## Project Structure

```
agents/       # Agent definitions
prompts/      # Prompt templates
tools/        # Tool implementations
pipelines/    # Multi-agent pipelines
tests/        # Behavioral tests
evals/        # Custom eval scorers
macros/       # Reusable Jinja2 macros
```
