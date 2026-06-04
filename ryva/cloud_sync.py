"""Ryva Cloud synchronisation helpers.

Syncs governance objects (traces, compliance reports, model cards, approvals,
change history, manifest) to the Ryva Cloud API.  When no cloud credentials
are configured the functions log a warning and return gracefully so that all
other CLI commands continue to work offline.
"""
from __future__ import annotations

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


def cloud_sync(root: Path, token: str, project_id: str) -> dict:
    """Sync all local data to Ryva Cloud (traces, lineage, reports, model cards)."""
    payload = {
        'project_id': project_id,
        'project_name': root.name,
        'traces': [],
        'lineage': [],
        'compliance_report': None,
        'model_cards': [],
        'benchmark_results': [],
    }

    traces_dir = root / 'traces'
    if traces_dir.exists():
        for f in sorted(traces_dir.glob('*.json')):
            try:
                payload['traces'].append(json.loads(f.read_text()))
            except Exception:
                pass

    lineage_dir = root / 'lineage'
    if lineage_dir.exists():
        for f in sorted(lineage_dir.glob('*.json')):
            try:
                payload['lineage'].append(json.loads(f.read_text()))
            except Exception:
                pass

    gov_report = root / 'target' / 'governance_report.json'
    if gov_report.exists():
        try:
            payload['compliance_report'] = json.loads(gov_report.read_text())
        except Exception:
            pass

    cards_dir = root / 'target' / 'model_cards'
    if cards_dir.exists():
        for f in cards_dir.glob('*.json'):
            try:
                payload['model_cards'].append(json.loads(f.read_text()))
            except Exception:
                pass

    res = httpx.post(
        f'{RYVA_CLOUD_URL}/api/v1/sync/',
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=120
    )
    res.raise_for_status()
    return res.json()


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


def sync_all(root: Path, project_id: str, api_key: str, cloud_url: str) -> dict:
    """Sync all governance objects to Ryva Cloud.

    Returns a dict mapping object type to sync result (or None if skipped).
    """
    results: dict = {}

    report = root / "target" / "governance_report.json"
    if report.exists():
        data = _load_json(report)
        if data:
            try:
                results["compliance"] = _post(
                    f"{cloud_url}/api/v1/governance/compliance",
                    {"project_id": project_id, "report": data},
                    api_key,
                )
                console.print("[dim]  ✓ Synced compliance report[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync compliance report: {exc}[/yellow]")

    cards_dir = root / "target" / "model_cards"
    if cards_dir.exists():
        cards = [_load_json(f) for f in sorted(cards_dir.glob("*.json"))]
        cards = [c for c in cards if c]
        if cards:
            try:
                results["model_cards"] = _post(
                    f"{cloud_url}/api/v1/governance/model-cards/bulk",
                    {"project_id": project_id, "cards": cards},
                    api_key,
                )
                console.print(f"[dim]  ✓ Synced {len(cards)} model card(s)[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync model cards: {exc}[/yellow]")

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
        if manifest:
            try:
                results["manifest"] = _post(
                    f"{cloud_url}/api/v1/governance/manifest",
                    {"project_id": project_id, "manifest": manifest},
                    api_key,
                )
                console.print("[dim]  ✓ Synced project manifest[/dim]")
            except Exception as exc:
                console.print(f"[yellow]  ⚠ Could not sync manifest: {exc}[/yellow]")

    return results
