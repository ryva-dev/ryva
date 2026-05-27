from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from ryva.utils import console, load_manifest

# Keywords that indicate EU AI Act high-risk domains (Annex III)
_HIGH_RISK_KEYWORDS = frozenset({
    "medical", "health", "clinical", "diagnostic", "patient", "hospital",
    "financial", "credit", "loan", "fraud", "insurance",
    "legal", "law", "court", "judge", "sentencing", "parole",
    "recruitment", "hiring", "employment", "hr", "performance",
    "safety", "autonomous", "critical", "infrastructure",
    "biometric", "face", "recognition", "surveillance",
    "education", "exam", "assessment", "student", "grading",
    "police", "law enforcement", "border", "immigration", "asylum",
    "welfare", "social", "benefit", "eligibility",
})

_MEDIUM_RISK_KEYWORDS = frozenset({
    "customer", "support", "chatbot", "assistant",
    "recommendation", "suggest", "decision", "classify",
    "generate", "content", "marketing", "sales", "sentiment",
})


def _score_risk(agent: dict, has_tests: bool, has_adversarial: bool) -> tuple[str, list[str]]:
    """Assign EU AI Act risk level and reasons to an agent."""
    text = f"{agent.get('description', '')} {agent.get('name', '')}".lower()
    high_matches = [kw for kw in _HIGH_RISK_KEYWORDS if kw in text]
    medium_matches = [kw for kw in _MEDIUM_RISK_KEYWORDS if kw in text]
    reasons: list[str] = []

    if not has_tests:
        reasons.append("No test cases — untested AI system")
    if not has_adversarial:
        reasons.append("No adversarial tests — robustness not validated")

    if high_matches:
        reasons.append(f"High-risk domain indicators: {', '.join(high_matches[:3])}")
        return "HIGH", reasons

    if medium_matches:
        reasons.append(f"General-purpose AI indicators: {', '.join(medium_matches[:2])}")
        return "MEDIUM", reasons

    return "LOW", reasons or ["No high-risk domain indicators detected"]


def generate_report(root: Path) -> dict:
    """Generate a full AI governance and compliance report."""
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})
    tools = manifest.get("tools", {})
    pipelines = manifest.get("pipelines", {})
    project = manifest.get("project", {})
    prompt_hashes = manifest.get("prompt_hashes", {})

    lineage_dir = root / "lineage"
    total_runs = len(list(lineage_dir.glob("*.json"))) if lineage_dir.exists() else 0

    feedback_dir = root / "logs" / "feedback"
    feedback_count = len(list(feedback_dir.glob("*.json"))) if feedback_dir.exists() else 0

    bom_entries: list[dict] = []
    risk_summary = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for name, agent in agents.items():
        tests_dir = root / "tests" / name
        has_tests = tests_dir.exists() and any(tests_dir.glob("*.yml"))
        has_adversarial = any((root / "tests").glob("adversarial*"))

        agent_runs: list[dict] = []
        if lineage_dir.exists():
            for f in lineage_dir.glob("*.json"):
                try:
                    r = json.loads(f.read_text())
                    if r.get("agent") == name:
                        agent_runs.append(r)
                except (json.JSONDecodeError, OSError):
                    continue

        risk_level, risk_reasons = _score_risk(agent, has_tests, has_adversarial)
        risk_summary[risk_level] += 1

        prompt_ref = agent.get("prompt", "")
        prompt_name = prompt_ref.replace("ref(prompts/", "").replace(")", "")

        bom_entries.append({
            "name": name,
            "type": "agent",
            "description": agent.get("description", ""),
            "model": agent.get("model", ""),
            "version": agent.get("version", ""),
            "prompt_template": prompt_ref,
            "prompt_hash": prompt_hashes.get(prompt_name, ""),
            "tools_used": agent.get("tools", []),
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
            "tested": has_tests,
            "adversarial_tested": has_adversarial,
            "total_production_runs": len(agent_runs),
        })

    for name, pipeline in pipelines.items():
        bom_entries.append({
            "name": name,
            "type": "pipeline",
            "description": pipeline.get("description", ""),
            "steps": [s.get("name") for s in pipeline.get("steps", [])],
            "risk_level": "MEDIUM",
            "tested": (root / "tests" / f"{name}.yml").exists(),
            "adversarial_tested": False,
            "total_production_runs": 0,
        })

    has_policies = bool(project.get("policies")) or (root / "policies.yml").exists()
    has_tests_any = any(e.get("tested") for e in bom_entries if e["type"] == "agent")
    has_adversarial_any = any(e.get("adversarial_tested") for e in bom_entries)
    docs_dir = root / "target" / "docs"
    has_docs = docs_dir.exists() and any(docs_dir.glob("*.md"))

    checklist = _eu_ai_act_checklist(
        root=root,
        has_policies=has_policies,
        has_lineage=total_runs > 0,
        has_feedback=feedback_count > 0,
        has_tests=has_tests_any,
        has_adversarial=has_adversarial_any,
        has_docs=has_docs,
        high_risk_count=risk_summary["HIGH"],
    )
    score = sum(1 for item in checklist if item["status"] == "✓")

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "project": project.get("name", root.name),
        "ryva_version": manifest.get("ryva_version", "0.1.0"),
        "summary": {
            "total_ai_systems": len(bom_entries),
            "agents": len(agents),
            "pipelines": len(pipelines),
            "tools": len(tools),
            "risk_distribution": risk_summary,
            "total_production_runs": total_runs,
            "feedback_entries": feedback_count,
            "eu_ai_act_compliance_score": f"{score}/{len(checklist)}",
            "prompt_versions_tracked": len(prompt_hashes),
        },
        "risk_assessment": {
            "high_risk_systems": [
                e["name"] for e in bom_entries if e.get("risk_level") == "HIGH"
            ],
            "untested_systems": [
                e["name"] for e in bom_entries if not e.get("tested")
            ],
            "no_adversarial_testing": [
                e["name"] for e in bom_entries
                if e["type"] == "agent" and not e.get("adversarial_tested")
            ],
        },
        "eu_ai_act_checklist": checklist,
        "bill_of_materials": bom_entries,
        "prompt_version_registry": prompt_hashes,
    }


def _eu_ai_act_checklist(
    root: Path,
    has_policies: bool,
    has_lineage: bool,
    has_feedback: bool,
    has_tests: bool,
    has_adversarial: bool,
    has_docs: bool,
    high_risk_count: int,
) -> list[dict]:
    def item(article: str, requirement: str, met: bool, guidance: str) -> dict:
        return {
            "article": article,
            "requirement": requirement,
            "status": "✓" if met else "✗",
            "guidance": "" if met else guidance,
        }

    return [
        item(
            "Art. 9",
            "Risk management system for high-risk AI",
            high_risk_count == 0 or has_tests,
            "Add test cases for high-risk agents: ryva test --agent <name>",
        ),
        item(
            "Art. 10",
            "Training data provenance documented",
            (root / "data").exists() or (root / "datasets").exists(),
            "Create a data/ directory and document training data sources.",
        ),
        item(
            "Art. 12",
            "Audit logs and decision records",
            has_lineage,
            "Run agents via ryva run to generate lineage records automatically.",
        ),
        item(
            "Art. 13",
            "Technical documentation generated",
            has_docs,
            "Generate docs with: ryva docs generate",
        ),
        item(
            "Art. 14",
            "Human oversight mechanisms defined",
            has_policies,
            "Define policies in project.yml under 'policies:' or create policies.yml.",
        ),
        item(
            "Art. 15",
            "Adversarial and robustness testing",
            has_adversarial,
            "Run: ryva test --adversarial && ryva test --fuzz",
        ),
        item(
            "Art. 13",
            "Decision explainability via lineage chain",
            has_lineage,
            "Use: ryva lineage show <run-id>",
        ),
        item(
            "Art. 9",
            "Continuous monitoring and outcome feedback",
            has_feedback,
            "Record outcomes with: ryva feedback record --run-id <id> --outcome correct",
        ),
        item(
            "Art. 10",
            "Bias and fairness testing documented",
            has_adversarial and has_tests,
            "Expand test cases to include fairness and demographic parity scenarios.",
        ),
        item(
            "General",
            "Output alignment policies enforced",
            has_policies,
            "Add policies to project.yml then run: ryva align",
        ),
    ]


def show_report(root: Path, out: Path | None = None) -> None:
    report = generate_report(root)

    s = report["summary"]
    risk = s["risk_distribution"]
    console.print(Panel(
        f"[bold cyan]AI Governance Report[/bold cyan] — {report['project']}\n"
        f"[dim]{report['generated_at'][:19].replace('T', ' ')}[/dim]\n\n"
        f"Systems: [bold]{s['total_ai_systems']}[/bold] "
        f"({s['agents']} agents, {s['pipelines']} pipelines, {s['tools']} tools)\n"
        f"Risk: [red]{risk['HIGH']} high[/red] / "
        f"[yellow]{risk['MEDIUM']} medium[/yellow] / "
        f"[green]{risk['LOW']} low[/green]\n"
        f"Runs tracked: [cyan]{s['total_production_runs']}[/cyan]   "
        f"Prompt versions: [cyan]{s['prompt_versions_tracked']}[/cyan]   "
        f"Feedback entries: [cyan]{s['feedback_entries']}[/cyan]\n"
        f"EU AI Act score: [bold]{s['eu_ai_act_compliance_score']}[/bold]",
        expand=False,
    ))

    ra = report["risk_assessment"]
    if ra["high_risk_systems"]:
        console.print(
            f"\n[bold red]⚠  High-Risk Systems:[/bold red] "
            f"{', '.join(ra['high_risk_systems'])}"
        )
    if ra["untested_systems"]:
        console.print(
            f"[bold yellow]⚠  Untested Systems:[/bold yellow] "
            f"{', '.join(ra['untested_systems'])}"
        )

    console.print("\n[bold]EU AI Act Compliance Checklist[/bold]")
    checklist_table = Table(show_header=True, header_style="bold")
    checklist_table.add_column("Article", style="dim")
    checklist_table.add_column("Requirement")
    checklist_table.add_column("", justify="center")
    checklist_table.add_column("Action Required", style="dim")

    for item in report["eu_ai_act_checklist"]:
        color = "green" if item["status"] == "✓" else "red"
        checklist_table.add_row(
            item["article"],
            item["requirement"],
            f"[{color}]{item['status']}[/{color}]",
            item.get("guidance", "")[:70],
        )
    console.print(checklist_table)

    console.print("\n[bold]AI Bill of Materials[/bold]")
    bom_table = Table(show_header=True, header_style="bold")
    bom_table.add_column("Name", style="cyan")
    bom_table.add_column("Type", style="dim")
    bom_table.add_column("Model", style="dim")
    bom_table.add_column("Risk")
    bom_table.add_column("Tested", justify="center")
    bom_table.add_column("Runs", justify="right")
    bom_table.add_column("Prompt Hash", style="dim")

    for entry in report["bill_of_materials"]:
        risk_level = entry.get("risk_level", "—")
        risk_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(risk_level, "dim")
        tested = "[green]✓[/green]" if entry.get("tested") else "[red]✗[/red]"
        bom_table.add_row(
            entry["name"],
            entry["type"],
            entry.get("model", "—"),
            f"[{risk_color}]{risk_level}[/{risk_color}]",
            tested,
            str(entry.get("total_production_runs", "—")),
            (entry.get("prompt_hash") or "—")[:20],
        )
    console.print(bom_table)

    if out:
        out.write_text(json.dumps(report, indent=2))
        console.print(f"\n[green]✓ Full report saved to {out}[/green]")
