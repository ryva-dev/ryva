from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional
import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

RYVA_CLOUD_URL = os.environ.get('RYVA_CLOUD_URL', 'https://ryva-cloud-production.up.railway.app')


def get_token(root: Path) -> Optional[str]:
    """Get stored cloud token from .ryva_cloud file."""
    token_file = root / '.ryva_cloud'
    if token_file.exists():
        data = json.loads(token_file.read_text())
        return data.get('token')
    # Also check home directory
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


def get_project_id(root: Path) -> Optional[str]:
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
    """Sync all local data to Ryva Cloud."""
    payload = {
        'project_id': project_id,
        'project_name': root.name,
        'traces': [],
        'lineage': [],
        'compliance_report': None,
        'model_cards': [],
        'benchmark_results': [],
    }

    # Collect traces
    traces_dir = root / 'traces'
    if traces_dir.exists():
        for f in sorted(traces_dir.glob('*.json')):
            try:
                data = json.loads(f.read_text())
                payload['traces'].append(data)
            except Exception:
                pass

    # Collect lineage
    lineage_dir = root / 'lineage'
    if lineage_dir.exists():
        for f in sorted(lineage_dir.glob('*.json')):
            try:
                data = json.loads(f.read_text())
                payload['lineage'].append(data)
            except Exception:
                pass

    # Collect compliance report
    gov_report = root / 'target' / 'governance_report.json'
    if gov_report.exists():
        try:
            payload['compliance_report'] = json.loads(gov_report.read_text())
        except Exception:
            pass

    # Collect model cards
    cards_dir = root / 'target' / 'model_cards'
    if cards_dir.exists():
        for f in cards_dir.glob('*.json'):
            try:
                payload['model_cards'].append(json.loads(f.read_text()))
            except Exception:
                pass

    # Send to cloud
    res = httpx.post(
        f'{RYVA_CLOUD_URL}/api/v1/sync/',
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=120
    )
    res.raise_for_status()
    return res.json()