from __future__ import annotations

from ryva.embeddings import (
    _token_f1,
    batch_similarity,
    cosine_similarity,
    semantic_similarity,
)

# ---------------------------------------------------------------------------
# cosine_similarity (pure math, no model required)
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-9

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) + 1.0) < 1e-9

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_symmetric(self):
        a = [0.5, 0.3, 0.8]
        b = [0.1, 0.9, 0.4]
        assert abs(cosine_similarity(a, b) - cosine_similarity(b, a)) < 1e-9


# ---------------------------------------------------------------------------
# Token F1 fallback (no model required)
# ---------------------------------------------------------------------------

class TestTokenF1:
    def test_identical_text(self):
        assert _token_f1("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert _token_f1("cat sat mat", "dog ran far") == 0.0

    def test_partial_overlap(self):
        score = _token_f1("the quick fox", "quick brown fox")
        assert 0.0 < score < 1.0

    def test_empty_text_returns_zero(self):
        assert _token_f1("", "hello world") == 0.0
        assert _token_f1("hello world", "") == 0.0

    def test_symmetric(self):
        a, b = "machine learning models", "deep learning neural networks"
        assert abs(_token_f1(a, b) - _token_f1(b, a)) < 1e-9


# ---------------------------------------------------------------------------
# semantic_similarity (uses embeddings if available, else token F1)
# ---------------------------------------------------------------------------

class TestSemanticSimilarity:
    def test_returns_float_in_unit_interval(self):
        score = semantic_similarity("hello world", "hi there")
        assert 0.0 <= score <= 1.0

    def test_identical_text_high_score(self):
        score = semantic_similarity("the cat sat on the mat", "the cat sat on the mat")
        assert score > 0.9

    def test_unrelated_text_lower_than_identical(self):
        same = semantic_similarity("cat dog", "cat dog")
        diff = semantic_similarity("cat dog", "quantum physics")
        assert same > diff

    def test_empty_string_does_not_crash(self):
        score = semantic_similarity("", "hello")
        assert 0.0 <= score <= 1.0

    def test_symmetry(self):
        a = "neural network training"
        b = "deep learning optimization"
        s1 = semantic_similarity(a, b)
        s2 = semantic_similarity(b, a)
        assert abs(s1 - s2) < 0.05


# ---------------------------------------------------------------------------
# batch_similarity
# ---------------------------------------------------------------------------

class TestBatchSimilarity:
    def test_returns_list_same_length(self):
        scores = batch_similarity("hello", ["hi", "world", "greetings"])
        assert len(scores) == 3

    def test_all_scores_in_unit_interval(self):
        scores = batch_similarity("machine learning", [
            "deep learning",
            "cooking recipes",
            "neural networks",
        ])
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_empty_list_returns_empty(self):
        assert batch_similarity("query", []) == []

    def test_exact_match_scores_highest(self):
        query = "the sky is blue"
        candidates = ["the sky is blue", "cars drive on roads", "oceans are deep"]
        scores = batch_similarity(query, candidates)
        assert scores[0] == max(scores)
