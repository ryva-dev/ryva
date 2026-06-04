"""Release gate enforcement.

Checks whether an AI system meets governance requirements before allowing
sync to a target environment.  Also handles approval invalidation when
significant changes are detected during compile.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    agents_checked: list[str] = field(default_factory=list)


ENVIRONMENT_REQUIREMENTS: dict[str, dict] = {
    "dev": {
        "required_approvals": [],
        "require_passing_tests": False,
        "require_governance_report": False,
    },
    "staging": {
        "required_approvals": ["technical"],
        "require_passing_tests": True,
        "require_governance_report": True,
    },
    "production": {
        "required_approvals": ["technical", "privacy", "compliance", "legal"],
        "require_passing_tests": True,
        "require_governance_report": True,
        "require_no_stale_approvals": True,
    },
}


def check_release_gates(env: str = "dev", root: Path | None = None) -> GateResult:
    """Check all release gates for the current project.

    Returns GateResult with passed=True if all gates pass.
    """
    if root is None:
        root = Path.cwd()

    requirements = ENVIRONMENT_REQUIREMENTS.get(env, ENVIRONMENT_REQUIREMENTS["dev"])
    failures: list[str] = []
    warnings: list[str] = []
    agents_checked: list[str] = []

    manifest_path = root / "target" / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass

    agents = list(manifest.get("agents", {}).keys())
    if not agents:
        warnings.append("No agents compiled. Run 'ryva compile' first.")
        return GateResult(passed=True, warnings=warnings)

    approvals: list[dict] = []
    approvals_dir = root / "target" / "approvals"
    if approvals_dir.exists():
        for f in sorted(approvals_dir.glob("*.json")):
            try:
                approvals.append(json.loads(f.read_text()))
            except Exception:
                pass

    for agent_name in agents:
        agents_checked.append(agent_name)
        agent_manifest = manifest["agents"].get(agent_name, {})
        current_prompt_hash = agent_manifest.get("prompt_hash")
        current_model = agent_manifest.get("model")
        agent_approvals = [a for a in approvals if a.get("agent") == agent_name]

        for required_step in requirements.get("required_approvals", []):
            step_approvals = [
                a for a in agent_approvals
                if a.get("step") == required_step and a.get("status") == "approved"
            ]

            if not step_approvals:
                failures.append(
                    f"{agent_name}: missing '{required_step}' approval "
                    f"(required for {env})"
                )
                continue

            if requirements.get("require_no_stale_approvals"):
                latest = max(step_approvals, key=lambda a: a.get("approved_at", ""))
                approved_prompt_hash = latest.get("prompt_hash")
                approved_model = latest.get("approved_model")

                if approved_prompt_hash and current_prompt_hash:
                    if approved_prompt_hash != current_prompt_hash:
                        failures.append(
                            f"{agent_name}: '{required_step}' approval is stale — "
                            f"prompt changed from {approved_prompt_hash[:8]} "
                            f"to {current_prompt_hash[:8]} after approval. "
                            f"Re-review required."
                        )

                if approved_model and current_model and approved_model != current_model:
                    failures.append(
                        f"{agent_name}: '{required_step}' approval is stale — "
                        f"model changed from {approved_model} "
                        f"to {current_model} after approval. "
                        f"Re-review required."
                    )

        if requirements.get("require_passing_tests"):
            test_results_dir = root / "target" / "test_results"
            if not test_results_dir.exists():
                failures.append(
                    f"{agent_name}: no test results found. "
                    f"Run 'ryva test' before syncing to {env}."
                )
            else:
                agent_results = list(test_results_dir.glob(f"{agent_name}*.json"))
                if not agent_results:
                    warnings.append(
                        f"{agent_name}: no test results for this agent. "
                        f"Consider running 'ryva test --agent {agent_name}'."
                    )

        if requirements.get("require_governance_report"):
            if not (root / "target" / "governance_report.json").exists():
                if not any(
                    "No governance report found" in f for f in failures
                ):
                    failures.append(
                        "No governance report found. "
                        f"Run 'ryva governance report' before syncing to {env}."
                    )

    exceptions_file = root / "target" / "exceptions.json"
    if exceptions_file.exists():
        try:
            exceptions = json.loads(exceptions_file.read_text())
            now = datetime.now(UTC).isoformat()
            for exc in exceptions:
                if exc.get("expires_at") and exc["expires_at"] < now:
                    warnings.append(
                        f"Exception '{exc.get('id')}' for {exc.get('agent')} "
                        f"expired on {exc['expires_at'][:10]}. Review or renew."
                    )
        except Exception:
            pass

    return GateResult(
        passed=len(failures) == 0,
        failures=failures,
        warnings=warnings,
        agents_checked=agents_checked,
    )


def invalidate_stale_approvals(
    changes: list[dict], root: Path | None = None
) -> list[str]:
    """Mark approvals as stale when significant changes are detected.

    Returns list of invalidated approval IDs.
    """
    if root is None:
        root = Path.cwd()

    significant_change_types = {"PROMPT_CHANGE", "MODEL_CHANGE"}
    significant_changes = [
        c for c in changes if c.get("type") in significant_change_types
    ]

    if not significant_changes:
        return []

    affected_agents = {c["agent"] for c in significant_changes}
    invalidated: list[str] = []

    approvals_dir = root / "target" / "approvals"
    if not approvals_dir.exists():
        return []

    now = datetime.now(UTC).isoformat()
    for filepath in sorted(approvals_dir.glob("*.json")):
        try:
            approval = json.loads(filepath.read_text())
        except Exception:
            continue

        if approval.get("agent") in affected_agents and approval.get("status") == "approved":
            approval["status"] = "stale"
            approval["stale_reason"] = (
                "Significant change detected after approval. Re-review required."
            )
            approval["stale_at"] = now
            filepath.write_text(json.dumps(approval, indent=2))
            invalidated.append(approval["id"])

    return invalidated
