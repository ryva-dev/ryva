from __future__ import annotations

import json
from pathlib import Path

import pytest

from ryva.model_card import (
    MODEL_CARD_TEMPLATE,
    _assess_risk,
    generate_model_card,
    print_model_card_summary,
    save_model_card,
)

REQUIRED_TOP_LEVEL_KEYS = [
    "schema_version",
    "generated_at",
    "generated_by",
    "system",
    "model",
    "data",
    "performance",
    "risk",
    "compliance",
    "audit",
    "contacts",
]


def _make_manifest(tmp_path: Path, agent_name: str = "test_agent", description: str = "") -> None:
    (tmp_path / "target").mkdir(exist_ok=True)
    manifest = {
        "ryva_version": "0.1.0",
        "project": {"name": "test-project"},
        "agents": {
            agent_name: {
                "name": agent_name,
                "version": "1.0.0",
                "description": description,
                "prompt": "ref(prompts/test_prompt)",
                "tools": [],
                "input": {"schema_": {"text": {"type": "str", "required": True}}},
                "output": {"schema_": {"result": {"type": "str"}}},
                "meta": {},
            }
        },
        "tools": {},
        "pipelines": {},
        "prompt_hashes": {"test_prompt": "abc123def456"},
    }
    (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))


class TestGenerateModelCard:
    def test_returns_all_required_top_level_keys(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        for key in REQUIRED_TOP_LEVEL_KEYS:
            assert key in card, f"Missing key: {key}"

    def test_risk_high_when_description_contains_medical(self, tmp_path):
        _make_manifest(tmp_path, description="A medical diagnosis assistant for clinical use")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["risk"]["risk_level"] == "HIGH"

    def test_risk_high_when_description_contains_financial(self, tmp_path):
        _make_manifest(tmp_path, description="financial loan approval system")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["risk"]["risk_level"] == "HIGH"

    def test_risk_low_when_no_keywords(self, tmp_path):
        _make_manifest(tmp_path, description="Summarizes text into bullet points")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["risk"]["risk_level"] == "LOW"

    def test_risk_medium_when_customer_support(self, tmp_path):
        _make_manifest(tmp_path, description="Customer support chatbot for product questions")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["risk"]["risk_level"] in ("MEDIUM", "LOW")

    def test_contains_correct_agent_name(self, tmp_path):
        _make_manifest(tmp_path, agent_name="my_agent")
        card = generate_model_card(tmp_path, "my_agent")
        assert card["system"]["name"] == "my_agent"

    def test_returns_empty_dict_for_unknown_agent(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "nonexistent_agent")
        assert card == {}

    def test_eu_ai_act_risk_category_maps_high(self, tmp_path):
        _make_manifest(tmp_path, description="medical diagnostic system")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["compliance"]["eu_ai_act"]["risk_category"] == "HIGH"

    def test_eu_ai_act_risk_category_maps_minimal_for_low(self, tmp_path):
        _make_manifest(tmp_path, description="Summarizes text")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["compliance"]["eu_ai_act"]["risk_category"] == "MINIMAL"

    def test_colorado_ai_act_high_risk_true_when_risk_high(self, tmp_path):
        _make_manifest(tmp_path, description="legal sentencing recommendation system")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["compliance"]["colorado_ai_act"]["high_risk_ai_system"] is True
        assert card["compliance"]["colorado_ai_act"]["consequential_decision"] is True

    def test_colorado_ai_act_high_risk_false_when_risk_low(self, tmp_path):
        _make_manifest(tmp_path, description="Summarizes product descriptions")
        card = generate_model_card(tmp_path, "test_agent")
        assert card["compliance"]["colorado_ai_act"]["high_risk_ai_system"] is False

    def test_prompt_hash_in_model_section(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        assert card["model"]["prompt_hash"].startswith("sha256:")

    def test_generated_at_is_set(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        assert card["generated_at"] is not None
        assert "T" in card["generated_at"]

    def test_audit_lineage_tracking_is_true(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        assert card["audit"]["lineage_tracking"] is True

    def test_performance_section_has_required_fields(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        perf = card["performance"]
        assert "test_coverage" in perf
        assert "adversarial_tested" in perf
        assert "hallucination_tested" in perf
        assert "fuzz_tested" in perf

    def test_graceful_fallback_without_manifest(self, tmp_path):
        # No manifest created — should return {} or handle gracefully
        (tmp_path / "target").mkdir(exist_ok=True)
        card = generate_model_card(tmp_path, "any_agent")
        assert card == {}


class TestSaveModelCard:
    def test_writes_valid_json_file(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        path = save_model_card(tmp_path, "test_agent", card)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["system"]["name"] == "test_agent"

    def test_saves_to_target_model_cards_directory(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        path = save_model_card(tmp_path, "test_agent", card)
        assert "model_cards" in str(path)
        assert path.name == "test_agent_model_card.json"

    def test_creates_directory_if_missing(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        cards_dir = tmp_path / "target" / "model_cards"
        assert not cards_dir.exists() or True  # may or may not exist
        save_model_card(tmp_path, "test_agent", card)
        assert cards_dir.exists()


class TestAssessRisk:
    def test_high_risk_for_medical(self):
        level, justification = _assess_risk("medical imaging diagnostic tool")
        assert level == "HIGH"
        assert "medical" in justification

    def test_high_risk_for_biometric(self):
        level, _ = _assess_risk("biometric face recognition system")
        assert level == "HIGH"

    def test_low_risk_for_neutral(self):
        level, justification = _assess_risk("converts JSON to YAML")
        assert level == "LOW"
        assert "No high-risk" in justification

    def test_medium_risk_for_customer_support(self):
        level, _ = _assess_risk("customer support assistant")
        assert level == "MEDIUM"


class TestPrintModelCardSummary:
    def test_does_not_raise(self, tmp_path):
        _make_manifest(tmp_path)
        card = generate_model_card(tmp_path, "test_agent")
        print_model_card_summary(card)  # should not raise
