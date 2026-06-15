"""Ryva Cloud synchronisation helpers.

Syncs governance objects (traces, compliance reports, model cards, approvals,
change history, manifest) to the Ryva Cloud API.  When no cloud credentials
are configured the functions log a warning and return gracefully so that all
other CLI commands continue to work offline.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

import httpx

from ryva.utils import console

RYVA_CLOUD_URL = os.environ.get('RYVA_CLOUD_URL', 'https://ryva-cloud-production.up.railway.app')


# ── Token / credential helpers ────────────────────────────────────────────────

def get_token(root: Path) -> str | None:
    """Get stored cloud token from .ryva_cloud file."""
    token_file = root / '.ryva_cloud'
    if token_file.exists():
        data = json.loads(token_file.read_text())
        return data.get('token')
    home_token = Path.home() / '.ryva_cloud'
    if home_token.exists():
        data = json.loads(home_token.read_text())
        return data.get('token')
    return None


def save_token(token: str, project_id: str):
    """Save cloud token to home directory."""
    token_file = Path.home() / '.ryva_cloud'
    data = {'token': token, 'project_id': project_id}
    token_file.write_text(json.dumps(data))
    token_file.chmod(0o600)


def get_project_id(root: Path) -> str | None:
    """Get stored project ID."""
    token_file = root / '.ryva_cloud'
    if token_file.exists():
        data = json.loads(token_file.read_text())
        return data.get('project_id')
    home_token = Path.home() / '.ryva_cloud'
    if home_token.exists():
        data = json.loads(home_token.read_text())
        return data.get('project_id')
    return None


def cloud_login(email: str, password: str) -> dict:
    """Login to Ryva Cloud and return token."""
    res = httpx.post(
        f'{RYVA_CLOUD_URL}/api/v1/users/signin',
        json={'email': email, 'password': password},
        timeout=30
    )
    res.raise_for_status()
    return res.json()


def _load_trace_payload(path: Path, project_id: str) -> dict | None:
    trace = _load_json(path)
    if not isinstance(trace, dict):
        return None
    tokens = trace.get("tokens") or {}
    return {
        "run_id": trace.get("run_id"),
        "project_id": project_id,
        "agent": trace.get("agent"),
        "model": trace.get("model"),
        "provider": trace.get("provider"),
        "status": trace.get("status"),
        "duration_ms": trace.get("duration_ms"),
        "steps": trace.get("steps", []),
        "input_tokens": tokens.get("input"),
        "output_tokens": tokens.get("output"),
        "estimated_cost": trace.get("cost_usd"),
        "started_at": trace.get("started_at"),
        "finished_at": trace.get("finished_at"),
    }


def _load_lineage_payload(path: Path, project_id: str) -> dict | None:
    record = _load_json(path)
    if not isinstance(record, dict):
        return None
    tokens = record.get("tokens") or {}
    return {
        "run_id": record.get("run_id"),
        "project_id": project_id,
        "agent": record.get("agent"),
        "input_hash": record.get("input_hash"),
        "prompt_hash": record.get("prompt_hash"),
        "output_hash": record.get("output_hash"),
        "prompt_template": record.get("prompt_template"),
        "input_tokens": tokens.get("input"),
        "output_tokens": tokens.get("output"),
        "cost_usd": record.get("cost_usd"),
        "parent_run_id": record.get("parent_run_id"),
        "trace_id": record.get("trace_id"),
        "retrieval_chunks": record.get("retrieval_chunks", []),
        "tool_calls": record.get("tool_calls", []),
        "signature": record.get("signature"),
        "signature_verified": record.get("signature_verified", False),
        "chain_depth": record.get("chain_depth", 1),
    }


def _derive_overall_score(report: dict) -> float | None:
    summary = report.get("summary") or {}
    eu_score = summary.get("eu_ai_act_compliance_score")
    if isinstance(eu_score, str) and "/" in eu_score:
        try:
            passed, total = eu_score.split("/", 1)
            total_value = float(total)
            if total_value > 0:
                return round((float(passed) / total_value) * 100, 2)
        except (TypeError, ValueError):
            return None
    return None


def _load_compliance_payload(path: Path, project_id: str, project_name: str) -> dict | None:
    report = _load_json(path)
    if not isinstance(report, dict):
        return None
    return {
        "project_id": project_id,
        "project_name": report.get("project") or project_name,
        "ryva_version": report.get("ryva_version"),
        "overall_score": _derive_overall_score(report),
        "overall_status": None,
        "eu_ai_act": report.get("eu_ai_act") or {},
        "colorado_ai_act": report.get("colorado_ai_act") or {},
        "risk_summary": report.get("risk_assessment"),
        "ai_bill_of_materials": report.get("bill_of_materials") or [],
        "metrics": (report.get("summary") or {}),
        "prompt_version_registry": report.get("prompt_version_registry") or {},
        "raw_report": report,
    }


def _load_model_card_payload(path: Path, project_id: str) -> dict | None:
    card = _load_json(path)
    if not isinstance(card, dict):
        return None
    system = card.get("system") or {}
    model = card.get("model") or {}
    perf = card.get("performance") or {}
    risk = card.get("risk") or {}
    compliance = card.get("compliance") or {}
    gdpr = compliance.get("gdpr") or {}
    return {
        "project_id": project_id,
        "agent_name": system.get("name"),
        "risk_level": risk.get("risk_level"),
        "risk_justification": risk.get("risk_justification"),
        "model_id": model.get("model_id"),
        "provider": model.get("provider"),
        "intended_use": system.get("intended_use"),
        "known_limitations": risk.get("known_limitations"),
        "eu_ai_act_status": compliance.get("eu_ai_act"),
        "colorado_ai_act_status": compliance.get("colorado_ai_act"),
        "pii_masking_enabled": gdpr.get("pii_masking_enabled"),
        "test_coverage": perf.get("test_coverage"),
        "adversarial_tested": perf.get("adversarial_tested"),
        "hallucination_tested": perf.get("hallucination_tested"),
        "total_production_runs": perf.get("total_production_runs"),
        "raw_card": card,
    }


def cloud_sync(root: Path, token: str, project_id: str) -> dict:
    """Sync all local data to Ryva Cloud using the canonical backend routes."""
    return sync_all(root, project_id, token, RYVA_CLOUD_URL)


# ── Governance-object sync helpers (API-key based) ────────────────────────────

def _load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _post(url: str, payload: dict, api_key: str) -> dict:
    resp = httpx.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def _external_signature_message(kind: str, project_id: str, system_id: str, payload: dict) -> str:
    body = dict(payload)
    body.pop("signature", None)
    body.pop("signature_verified", None)
    return json.dumps(
        {
            "kind": kind,
            "project_id": project_id,
            "system_id": system_id,
            "payload": body,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _sign_external_payload(kind: str, project_id: str, system_id: str, payload: dict, ingestion_token: str) -> dict:
    signed = dict(payload)
    message = _external_signature_message(kind, project_id, system_id, signed)
    signed["signature"] = hmac.new(
        ingestion_token.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signed["signature_verified"] = False
    return signed


def _post_external(url: str, payload: dict, ingestion_token: str) -> dict:
    resp = httpx.post(
        url,
        json=payload,
        headers={"X-Ryva-Ingestion-Token": ingestion_token},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def sync_external_trace(
    *,
    project_id: str,
    system_id: str,
    ingestion_token: str,
    payload: dict,
    cloud_url: str,
) -> dict:
    signed = _sign_external_payload(
        "external_trace",
        project_id,
        system_id,
        payload,
        ingestion_token,
    )
    return _post_external(
        f"{cloud_url}/api/v1/systems/{system_id}/external-traces?project_id={project_id}",
        signed,
        ingestion_token,
    )


def sync_external_lineage(
    *,
    project_id: str,
    system_id: str,
    ingestion_token: str,
    payload: dict,
    cloud_url: str,
) -> dict:
    signed = _sign_external_payload(
        "external_lineage",
        project_id,
        system_id,
        payload,
        ingestion_token,
    )
    return _post_external(
        f"{cloud_url}/api/v1/systems/{system_id}/external-lineage?project_id={project_id}",
        signed,
        ingestion_token,
    )


def preview_external_refresh(
    *,
    project_id: str,
    system_id: str | None,
    external_system_id: str | None,
    source_type: str,
    descriptor: dict,
    ingestion_token: str,
    cloud_url: str,
) -> dict:
    payload = {
        "project_id": project_id,
        "system_id": system_id,
        "external_system_id": external_system_id,
        "source_type": source_type,
        "descriptor": descriptor,
    }
    return _post_external(
        f"{cloud_url}/api/v1/systems/source-sync/refresh/preview",
        payload,
        ingestion_token,
    )


def refresh_external_metadata(
    *,
    project_id: str,
    system_id: str | None,
    external_system_id: str | None,
    source_type: str,
    descriptor: dict,
    ingestion_token: str,
    cloud_url: str,
) -> dict:
    payload = {
        "project_id": project_id,
        "system_id": system_id,
        "external_system_id": external_system_id,
        "source_type": source_type,
        "descriptor": descriptor,
    }
    return _post_external(
        f"{cloud_url}/api/v1/systems/source-sync/refresh",
        payload,
        ingestion_token,
    )


def sync_all(root: Path, project_id: str, api_key: str, cloud_url: str) -> dict:
    """Sync all governance objects to Ryva Cloud.

    Returns a dict mapping object type to sync result (or None if skipped).
    """
    results: dict = {}

    traces_dir = root / "traces"
    if traces_dir.exists():
        trace_files = sorted(traces_dir.glob("*.json"))
        synced = 0
        for trace_file in trace_files:
            payload = _load_trace_payload(trace_file, project_id)
            if not payload:
                continue
            try:
                _post(f"{cloud_url}/api/v1/traces/", payload, api_key)
                synced += 1
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync trace {trace_file.name}: {exc}[/yellow]")
        results["traces"] = {"synced": synced, "total": len(trace_files)}
        console.print(f"[dim]  ✓ Synced {synced}/{len(trace_files)} trace(s)[/dim]")

    lineage_dir = root / "lineage"
    if lineage_dir.exists():
        lineage_files = sorted(lineage_dir.glob("*.json"))
        synced = 0
        for lineage_file in lineage_files:
            payload = _load_lineage_payload(lineage_file, project_id)
            if not payload:
                continue
            try:
                _post(f"{cloud_url}/api/v1/lineage/", payload, api_key)
                synced += 1
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync lineage {lineage_file.name}: {exc}[/yellow]")
        results["lineage"] = {"synced": synced, "total": len(lineage_files)}
        console.print(f"[dim]  ✓ Synced {synced}/{len(lineage_files)} lineage record(s)[/dim]")

    report = root / "target" / "governance_report.json"
    if report.exists():
        payload = _load_compliance_payload(report, project_id, root.name)
        if payload:
            try:
                results["compliance"] = _post(
                    f"{cloud_url}/api/v1/compliance/report",
                    payload,
                    api_key,
                )
                console.print("[dim]  ✓ Synced compliance report[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync compliance report: {exc}[/yellow]")

    cards_dir = root / "target" / "model_cards"
    if cards_dir.exists():
        cards = [_load_model_card_payload(f, project_id) for f in sorted(cards_dir.glob("*.json"))]
        cards = [c for c in cards if c]
        if cards:
            synced = 0
            for card in cards:
                try:
                    _post(f"{cloud_url}/api/v1/compliance/model-cards", card, api_key)
                    synced += 1
                except Exception as exc:
                    console.print(
                        f"[yellow]  ⚠ Could not sync model card {card.get('agent_name')}: {exc}[/yellow]"
                    )
            results["model_cards"] = {"synced": synced, "total": len(cards)}
            console.print(f"[dim]  ✓ Synced {synced}/{len(cards)} model card(s)[/dim]")

    approvals_dir = root / "target" / "approvals"
    if approvals_dir.exists():
        approvals = [_load_json(f) for f in sorted(approvals_dir.glob("*.json"))]
        approvals = [a for a in approvals if a]
        if approvals:
            try:
                results["approvals"] = _post(
                    f"{cloud_url}/api/v1/governance/approvals/bulk",
                    {"project_id": project_id, "approvals": approvals},
                    api_key,
                )
                console.print(f"[dim]  ✓ Synced {len(approvals)} approval record(s)[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync approvals: {exc}[/yellow]")

    history_file = root / "target" / "change_history.json"
    if history_file.exists():
        history = _load_json(history_file)
        if history:
            try:
                results["changes"] = _post(
                    f"{cloud_url}/api/v1/governance/changes/bulk",
                    {"project_id": project_id, "changes": history},
                    api_key,
                )
                console.print(f"[dim]  ✓ Synced {len(history)} change record(s)[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync change history: {exc}[/yellow]")

    manifest_file = root / "target" / "manifest.json"
    if manifest_file.exists():
        manifest = _load_json(manifest_file)
        if isinstance(manifest, dict):
            try:
                results["manifest"] = _post(
                    f"{cloud_url}/api/v1/governance/manifest",
                    {"project_id": project_id, "manifest": manifest},
                    api_key,
                )
                console.print("[dim]  ✓ Synced project manifest[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync manifest: {exc}[/yellow]")

    exceptions_file = root / "target" / "exceptions.json"
    if exceptions_file.exists():
        exceptions = _load_json(exceptions_file)
        if exceptions:
            try:
                results["exceptions"] = _post(
                    f"{cloud_url}/api/v1/release/exceptions/bulk",
                    {"project_id": project_id, "exceptions": exceptions},
                    api_key,
                )
                console.print(f"[dim]  ✓ Synced {len(exceptions)} exception record(s)[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync exceptions: {exc}[/yellow]")

    return results
