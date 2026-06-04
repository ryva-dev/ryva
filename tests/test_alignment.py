from __future__ import annotations

import json

from ryva.alignment import _apply_rule, check_output, load_policies

# ---------------------------------------------------------------------------
# _apply_rule
# ---------------------------------------------------------------------------

class TestKeywordForbidden:
    def test_passes_when_no_match(self):
        ok, _ = _apply_rule("keyword_forbidden", "Hello world", {"keywords": ["bad"]})
        assert ok

    def test_fails_on_match(self):
        ok, detail = _apply_rule("keyword_forbidden", "This is bad", {"keywords": ["bad"]})
        assert not ok
        assert "bad" in detail

    def test_case_insensitive_by_default(self):
        ok, _ = _apply_rule("keyword_forbidden", "This is BAD", {"keywords": ["bad"]})
        assert not ok

    def test_case_sensitive_mode(self):
        ok, _ = _apply_rule(
            "keyword_forbidden", "This is BAD",
            {"keywords": ["bad"], "case_sensitive": True}
        )
        assert ok

    def test_multiple_keywords_any_triggers(self):
        ok, _ = _apply_rule(
            "keyword_forbidden", "competitor is here",
            {"keywords": ["rival", "competitor"]}
        )
        assert not ok

    def test_empty_keywords_always_passes(self):
        ok, _ = _apply_rule("keyword_forbidden", "anything", {"keywords": []})
        assert ok


class TestMustContain:
    def test_passes_when_present(self):
        ok, _ = _apply_rule("must_contain", "See source below", {"text": "source"})
        assert ok

    def test_fails_when_absent(self):
        ok, detail = _apply_rule("must_contain", "No citation here", {"text": "source"})
        assert not ok
        assert "source" in detail

    def test_case_insensitive_by_default(self):
        ok, _ = _apply_rule("must_contain", "See SOURCE here", {"text": "source"})
        assert ok


class TestMustContainPattern:
    def test_passes_on_match(self):
        ok, _ = _apply_rule("must_contain_pattern", "Source: Wikipedia", {"pattern": r"Source:"})
        assert ok

    def test_fails_when_no_match(self):
        ok, _ = _apply_rule("must_contain_pattern", "No citation", {"pattern": r"Source:"})
        assert not ok

    def test_case_insensitive_by_default(self):
        ok, _ = _apply_rule("must_contain_pattern", "source: wiki", {"pattern": r"Source:"})
        assert ok


class TestMaxLength:
    def test_passes_when_within(self):
        ok, _ = _apply_rule("max_length", "short", {"max": 100})
        assert ok

    def test_fails_when_exceeded(self):
        ok, detail = _apply_rule("max_length", "a" * 101, {"max": 100})
        assert not ok
        assert "101" in detail

    def test_exact_boundary_passes(self):
        ok, _ = _apply_rule("max_length", "a" * 100, {"max": 100})
        assert ok


class TestMinLength:
    def test_passes_when_sufficient(self):
        ok, _ = _apply_rule("min_length", "hello world", {"min": 5})
        assert ok

    def test_fails_when_too_short(self):
        ok, detail = _apply_rule("min_length", "hi", {"min": 10})
        assert not ok
        assert "2" in detail


class TestJsonFieldRequired:
    def test_passes_when_field_present(self):
        ok, _ = _apply_rule("json_field_required", '{"summary": "text"}', {"field": "summary"})
        assert ok

    def test_fails_when_field_missing(self):
        ok, detail = _apply_rule("json_field_required", '{"other": 1}', {"field": "summary"})
        assert not ok
        assert "summary" in detail

    def test_fails_on_invalid_json(self):
        ok, _ = _apply_rule("json_field_required", "not json", {"field": "summary"})
        assert not ok


class TestJsonFieldForbidden:
    def test_passes_when_field_absent(self):
        ok, _ = _apply_rule("json_field_forbidden", '{"a": 1}', {"field": "secret"})
        assert ok

    def test_fails_when_field_present(self):
        ok, _ = _apply_rule("json_field_forbidden", '{"secret": "data"}', {"field": "secret"})
        assert not ok

    def test_passes_on_non_json(self):
        ok, _ = _apply_rule("json_field_forbidden", "plain text", {"field": "secret"})
        assert ok


class TestUnknownRule:
    def test_unknown_rule_passes(self):
        ok, _ = _apply_rule("does_not_exist", "anything", {})
        assert ok


# ---------------------------------------------------------------------------
# check_output
# ---------------------------------------------------------------------------

class TestCheckOutput:
    def _policy(self, name, check, **kwargs):
        return {"name": name, "check": check, "severity": "error", **kwargs}

    def test_no_violations_when_all_pass(self):
        policies = [self._policy("no_bad", "keyword_forbidden", keywords=["bad"])]
        assert check_output("all good here", policies) == []

    def test_returns_violation_on_failure(self):
        policies = [self._policy("no_bad", "keyword_forbidden", keywords=["bad"])]
        violations = check_output("this is bad", policies)
        assert len(violations) == 1
        assert violations[0]["policy"] == "no_bad"

    def test_multiple_policies_all_checked(self):
        policies = [
            self._policy("no_bad", "keyword_forbidden", keywords=["bad"]),
            {"name": "min_len", "check": "min_length", "severity": "warning", "min": 100},
        ]
        violations = check_output("bad", policies)
        assert len(violations) == 2

    def test_severity_preserved(self):
        policies = [{
            "name": "warn_rule",
            "check": "keyword_forbidden",
            "keywords": ["warn_word"],
            "severity": "warning",
        }]
        violations = check_output("warn_word here", policies)
        assert violations[0]["severity"] == "warning"

    def test_empty_policies_no_violations(self):
        assert check_output("anything", []) == []


# ---------------------------------------------------------------------------
# load_policies
# ---------------------------------------------------------------------------

class TestLoadPolicies:
    def test_loads_from_project(self, tmp_path):
        project = {"policies": [{"name": "p1", "check": "max_length", "max": 100}]}
        result = load_policies(tmp_path, project)
        assert len(result) == 1

    def test_loads_from_policies_yml(self, tmp_path):
        (tmp_path / "policies.yml").write_text(
            "policies:\n  - name: p2\n    check: min_length\n    min: 5\n"
        )
        result = load_policies(tmp_path, {})
        assert len(result) == 1
        assert result[0]["name"] == "p2"

    def test_merges_both_sources(self, tmp_path):
        (tmp_path / "policies.yml").write_text(
            "policies:\n  - name: from_file\n    check: max_length\n    max: 100\n"
        )
        project = {"policies": [{"name": "from_project", "check": "min_length", "min": 1}]}
        result = load_policies(tmp_path, project)
        assert len(result) == 2

    def test_no_config_returns_empty(self, tmp_path):
        assert load_policies(tmp_path, {}) == []


# ---------------------------------------------------------------------------
# Code fence stripping (Fix 2)
# ---------------------------------------------------------------------------

class TestCodeFenceStripping:
    def test_json_in_fences_passes_json_field_required(self):
        fenced = '```json\n{"summary": "hello", "count": 5}\n```'
        ok, detail = _apply_rule("json_field_required", fenced, {"field": "summary"})
        assert ok, f"False positive: {detail}"

    def test_plain_json_still_passes_json_field_required(self):
        ok, _ = _apply_rule("json_field_required", '{"key": "value"}', {"field": "key"})
        assert ok

    def test_json_in_backtick_fences_no_language_tag(self):
        fenced = '```\n{"field": true}\n```'
        ok, _ = _apply_rule("json_field_required", fenced, {"field": "field"})
        assert ok

    def test_fenced_json_missing_field_still_fails(self):
        fenced = '```json\n{"other": "value"}\n```'
        ok, detail = _apply_rule("json_field_required", fenced, {"field": "missing"})
        assert not ok
        assert "missing" in detail

    def test_fenced_json_passes_json_field_forbidden(self):
        fenced = '```json\n{"safe_field": true}\n```'
        ok, _ = _apply_rule("json_field_forbidden", fenced, {"field": "bad_field"})
        assert ok

    def test_keyword_forbidden_checks_content_not_fence_syntax(self):
        fenced = '```json\n{"result": "clean output"}\n```'
        ok, _ = _apply_rule("keyword_forbidden", fenced, {"keywords": ["badword"]})
        assert ok

    def test_check_output_strips_fences_for_all_policies(self):
        fenced = '```json\n{"summary": "all good", "status": "ok"}\n```'
        policies = [
            {"check": "json_field_required", "name": "needs-summary", "field": "summary", "severity": "error"},
            {"check": "keyword_forbidden", "name": "no-bad", "keywords": ["forbidden"], "severity": "error"},
        ]
        violations = check_output(fenced, policies)
        assert violations == [], f"False positives: {violations}"


# ---------------------------------------------------------------------------
# keyword_forbidden — negation-awareness (Fix 2)
# ---------------------------------------------------------------------------

class TestKeywordForbiddenNegation:
    """Compliant outputs that mention forbidden terms in negated context must pass."""

    _NEGATED = [
        "This system does not provide diagnosis",
        "No diagnosis is made by this system",
        "The system never provides a diagnosis",
        "patient_care_decision is always false — no diagnosis provided",
        "This is not a diagnosis tool",
        "Refusal to provide diagnosis: this is an administrative routing system",
        "diagnosis is prohibited by design",
    ]

    _AFFIRMATIVE = [
        "The diagnosis is hypertension",
        "Based on symptoms, diagnosis: type 2 diabetes",
        "I can provide a diagnosis for your condition",
    ]

    def test_negated_context_passes(self):
        for text in self._NEGATED:
            ok, detail = _apply_rule("keyword_forbidden", text, {"keywords": ["diagnosis"]})
            assert ok, f"False positive on negated text: {text!r}  detail={detail!r}"

    def test_affirmative_context_fails(self):
        for text in self._AFFIRMATIVE:
            ok, _ = _apply_rule("keyword_forbidden", text, {"keywords": ["diagnosis"]})
            assert not ok, f"Should have violated for affirmative text: {text!r}"

    def test_singular_keyword_key_supported(self):
        """Policy may use 'keyword' (str) instead of 'keywords' (list)."""
        ok, _ = _apply_rule("keyword_forbidden", "diagnosis confirmed", {"keyword": "diagnosis"})
        assert not ok

    def test_plain_forbidden_word_still_fails(self):
        """Existing simple violation cases must still be caught."""
        ok, _ = _apply_rule("keyword_forbidden", "This is bad", {"keywords": ["bad"]})
        assert not ok

    def test_multiple_occurrences_all_negated_passes(self):
        text = "no diagnosis given, never provided a diagnosis to users"
        ok, _ = _apply_rule("keyword_forbidden", text, {"keywords": ["diagnosis"]})
        assert ok

    def test_mixed_negated_and_affirmative_fails(self):
        """If ANY occurrence is affirmative the policy must fire."""
        text = "no diagnosis in most cases but diagnosis: hypertension was reported"
        ok, _ = _apply_rule("keyword_forbidden", text, {"keywords": ["diagnosis"]})
        assert not ok


# ---------------------------------------------------------------------------
# forbidden_pattern — JSON-aware regex (Fix 3)
# ---------------------------------------------------------------------------

_EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"


class TestForbiddenPattern:
    def test_field_name_does_not_trigger_email_pattern(self):
        """Field name 'email_status' must not be matched by an email regex."""
        payload = json.dumps({
            "email_status": "verified",
            "summary": "Patient called about appointment",
            "routing": "scheduling",
        })
        ok, _ = _apply_rule("forbidden_pattern", payload, {"pattern": _EMAIL_PATTERN})
        assert ok

    def test_actual_email_in_value_triggers_violation(self):
        """A real email address inside a JSON value must be caught."""
        payload = json.dumps({"summary": "Contact patient at john.doe@example.com"})
        ok, detail = _apply_rule("forbidden_pattern", payload, {"pattern": _EMAIL_PATTERN})
        assert not ok
        assert "pattern" in detail.lower() or "forbidden" in detail.lower()

    def test_non_json_text_also_checked(self):
        """Plain text output (not JSON) is still checked against the pattern."""
        ok, _ = _apply_rule("forbidden_pattern", "Call alice@example.com now", {"pattern": _EMAIL_PATTERN})
        assert not ok

    def test_no_email_in_plain_text_passes(self):
        ok, _ = _apply_rule("forbidden_pattern", "No contact info here", {"pattern": _EMAIL_PATTERN})
        assert ok

    def test_nested_json_values_checked(self):
        """Email nested inside a list value must be caught."""
        payload = json.dumps({"contacts": [{"note": "reach out to bob@example.com"}]})
        ok, _ = _apply_rule("forbidden_pattern", payload, {"pattern": _EMAIL_PATTERN})
        assert not ok

    def test_case_insensitive_by_default(self):
        ok, _ = _apply_rule("forbidden_pattern", json.dumps({"v": "BAD word"}), {"pattern": r"bad"})
        assert not ok

    def test_case_sensitive_respects_flag(self):
        ok, _ = _apply_rule(
            "forbidden_pattern", json.dumps({"v": "BAD word"}),
            {"pattern": r"bad", "case_sensitive": True}
        )
        assert ok

    def test_fenced_json_values_checked(self):
        """Fenced JSON output values are also checked (fences stripped first)."""
        fenced = '```json\n{"summary": "contact me at eve@example.com"}\n```'
        ok, _ = _apply_rule("forbidden_pattern", fenced, {"pattern": _EMAIL_PATTERN})
        assert not ok
