from __future__ import annotations

import math

_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None
_available: bool | None = None


def _get_model():
    """Lazy-load sentence-transformers model; returns None if unavailable."""
    global _model, _available
    if _available is False:
        return None
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
        _available = True
        return _model
    except Exception:
        _available = False
        return None


def embed(texts: list[str]) -> list[list[float]] | None:
    """
    Embed a list of texts using sentence-transformers.
    Returns None if the model is unavailable.
    """
    model = _get_model()
    if model is None:
        return None
    try:
        vecs = model.encode(texts, convert_to_numpy=True)
        return vecs.tolist()
    except Exception:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two dense vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_similarity(text_a: str, text_b: str) -> float:
    """
    Compute semantic similarity in [0, 1] between two texts.
    Uses sentence-transformers if available; falls back to token F1.
    """
    vecs = embed([text_a, text_b])
    if vecs is not None:
        return max(0.0, float(cosine_similarity(vecs[0], vecs[1])))
    return _token_f1(text_a, text_b)


def batch_similarity(query: str, texts: list[str]) -> list[float]:
    """
    Compute similarity between a query and each text in a list.
    Returns a list of float scores in [0, 1].
    """
    if not texts:
        return []
    vecs = embed([query] + texts)
    if vecs is not None:
        q_vec = vecs[0]
        return [max(0.0, float(cosine_similarity(q_vec, v))) for v in vecs[1:]]
    return [_token_f1(query, t) for t in texts]


def is_available() -> bool:
    """Return True if sentence-transformers is installed and model can be loaded."""
    return _get_model() is not None


# ---------------------------------------------------------------------------
# Fallback: token-overlap F1 (no external deps)
# ---------------------------------------------------------------------------

_STOP = frozenset({
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "for",
    "of", "and", "or", "but", "not", "with", "this", "that",
})


def _token_f1(text_a: str, text_b: str) -> float:
    tokens_a = {t for t in text_a.lower().split() if t not in _STOP}
    tokens_b = {t for t in text_b.lower().split() if t not in _STOP}
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = tokens_a & tokens_b
    precision = len(overlap) / len(tokens_a)
    recall = len(overlap) / len(tokens_b)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
