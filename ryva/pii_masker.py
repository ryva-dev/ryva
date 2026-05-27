from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# PII regex patterns
# ---------------------------------------------------------------------------

_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(
        r"\b\d{3}[- ]\d{2}[- ]\d{4}\b",
        re.ASCII,
    ),
    "credit_card": re.compile(
        r"\b(?:\d[ -]?){13,16}\b",
        re.ASCII,
    ),
    "email": re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    ),
    "phone": re.compile(
        r"\b(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})\b",
        re.ASCII,
    ),
    "ip_address": re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        re.ASCII,
    ),
    "passport": re.compile(
        r"\b[A-Z]{1,2}\d{6,9}\b",
    ),
}

_DEFAULT_ENTITIES = {"ssn", "credit_card", "email", "phone"}
_MASK = "[REDACTED]"


def mask_text(
    text: str,
    entities: set[str] | None = None,
    mask: str = _MASK,
) -> tuple[str, list[dict]]:
    """
    Mask PII in text. Returns (masked_text, list_of_findings).

    Each finding: {"entity": str, "original": str, "start": int, "end": int}
    """
    active = entities if entities is not None else _DEFAULT_ENTITIES
    findings: list[dict] = []

    # Collect all matches with their positions
    for entity, pattern in _PATTERNS.items():
        if entity not in active:
            continue
        for m in pattern.finditer(text):
            findings.append({
                "entity": entity,
                "original": m.group(),
                "start": m.start(),
                "end": m.end(),
            })

    if not findings:
        return text, []

    # Sort by start position descending so replacements don't shift indices
    findings.sort(key=lambda f: f["start"], reverse=True)

    chars = list(text)
    for f in findings:
        chars[f["start"]: f["end"]] = list(mask)

    masked = "".join(chars)

    # Return findings sorted by position ascending for readability
    findings.sort(key=lambda f: f["start"])
    return masked, findings


def mask_dict(
    data: dict,
    entities: set[str] | None = None,
    mask: str = _MASK,
) -> tuple[dict, list[dict]]:
    """Recursively mask PII in all string values of a dict."""
    import json
    text = json.dumps(data)
    masked_text, findings = mask_text(text, entities=entities, mask=mask)
    try:
        import json as _json
        masked_data = _json.loads(masked_text)
    except Exception:
        masked_data = data
    return masked_data, findings


def load_pii_config(project: dict) -> dict:
    """Extract PII masking config from project dict."""
    cfg = project.get("pii_masking", {})
    return {
        "enabled": cfg.get("enabled", False),
        "entities": set(cfg.get("entities", list(_DEFAULT_ENTITIES))),
        "mask": cfg.get("mask", _MASK),
    }


def apply_if_enabled(
    text: str,
    project: dict,
) -> tuple[str, list[dict]]:
    """Mask text only if pii_masking.enabled is true in project config."""
    cfg = load_pii_config(project)
    if not cfg["enabled"]:
        return text, []
    return mask_text(text, entities=cfg["entities"], mask=cfg["mask"])
