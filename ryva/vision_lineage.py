from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rich.table import Table
from rich.tree import Tree

from ryva.utils import console

_VISION_DIR = "vision_lineage"


# ---------------------------------------------------------------------------
# Image hashing
# ---------------------------------------------------------------------------

def hash_image(path: Path) -> str:
    """Return SHA-256 fingerprint of an image file with 'sha256:' prefix."""
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return "sha256:" + sha.hexdigest()[:16]


def hash_image_bytes(data: bytes) -> str:
    """Hash raw image bytes."""
    return "sha256:" + hashlib.sha256(data).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Record inference / annotation
# ---------------------------------------------------------------------------

def record_inference(
    root: Path,
    image_path: Path | None = None,
    image_hash: str | None = None,
    model: str = "",
    agent: str = "",
    predictions: list[dict] | None = None,
    metadata: dict | None = None,
) -> str:
    """
    Record a vision model inference result.

    image_path or image_hash must be provided (or both).
    predictions is a list of {label, confidence, bbox?} dicts.
    Returns record_id.
    """
    if image_path is not None and image_hash is None:
        image_hash = hash_image(image_path)

    record_id = str(uuid.uuid4())[:8]
    entry = {
        "record_id": record_id,
        "type": "inference",
        "image_path": str(image_path) if image_path else None,
        "image_hash": image_hash,
        "model": model,
        "agent": agent,
        "timestamp": datetime.now(UTC).isoformat(),
        "predictions": predictions or [],
        "metadata": metadata or {},
    }
    _write_record(root, record_id, entry)
    return record_id


def record_annotation(
    root: Path,
    image_path: Path | None = None,
    image_hash: str | None = None,
    annotator: str = "",
    labels: list[dict] | None = None,
    inference_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """
    Record a human annotation for an image.

    labels is a list of {label, confidence?, bbox?} dicts.
    inference_id links this annotation to a prior inference record.
    Returns record_id.
    """
    if image_path is not None and image_hash is None:
        image_hash = hash_image(image_path)

    record_id = str(uuid.uuid4())[:8]
    entry = {
        "record_id": record_id,
        "type": "annotation",
        "image_path": str(image_path) if image_path else None,
        "image_hash": image_hash,
        "annotator": annotator,
        "timestamp": datetime.now(UTC).isoformat(),
        "labels": labels or [],
        "inference_id": inference_id,
        "metadata": metadata or {},
    }
    _write_record(root, record_id, entry)
    return record_id


def _write_record(root: Path, record_id: str, entry: dict) -> None:
    vis_dir = root / _VISION_DIR
    vis_dir.mkdir(exist_ok=True)
    (vis_dir / f"{record_id}.json").write_text(json.dumps(entry, indent=2))


# ---------------------------------------------------------------------------
# Agreement scoring
# ---------------------------------------------------------------------------

def compute_agreement(
    inference_id: str,
    annotation_id: str,
    root: Path,
) -> dict:
    """
    Compute label agreement between an inference and an annotation.

    Uses semantic similarity from ryva.embeddings when available,
    falling back to exact label matching.
    Returns a dict with agreement_score in [0, 1] and per-label breakdown.
    """
    inf_record = _load_record(root, inference_id)
    ann_record = _load_record(root, annotation_id)

    if inf_record is None or ann_record is None:
        return {
            "inference_id": inference_id,
            "annotation_id": annotation_id,
            "agreement_score": None,
            "error": "One or both records not found",
        }

    inf_labels = {str(p.get("label", "")).lower() for p in inf_record.get("predictions", [])}
    ann_labels = {str(lbl.get("label", "")).lower() for lbl in ann_record.get("labels", [])}

    if not inf_labels and not ann_labels:
        return {
            "inference_id": inference_id,
            "annotation_id": annotation_id,
            "agreement_score": 1.0,
            "matched": [],
            "only_inference": [],
            "only_annotation": [],
        }

    # Try semantic similarity if available
    try:
        from ryva.embeddings import semantic_similarity
        scores = []
        for il in inf_labels:
            best = max(
                (semantic_similarity(il, al) for al in ann_labels),
                default=0.0,
            )
            scores.append(best)
        agreement_score = sum(scores) / len(scores) if scores else 0.0
    except Exception:
        # Exact match fallback
        matched = inf_labels & ann_labels
        union = inf_labels | ann_labels
        agreement_score = len(matched) / len(union) if union else 1.0

    matched = inf_labels & ann_labels
    return {
        "inference_id": inference_id,
        "annotation_id": annotation_id,
        "agreement_score": round(float(agreement_score), 4),
        "matched": sorted(matched),
        "only_inference": sorted(inf_labels - ann_labels),
        "only_annotation": sorted(ann_labels - inf_labels),
    }


# ---------------------------------------------------------------------------
# Lineage chain by image hash
# ---------------------------------------------------------------------------

def lineage_for_image(root: Path, image_hash: str) -> list[dict]:
    """Return all records (inference + annotation) for a given image hash, ordered by timestamp."""
    vis_dir = root / _VISION_DIR
    if not vis_dir.exists():
        return []

    records = []
    for path in vis_dir.glob("*.json"):
        try:
            r = json.loads(path.read_text())
            if r.get("image_hash") == image_hash:
                records.append(r)
        except (json.JSONDecodeError, OSError):
            continue

    records.sort(key=lambda r: r.get("timestamp", ""))
    return records


def _load_record(root: Path, record_id: str) -> dict | None:
    path = root / _VISION_DIR / f"{record_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_vision_report(root: Path) -> dict:
    """Summarise all vision lineage records."""
    vis_dir = root / _VISION_DIR
    if not vis_dir.exists():
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "total_records": 0,
            "inferences": 0,
            "annotations": 0,
            "unique_images": 0,
            "models": [],
            "annotators": [],
        }

    records = []
    for path in vis_dir.glob("*.json"):
        try:
            records.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue

    inferences = [r for r in records if r.get("type") == "inference"]
    annotations = [r for r in records if r.get("type") == "annotation"]
    unique_hashes = {r["image_hash"] for r in records if r.get("image_hash")}
    models = list({r.get("model") for r in inferences if r.get("model")})
    annotators = list({r.get("annotator") for r in annotations if r.get("annotator")})

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_records": len(records),
        "inferences": len(inferences),
        "annotations": len(annotations),
        "unique_images": len(unique_hashes),
        "models": sorted(models),
        "annotators": sorted(annotators),
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def show_lineage(root: Path, image_hash: str) -> None:
    records = lineage_for_image(root, image_hash)
    if not records:
        console.print(f"[red]No vision lineage found for image hash '{image_hash}'.[/red]")
        return

    tree = Tree(f"[bold cyan]Vision lineage for[/bold cyan] [bold]{image_hash}[/bold]")
    for r in records:
        rec_type = r.get("type", "?")
        ts = (r.get("timestamp") or "")[:19].replace("T", " ")
        if rec_type == "inference":
            label = (
                f"[green]inference[/green] {r.get('model', '—')} "
                f"[dim]{ts}[/dim]"
            )
            node = tree.add(label)
            for pred in r.get("predictions", [])[:5]:
                conf = pred.get("confidence")
                conf_str = f" ({conf:.2f})" if conf is not None else ""
                node.add(f"[dim]{pred.get('label', '?')}{conf_str}[/dim]")
        else:
            label = (
                f"[yellow]annotation[/yellow] by {r.get('annotator', '—')} "
                f"[dim]{ts}[/dim]"
            )
            node = tree.add(label)
            for lbl in r.get("labels", [])[:5]:
                node.add(f"[dim]{lbl.get('label', '?')}[/dim]")

    console.print(tree)


def show_vision_report(root: Path, out: Path | None = None) -> None:
    report = generate_vision_report(root)
    table = Table(title="Vision Lineage Report", show_header=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value")
    table.add_row("Total Records", str(report["total_records"]))
    table.add_row("Inferences", str(report["inferences"]))
    table.add_row("Annotations", str(report["annotations"]))
    table.add_row("Unique Images", str(report["unique_images"]))
    if report["models"]:
        table.add_row("Models", ", ".join(report["models"]))
    if report["annotators"]:
        table.add_row("Annotators", ", ".join(report["annotators"]))
    console.print(table)

    if out:
        out.write_text(json.dumps(report, indent=2))
        console.print(f"[green]✓ Report saved to {out}[/green]")
