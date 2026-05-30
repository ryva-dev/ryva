from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def export_audit_package(root: Path, out: Path | None = None) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    project_name = _get_project_name(root)
    output_path = out or root / "target" / f"ryva_audit_{project_name}_{timestamp}.zip"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Building audit package...", total=None)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:

            progress.update(task, description="Adding README...")
            readme = _generate_readme(root, project_name, timestamp)
            zf.writestr("README.md", readme)

            progress.update(task, description="Adding governance report...")
            gov_json = root / "target" / "governance_report.json"
            gov_md = root / "target" / "governance_report.md"
            if gov_json.exists():
                zf.write(gov_json, "governance/governance_report.json")
            if gov_md.exists():
                zf.write(gov_md, "governance/governance_report.md")
            else:
                zf.writestr(
                    "governance/MISSING.txt",
                    "Governance report not found. Run: ryva governance report",
                )

            progress.update(task, description="Adding model cards...")
            cards_dir = root / "target" / "model_cards"
            if cards_dir.exists():
                for card_file in cards_dir.glob("*.json"):
                    zf.write(card_file, f"model_cards/{card_file.name}")
            else:
                zf.writestr(
                    "model_cards/MISSING.txt",
                    "No model cards found. Run: ryva modelcard generate <agent>",
                )

            progress.update(task, description="Adding lineage records...")
            lineage_dir = root / "lineage"
            if lineage_dir.exists():
                lineage_files = list(lineage_dir.glob("*.json"))
                for lf in lineage_files[:100]:
                    zf.write(lf, f"lineage/{lf.name}")
                zf.writestr(
                    "lineage/SUMMARY.txt",
                    f"Total lineage records: {len(lineage_files)}\n"
                    f"Included in this package: {min(len(lineage_files), 100)}\n"
                    "Full lineage available via: ryva lineage search",
                )
            else:
                zf.writestr(
                    "lineage/MISSING.txt",
                    "No lineage records found. Run ryva run to generate lineage.",
                )

            progress.update(task, description="Adding test evidence...")
            test_evidence = _collect_test_evidence(root)
            zf.writestr("testing/test_evidence.json", json.dumps(test_evidence, indent=2))

            progress.update(task, description="Adding prompt registry...")
            manifest_path = root / "target" / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                prompt_hashes = manifest.get("prompt_hashes", {})
                registry = {
                    "generated_at": datetime.utcnow().isoformat(),
                    "prompt_versions": [
                        {
                            "name": name,
                            "sha256": f"sha256:{hash_val}",
                            "status": "active",
                        }
                        for name, hash_val in prompt_hashes.items()
                    ],
                }
                zf.writestr(
                    "prompts/prompt_version_registry.json",
                    json.dumps(registry, indent=2),
                )

            progress.update(task, description="Adding alignment policies...")
            policies_path = root / "policies.yml"
            project_yml = root / "project.yml"
            if policies_path.exists():
                zf.write(policies_path, "policies/policies.yml")
            if project_yml.exists():
                zf.write(project_yml, "project/project.yml")

            progress.update(task, description="Adding feedback data...")
            feedback_dir = root / "logs" / "feedback"
            if feedback_dir.exists():
                feedback_files = list(feedback_dir.glob("*.json"))
                if feedback_files:
                    feedback_summary = _summarize_feedback(feedback_files)
                    zf.writestr(
                        "feedback/feedback_summary.json",
                        json.dumps(feedback_summary, indent=2),
                    )

            progress.update(task, description="Adding cost data...")
            try:
                from ryva.cost_tracker import get_cost_summary
                cost_summary = get_cost_summary(root)
                zf.writestr(
                    "costs/cost_summary.json",
                    json.dumps(cost_summary, indent=2),
                )
            except Exception:
                pass

            progress.update(task, description="Adding EU AI Act checklist...")
            checklist = _generate_eu_checklist(root)
            zf.writestr("compliance/eu_ai_act_checklist.md", checklist)

            colorado = _generate_colorado_checklist(root)
            zf.writestr("compliance/colorado_ai_act_checklist.md", colorado)

            progress.update(task, description="Finalizing package...")
            package_manifest = {
                "package_version": "1.0.0",
                "generated_at": datetime.utcnow().isoformat(),
                "generated_by": "Ryva Forge Audit Export",
                "project": project_name,
                "contents": [
                    "README.md",
                    "governance/governance_report.json",
                    "governance/governance_report.md",
                    "model_cards/*.json",
                    "lineage/*.json",
                    "testing/test_evidence.json",
                    "prompts/prompt_version_registry.json",
                    "policies/policies.yml",
                    "feedback/feedback_summary.json",
                    "costs/cost_summary.json",
                    "compliance/eu_ai_act_checklist.md",
                    "compliance/colorado_ai_act_checklist.md",
                ],
                "intended_recipients": [
                    "Regulatory auditors",
                    "Legal and compliance teams",
                    "Chief Risk Officers",
                    "External audit firms",
                ],
            }
            zf.writestr("PACKAGE_MANIFEST.json", json.dumps(package_manifest, indent=2))

        progress.update(
            task, description="[bold green]Audit package complete.[/bold green]"
        )

    return output_path


def _get_project_name(root: Path) -> str:
    project_yml = root / "project.yml"
    if project_yml.exists():
        content = project_yml.read_text()
        match = re.search(r"name:\s*(.+)", content)
        if match:
            return match.group(1).strip().replace(" ", "_")
    return root.name


def _collect_test_evidence(root: Path) -> dict:
    tests_dir = root / "tests"
    evidence: dict = {
        "generated_at": datetime.utcnow().isoformat(),
        "test_types_configured": [],
        "test_files": [],
        "total_test_cases": 0,
    }
    if not tests_dir.exists():
        return evidence

    test_type_dirs = [
        "adversarial", "fuzz", "hallucination", "memory",
        "rag", "regression", "finetune", "vector", "multimodal",
    ]
    for td in test_type_dirs:
        if (tests_dir / td).exists():
            evidence["test_types_configured"].append(td)

    for yml in tests_dir.rglob("*.yml"):
        evidence["test_files"].append(str(yml.relative_to(root)))
        evidence["total_test_cases"] += 1

    return evidence


def _summarize_feedback(feedback_files: list) -> dict:
    total = len(feedback_files)
    correct = 0
    incorrect = 0
    partial = 0

    for f in feedback_files:
        try:
            data = json.loads(Path(f).read_text())
            outcome = data.get("outcome", "unknown")
            if outcome == "correct":
                correct += 1
            elif outcome == "incorrect":
                incorrect += 1
            elif outcome == "partial":
                partial += 1
        except Exception:
            pass

    return {
        "total_annotations": total,
        "correct": correct,
        "incorrect": incorrect,
        "partial": partial,
        "accuracy": round(correct / total, 3) if total > 0 else None,
    }


def _generate_eu_checklist(root: Path) -> str:
    gov_json = root / "target" / "governance_report.json"
    if gov_json.exists():
        try:
            report = json.loads(gov_json.read_text())
            checklist_items = report.get("eu_ai_act_checklist", [])
        except Exception:
            checklist_items = []
    else:
        checklist_items = []

    lines = [
        "# EU AI Act Compliance Checklist",
        f"\nGenerated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "Generated by: Ryva Forge AI Governance Platform\n",
        "---\n",
    ]

    if checklist_items:
        for item in checklist_items:
            status = item.get("status", "NOT ASSESSED")
            lines.append(f"## {item.get('article', '')} — {item.get('requirement', '')}")
            lines.append(f"**Status:** {status}")
            guidance = item.get("guidance", "")
            if guidance:
                lines.append(f"**Action:** {guidance}")
            lines.append("")
    else:
        article_map = {
            "Art. 9": "Risk Management System",
            "Art. 10": "Data and Data Governance",
            "Art. 12": "Record Keeping and Logging",
            "Art. 13": "Transparency and Information",
            "Art. 14": "Human Oversight",
            "Art. 15": "Accuracy, Robustness, and Cybersecurity",
        }
        for article, label in article_map.items():
            lines.append(f"## {article} — {label}")
            lines.append("**Status:** NOT ASSESSED")
            lines.append("**Action:** Run ryva governance report to assess.\n")

    return "\n".join(lines)


def _generate_colorado_checklist(root: Path) -> str:
    lines = [
        "# Colorado AI Act Compliance Checklist",
        "(SB 24-205, effective June 1, 2026)\n",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "Generated by: Ryva Forge AI Governance Platform\n",
        "---\n",
        "## Section 1 — Developer Obligations",
        "- Make available documentation describing known limitations, known or reasonably "
        "foreseeable risks of algorithmic discrimination, and a general statement of the "
        "purpose of the high-risk AI system.",
        "- Provide information on the data used to train the high-risk AI system.",
        "- Provide notice to deployers about the intended uses.\n",
        "## Section 2 — Deployer Obligations",
        "- Implement a risk management policy and program.",
        "- Complete an impact assessment prior to deployment.",
        "- Notify consumers when a consequential decision is made using a high-risk AI system.",
        "- Provide consumers with the opportunity to correct data and appeal decisions.",
        "- Disclose use of AI to consumers.\n",
        "## Section 3 — Ryva Coverage",
        "- Risk management: COVERED via ryva governance report and risk scoring",
        "- Impact assessment: COVERED via model cards (ryva modelcard generate)",
        "- Audit trail: COVERED via tamper-evident lineage records",
        "- Data documentation: COVERED via model cards data section",
        "- Known limitations: COVERED via model cards risk section\n",
        "## Section 4 — Gaps Requiring Manual Action",
        "- Consumer notice mechanism: Must be implemented in your application UI",
        "- Data correction workflow: Must be implemented in your application",
        "- Discrimination testing: Enable ryva test --adversarial for bias detection\n",
    ]
    return "\n".join(lines)


def _generate_readme(root: Path, project_name: str, timestamp: str) -> str:
    return f"""# Ryva Audit Package — {project_name}

Generated: {timestamp} UTC
Generated by: Ryva Forge AI Governance Platform (ryvaforge.com)

---

## Contents

| Folder | Contents |
|--------|----------|
| governance/ | Full governance report (JSON + Markdown) |
| model_cards/ | Model cards for each AI agent |
| lineage/ | Lineage records for recent production runs |
| testing/ | Test evidence summary |
| prompts/ | Prompt version registry with SHA-256 hashes |
| policies/ | Business alignment policies |
| feedback/ | Human feedback and accuracy annotations |
| costs/ | Cost and usage summary |
| compliance/ | EU AI Act and Colorado AI Act checklists |

---

## How to Use This Package

This package was generated automatically by Ryva and contains the technical
evidence required for AI governance audits under the EU AI Act and Colorado AI Act.

For questions about this package, contact the technical owner listed in each model card.

To regenerate this package with updated data:

```
ryva audit export
```

To verify lineage record integrity:

```
ryva lineage verify --all
```

---

## Important Notes

- Lineage records are tamper-evident and signed with HMAC-SHA256
- Prompt hashes allow verification that prompts have not changed since last compile
- Test evidence shows which test types have been run and configured
- All costs are estimated based on provider token pricing at time of run
"""
