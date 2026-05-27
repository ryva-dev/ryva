from __future__ import annotations

import json

import pytest

from ryva.runner import _parse_output, _resolve_prompt


class TestParseOutput:
    def test_valid_json_object(self):
        text = 'Here is the result: {"key": "value", "num": 42}'
        assert _parse_output(text) == {"key": "value", "num": 42}

    def test_pure_json(self):
        data = {"summary": "hello world", "score": 0.9}
        assert _parse_output(json.dumps(data)) == data

    def test_no_json_returns_raw(self):
        text = "This has no JSON object in it at all."
        assert _parse_output(text) == {"raw_output": text}

    def test_invalid_json_returns_raw(self):
        text = "{ broken }"
        assert _parse_output(text) == {"raw_output": text}

    def test_empty_string(self):
        assert _parse_output("") == {"raw_output": ""}

    def test_nested_json(self):
        data = {"outer": {"inner": [1, 2, 3]}}
        text = f"Output: {json.dumps(data)}"
        assert _parse_output(text) == data

    def test_json_with_surrounding_text(self):
        text = 'Here you go: {"result": true} — done.'
        assert _parse_output(text) == {"result": True}


class TestResolvePrompt:
    def test_no_prompt_ref_returns_json_input(self, tmp_path):
        input_data = {"text": "hello", "lang": "en"}
        result = _resolve_prompt(tmp_path, {}, input_data)
        assert result == json.dumps(input_data)

    def test_renders_jinja_template(self, tmp_path):
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "greet.j2").write_text("Hello, {{ input.name }}!")
        result = _resolve_prompt(tmp_path, {"prompt": "ref(prompts/greet)"}, {"name": "Alice"})
        assert result == "Hello, Alice!"

    def test_template_with_conditional(self, tmp_path):
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "cond.j2").write_text(
            "{% if input.flag %}yes{% else %}no{% endif %}"
        )
        assert _resolve_prompt(tmp_path, {"prompt": "ref(prompts/cond)"}, {"flag": True}) == "yes"
        assert _resolve_prompt(tmp_path, {"prompt": "ref(prompts/cond)"}, {"flag": False}) == "no"

    def test_missing_template_raises(self, tmp_path):
        (tmp_path / "prompts").mkdir()
        with pytest.raises(FileNotFoundError):
            _resolve_prompt(tmp_path, {"prompt": "ref(prompts/missing)"}, {})

    def test_macro_auto_imported(self, tmp_path):
        (tmp_path / "prompts").mkdir()
        macros_dir = tmp_path / "macros"
        macros_dir.mkdir()
        (macros_dir / "helpers.j2").write_text(
            "{% macro shout(text) %}{{ text | upper }}{% endmacro %}"
        )
        (tmp_path / "prompts" / "main.j2").write_text("{{ shout(input.word) }}")
        result = _resolve_prompt(tmp_path, {"prompt": "ref(prompts/main)"}, {"word": "hello"})
        assert result == "HELLO"

    def test_invalid_ref_falls_back_to_name(self, tmp_path):
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "plain.j2").write_text("{{ input.x }}")
        # Non-ref prompt string treated as name directly
        result = _resolve_prompt(tmp_path, {"prompt": "plain"}, {"x": "42"})
        assert result == "42"
