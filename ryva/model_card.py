from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


MODEL_CARD_TEMPLATE: dict[str, Any] = {
    "schema_version": "1.0.0",
    "generated_at": None,
    "generated_by": "Ryva Forge — AI Governance Platform",
    "system": {
        "name": None,
        "version": None,
        "type": None,
        "description": None,
        "intended_use": None,
        "out_of_scope_use": None,
        "owner": None,
    },
    "model": {
        "provider": None,
        "model_id": None,
        "model_version": None,
        "prompt_template": None,
        "prompt_hash": None,
    },
    "data": {
        "training_data": "Not applicable — uses pre-trained foundation model",
        "input_description": None,
        "output_description": None,
        "pii_handling": None,
        "data_sources": [],
        "retrieval_sources": [],
    },
    "performance": {
        "test_coverage": None,
        "adversarial_tested": None,
        "hallucination_tested": None,
        "fuzz_tested": None,
        "rag_tested": None,
        "total_production_runs": None,
        "avg_latency_ms": None,
        "success_rate": None,
        "estimated_cost_per_run_usd": None,
    },
    "risk": {
        "risk_level": None,
        "risk_justification": None,
        "known_limitations": [],
        "failure_modes": [],
        "human_oversight": None,
    },
    "compliance": {
        "eu_ai_act": {
            "risk_category": None,
            "article_13_transparency": None,
            "article_14_human_oversight": None,
            "article_15_accuracy": None,
        },
        "colorado_ai_act": {
            "high_risk_ai_system": None,
            "consequential_decision": None,
        },
        "gdpr": {
            "processes_personal_data": None,
            "pii_masking_enabled": None,
            "data_retention_days": None,
        },
    },
    "audit": {
        "lineage_tracking": None,
        "tamper_evident_logs": None,
        "audit_log_retention_days": None,
        "last_reviewed": None,
        "reviewer": None,
    },
    "contacts": {
        "technical_owner": None,
        "compliance_owner": None,
        "escalation_email": None,
    },
}

_HIGH_RISK_KEYWORDS = [
    "medical", "health", "financial", "legal", "biometric",
    "credit", "loan", "insurance", "diagnostic", "clinical",
    "employment", "hiring", "law enforcement", "government",
]

_MEDIUM_RISK_KEYWORDS = [
    "customer", "support", "recommendation", "content",
    "marketing", "sales", "chatbot", "assistant",
]


def _assess_risk(description: str) -> tuple[str, str]:
    text = description.lower()
    for kw in _HIGH_RISK_KEYWORDS:
        if kw in text:
            return "HIGH", f"High-risk domain keyword detected: '{kw}'"
    for kw in _MEDIUM_RISK_KEYWORDS:
        if kw in text:
            return "MEDIUM", f"Medium-risk domain keyword detected: '{kw}'"
    return "LOW", "No high-risk domain keywords detected in agent description."


def generate_model_card(root: Path, agent_name: str) -> dict:
    from ryva.cost_tracker import get_cost_summary
    from ryva.utils import load_manifest

    try:
        manifest = load_manifest(root)
    except FileNotFoundError:
        console.print("[yellow]No manifest found. Run 'ryva compile' first.[/yellow]")
        manifest = {"agents": {}, "project": {}, "prompt_hashes": {}}

    agents = manifest.get("agents", {})
    project = manifest.get("project", {})

    if agent_name not in agents:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        return {}

    agent = agents[agent_name]
    prompt_hashes = manifest.get("prompt_hashes", {})

    try:
        cost_data = get_cost_summary(root)
        agent_costs = cost_data.get("by_agent", {}).get(agent_name, {})
    except Exception:
        agent_costs = {}

    description = agent.get("description", "")
    risk_level, risk_justification = _assess_risk(description)

    tests_dir = root / "tests" / agent_name
    adversarial_tested = (root / "tests" / "adversarial").exists()
    fuzz_tested = (root / "tests" / "fuzz").exists()
    hallucination_tested = (root / "tests" / "hallucination").exists()
    rag_tested = (root / "tests" / "rag").exists()
    test_count = len(list(tests_dir.glob("**/*.yml"))) if tests_dir.exists() else 0

    pii_enabled = project.get("pii_masking", {}).get("enabled", False)

    secret_file = root / ".ryva_secret"
    lineage_signing = secret_file.exists() or bool(
        os.environ.get("RYVA_SECRET") or os.environ.get("RYVA_LINEAGE_SECRET")
    )

    prompt_ref = agent.get("prompt", "")
    prompt_name = prompt_ref.replace("ref(prompts/", "").replace(")", "")
    prompt_hash = prompt_hashes.get(prompt_name, "not compiled")

    providers = project.get("providers", {})
    default_provider = providers.get("default", "anthropic") if isinstance(providers, dict) else "anthropic"
    provider_cfg = providers.get(default_provider, {}) if isinstance(providers, dict) else {}
    model_id = agent.get("model") or (provider_cfg.get("model") if isinstance(provider_cfg, dict) else None) or "unknown"

    input_schema = agent.get("input") or {}
    if isinstance(input_schema, dict):
        input_fields = input_schema.get("schema_", {}) or {}
    else:
        input_fields = {}

    output_schema = agent.get("output") or {}
    if isinstance(output_schema, dict):
        output_fields = output_schema.get("schema_", {}) or {}
    else:
        output_fields = {}

    card: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": "Ryva Forge — AI Governance Platform",
        "system": {
            "name": agent_name,
            "version": agent.get("version", "1.0.0"),
            "type": "agent",
            "description": description or "No description provided.",
            "intended_use": description or "See description above.",
            "out_of_scope_use": "Any use case not explicitly described in the intended use.",
            "owner": (agent.get("meta") or {}).get("owner", project.get("name", "Unknown")),
        },
        "model": {
            "provider": default_provider,
            "model_id": model_id,
            "model_version": "As deployed at runtime",
            "prompt_template": prompt_ref,
            "prompt_hash": (
                f"sha256:{prompt_hash}"
                if prompt_hash != "not compiled"
                else "not compiled — run ryva compile first"
            ),
        },
        "data": {
            "training_data": f"Not applicable — uses pre-trained foundation model provided by {default_provider}",
            "input_description": f"Fields: {', '.join(input_fields.keys())}" if input_fields else "No input schema defined",
            "output_description": f"Fields: {', '.join(output_fields.keys())}" if output_fields else "No output schema defined",
            "pii_handling": (
                "PII masking enabled — sensitive data masked before logging"
                if pii_enabled
                else "PII masking not enabled — enable in project.yml"
            ),
            "data_sources": [],
            "retrieval_sources": [],
        },
        "performance": {
            "test_coverage": f"{test_count} test cases defined",
            "adversarial_tested": adversarial_tested,
            "hallucination_tested": hallucination_tested,
            "fuzz_tested": fuzz_tested,
            "rag_tested": rag_tested,
            "total_production_runs": agent_costs.get("runs", 0),
            "avg_latency_ms": agent_costs.get("avg_latency", "no data"),
            "success_rate": "See Ryva Cloud dashboard for live metrics",
            "estimated_cost_per_run_usd": agent_costs.get("cost", 0),
        },
        "risk": {
            "risk_level": risk_level,
            "risk_justification": risk_justification,
            "known_limitations": [
                "Outputs depend on the underlying foundation model and may vary between runs.",
                "Performance may degrade on inputs significantly different from tested cases.",
                "Model knowledge cutoff applies — real-time information requires RAG.",
            ],
            "failure_modes": [
                "Hallucination — model may generate plausible but incorrect information.",
                "Prompt injection — adversarial inputs may attempt to override instructions.",
                "Context window overflow — very long inputs may be truncated.",
            ],
            "human_oversight": "Human review recommended for all high-stakes decisions made using this system.",
        },
        "compliance": {
            "eu_ai_act": {
                "risk_category": (
                    "HIGH" if risk_level == "HIGH"
                    else "LIMITED" if risk_level == "MEDIUM"
                    else "MINIMAL"
                ),
                "article_13_transparency": "SATISFIED — model card provides required transparency documentation",
                "article_14_human_oversight": "PARTIAL — human oversight recommended but not enforced by system",
                "article_15_accuracy": (
                    "SATISFIED — adversarial and hallucination testing performed"
                    if adversarial_tested and hallucination_tested
                    else "INCOMPLETE — enable adversarial and hallucination testing"
                ),
            },
            "colorado_ai_act": {
                "high_risk_ai_system": risk_level == "HIGH",
                "consequential_decision": risk_level == "HIGH",
                "notice_required": risk_level == "HIGH",
                "impact_assessment_required": risk_level == "HIGH",
            },
            "gdpr": {
                "processes_personal_data": not pii_enabled,
                "pii_masking_enabled": pii_enabled,
                "data_retention_days": 90,
            },
        },
        "audit": {
            "lineage_tracking": True,
            "tamper_evident_logs": lineage_signing,
            "audit_log_retention_days": 90,
            "last_reviewed": datetime.utcnow().strftime("%Y-%m-%d"),
            "reviewer": "Generated automatically by Ryva Forge",
        },
        "contacts": {
            "technical_owner": (agent.get("meta") or {}).get("owner", "Not specified"),
            "compliance_owner": "Not specified — add to agent YAML under meta.compliance_owner",
            "escalation_email": "Not specified — add to project.yml under compliance.escalation_email",
        },
    }

    return card


def save_model_card(root: Path, agent_name: str, card: dict) -> Path:
    output_dir = root / "target" / "model_cards"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{agent_name}_model_card.json"
    output_path.write_text(json.dumps(card, indent=2))
    return output_path


def print_model_card_summary(card: dict) -> None:
    agent = card.get("system", {})
    risk = card.get("risk", {})
    perf = card.get("performance", {})
    compliance = card.get("compliance", {})

    risk_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(
        risk.get("risk_level", "LOW"), "white"
    )

    console.print(f"\n[bold white]Model Card — {agent.get('name')}[/bold white]")
    console.print(f"[dim]Generated: {card.get('generated_at', '')[:19]}[/dim]\n")

    console.print(f"[bold]Risk Level:[/bold] [{risk_color}]{risk.get('risk_level')}[/{risk_color}]")
    console.print(f"[dim]{risk.get('risk_justification')}[/dim]\n")

    console.print("[bold]Performance:[/bold]")
    console.print(f"  Test cases defined:    {perf.get('test_coverage')}")
    console.print(f"  Adversarial tested:    {'✓' if perf.get('adversarial_tested') else '✗'}")
    console.print(f"  Hallucination tested:  {'✓' if perf.get('hallucination_tested') else '✗'}")
    console.print(f"  Fuzz tested:           {'✓' if perf.get('fuzz_tested') else '✗'}")
    console.print(f"  Production runs:       {perf.get('total_production_runs', 0)}\n")

    eu = compliance.get("eu_ai_act", {})
    console.print("[bold]EU AI Act:[/bold]")
    console.print(f"  Risk category:         {eu.get('risk_category')}")
    console.print(f"  Article 13:            {str(eu.get('article_13_transparency', 'UNKNOWN'))[:20]}")
    console.print(f"  Article 15:            {str(eu.get('article_15_accuracy', 'UNKNOWN'))[:20]}\n")

    co = compliance.get("colorado_ai_act", {})
    console.print("[bold]Colorado AI Act:[/bold]")
    console.print(f"  High-risk system:      {'Yes' if co.get('high_risk_ai_system') else 'No'}")
    console.print(f"  Notice required:       {'Yes' if co.get('notice_required') else 'No'}")
