from __future__ import annotations
from pathlib import Path
from ryva.utils import console
from rich.panel import Panel
from ruamel.yaml import YAML

yaml = YAML()
yaml.default_flow_style = False


def scaffold(name: str, dest: Path) -> None:
    console.print(Panel(f"[bold cyan]Initializing Ryva project:[/bold cyan] [bold]{name}[/bold]", expand=False))

    dest.mkdir(parents=True, exist_ok=True)

    dirs = ["agents", "prompts", "tools", "pipelines", "tests/summarizer_agent", "evals", "macros", "target", "logs"]
    for d in dirs:
        (dest / d).mkdir(parents=True, exist_ok=True)
        console.print(f"  [dim]created {d}/[/dim]")

    _write_project_yml(dest, name)
    _write_example_agent(dest)
    _write_example_prompt(dest)
    _write_example_tool(dest)
    _write_example_pipeline(dest)
    _write_example_test(dest)
    _write_gitignore(dest)
    _write_readme(dest, name)

    console.print(f"\n[bold green]✓ Project '{name}' created at {dest}[/bold green]")
    console.print(f"\nNext steps:")
    console.print(f"  [cyan]cd {{name}}[/cyan]")
    console.print(f"  [cyan]export ANTHROPIC_API_KEY=your_key[/cyan]")
    console.print(f"  [cyan]ryva compile[/cyan]")


def _write_project_yml(dest: Path, name: str):
    data = {
        "name": name,
        "version": "0.1.0",
        "providers": {
            "default": "anthropic",
            "anthropic": {
                "model": "claude-sonnet-4-20250514",
                "api_key": "{{ env_var('ANTHROPIC_API_KEY') }}"
            }
        },
        "runtime": {
            "max_tokens": 4096,
            "timeout_ms": 10000,
            "retries": 2
        },
        "targets": {
            "dev": {"type": "local"}
        }
    }
    with open(dest / "project.yml", "w") as f:
        yaml.dump(data, f)
    console.print(f"  [dim]created project.yml[/dim]")


def _write_example_agent(dest: Path):
    data = {
        "name": "summarizer_agent",
        "version": "1.0.0",
        "description": "Summarizes a given piece of text into a concise output.",
        "prompt": "ref(prompts/summarizer)",
        "tools": [],
        "input": {
            "schema": {
                "text": {"type": "str", "required": True},
                "max_sentences": {"type": "int", "default": 3}
            }
        },
        "output": {
            "schema": {
                "summary": {"type": "str"},
                "word_count": {"type": "int"}
            }
        },
        "memory": {"strategy": "none"},
        "tags": ["text", "summarization"],
        "meta": {"owner": "your-team"}
    }
    with open(dest / "agents" / "summarizer_agent.yml", "w") as f:
        yaml.dump(data, f)
    console.print(f"  [dim]created agents/summarizer_agent.yml[/dim]")


def _write_example_prompt(dest: Path):
    template = (
        "You are a precise summarization assistant.\n\n"
        "Summarize the following text in {{ input.max_sentences }} sentences or fewer.\n"
        "Be concise, accurate, and preserve the key ideas.\n\n"
        "Text:\n"
        "{{ input.text }}\n\n"
        "Respond with a JSON object in this exact format:\n"
        "{\n"
        '  "summary": "your summary here",\n'
        '  "word_count": <integer word count of your summary>\n'
        "}\n"
    )
    (dest / "prompts" / "summarizer.j2").write_text(template)
    console.print(f"  [dim]created prompts/summarizer.j2[/dim]")
def _write_example_tool(dest: Path):
    data = {
        "name": "word_counter",
        "version": "1.0.0",
        "description": "Counts the number of words in a string.",
        "implementation": "tools/word_counter.py",
        "function": "run",
        "input": {
            "schema": {
                "text": {"type": "str", "required": True}
            }
        },
        "output": {
            "schema": {
                "count": {"type": "int"}
            }
        }
    }
    with open(dest / "tools" / "word_counter.yml", "w") as f:
        yaml.dump(data, f)

    (dest / "tools" / "word_counter.py").write_text(
        "def run(text: str) -> dict:\n"
        "    return {'count': len(text.split())}\n"
    )
    console.print(f"  [dim]created tools/word_counter.yml + tools/word_counter.py[/dim]")


def _write_example_pipeline(dest: Path):
    data = {
        "name": "summarize_pipeline",
        "description": "Summarizes input text end-to-end.",
        "input": {
            "schema": {"text": {"type": "str", "required": True}}
        },
        "steps": [
            {
                "name": "summarize",
                "agent": "ref(agents/summarizer_agent)",
                "input": {"text": "{{ input.text }}", "max_sentences": 3}
            }
        ],
        "output": {
            "summary": "{{ steps.summarize.output.summary }}"
        }
    }
    with open(dest / "pipelines" / "summarize_pipeline.yml", "w") as f:
        yaml.dump(data, f)
    console.print(f"  [dim]created pipelines/summarize_pipeline.yml[/dim]")


def _write_example_test(dest: Path):
    data = {
        "agent": "ref(agents/summarizer_agent)",
        "type": "schema",
        "cases": [
            {
                "name": "basic summarization",
                "input": {
                    "text": "Ryva is a framework for building, testing, and deploying agentic AI systems. It brings the same engineering discipline to AI that dbt brought to data transformation.",
                    "max_sentences": 2
                },
                "expect": {
                    "output.summary": {"type": "str", "min_length": 10},
                    "output.word_count": {"type": "int", "range": [1, 500]}
                }
            }
        ]
    }
    with open(dest / "tests" / "summarizer_agent" / "test_schema.yml", "w") as f:
        yaml.dump(data, f)
    console.print(f"  [dim]created tests/summarizer_agent/test_schema.yml[/dim]")


def _write_gitignore(dest: Path):
    (dest / ".gitignore").write_text(
        "target/\nlogs/\n.env\n__pycache__/\n*.pyc\n.venv/\n"
    )
    console.print(f"  [dim]created .gitignore[/dim]")


def _write_readme(dest: Path, name: str):
    content = (
        f"# {name}\n\n"
        "> Built with [Ryva](https://github.com/ryva-dev/ryva) — the engineering framework for agentic AI.\n\n"
        "## Getting Started\n\n"
        "```bash\n"
        "# Set your API key\n"
        "export ANTHROPIC_API_KEY=your_key_here\n\n"
        "# Compile the project\n"
        "ryva compile\n\n"
        "# Run the example agent\n"
        "ryva run --agent summarizer_agent --input '{\"text\": \"Your text here\"}'\n\n"
        "# Run tests\n"
        "ryva test\n\n"
        "# Generate docs\n"
        "ryva docs generate\n"
        "```\n\n"
        "## Project Structure\n\n"
        "```\n"
        "agents/       # Agent definitions\n"
        "prompts/      # Prompt templates\n"
        "tools/        # Tool implementations\n"
        "pipelines/    # Multi-agent pipelines\n"
        "tests/        # Behavioral tests\n"
        "evals/        # Custom eval scorers\n"
        "macros/       # Reusable Jinja2 macros\n"
        "```\n"
    )
    (dest / "README.md").write_text(content)
    console.print(f"  [dim]created README.md[/dim]")