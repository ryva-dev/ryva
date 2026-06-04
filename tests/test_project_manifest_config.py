from __future__ import annotations

from pathlib import Path

from ryva.compiler import compile_project
from ryva.schemas import AgentSchema, ProjectSchema
from ryva.utils import load_manifest


def _write_project(root: Path, extra: str = "") -> None:
    (root / "agents").mkdir(exist_ok=True)
    (root / "tools").mkdir(exist_ok=True)
    (root / "pipelines").mkdir(exist_ok=True)
    (root / "prompts").mkdir(exist_ok=True)
    (root / "project.yml").write_text(
        "name: test-project\nversion: '0.1.0'\n" + extra
    )


class TestProjectSchemaExtraFields:
    def test_pii_masking_preserved_in_schema(self):
        schema = ProjectSchema(**{
            "name": "test",
            "pii_masking": {"enabled": True, "entities": ["ssn", "email"]},
        })
        dumped = schema.model_dump()
        assert "pii_masking" in dumped
        assert dumped["pii_masking"]["enabled"] is True

    def test_budget_preserved_in_schema(self):
        schema = ProjectSchema(**{
            "name": "test",
            "budget": {"monthly_limit_usd": 50.0, "alert_threshold": 0.8},
        })
        dumped = schema.model_dump()
        assert "budget" in dumped
        assert dumped["budget"]["monthly_limit_usd"] == 50.0

    def test_policies_preserved_in_schema(self):
        schema = ProjectSchema(**{
            "name": "test",
            "policies": [{"name": "no-profanity", "check": "keyword_forbidden"}],
        })
        dumped = schema.model_dump()
        assert "policies" in dumped
        assert len(dumped["policies"]) == 1

    def test_unknown_fields_do_not_cause_validation_error(self):
        schema = ProjectSchema(**{
            "name": "test",
            "custom_field": "custom_value",
            "nested": {"a": 1, "b": 2},
        })
        assert schema is not None

    def test_standard_fields_still_work(self):
        schema = ProjectSchema(**{
            "name": "my-project",
            "version": "1.2.3",
            "providers": {"default": "anthropic"},
        })
        assert schema.name == "my-project"
        assert schema.version == "1.2.3"


class TestAgentSchemaExtraFields:
    def test_extra_agent_fields_preserved(self):
        schema = AgentSchema(**{
            "name": "my_agent",
            "description": "test",
            "custom_meta": {"team": "ai", "contact": "alice"},
        })
        dumped = schema.model_dump()
        assert "custom_meta" in dumped

    def test_standard_agent_fields_still_work(self):
        schema = AgentSchema(**{
            "name": "summarizer",
            "version": "2.0.0",
            "description": "summarizes text",
            "tools": [],
        })
        assert schema.name == "summarizer"
        assert schema.version == "2.0.0"


class TestPiiMaskingPreservedThroughCompile:
    def test_pii_masking_survives_compile(self, tmp_path):
        _write_project(tmp_path, extra=(
            "pii_masking:\n"
            "  enabled: true\n"
            "  entities:\n"
            "    - ssn\n"
            "    - email\n"
            "  mask: '[REDACTED]'\n"
        ))
        ok = compile_project(tmp_path)
        assert ok
        manifest = load_manifest(tmp_path)
        project = manifest["project"]
        assert "pii_masking" in project, (
            "pii_masking was silently dropped during compile — "
            "users think they are protected but they are not"
        )
        assert project["pii_masking"]["enabled"] is True

    def test_budget_survives_compile(self, tmp_path):
        _write_project(tmp_path, extra=(
            "budget:\n"
            "  monthly_limit_usd: 25.00\n"
            "  alert_threshold: 0.8\n"
        ))
        ok = compile_project(tmp_path)
        assert ok
        manifest = load_manifest(tmp_path)
        project = manifest["project"]
        assert "budget" in project
        assert project["budget"]["monthly_limit_usd"] == 25.00

    def test_inline_policies_survive_compile(self, tmp_path):
        _write_project(tmp_path, extra=(
            "policies:\n"
            "  - name: no-bad-words\n"
            "    check: keyword_forbidden\n"
            "    keywords:\n"
            "      - badword\n"
            "    severity: error\n"
        ))
        ok = compile_project(tmp_path)
        assert ok
        manifest = load_manifest(tmp_path)
        project = manifest["project"]
        assert "policies" in project
        assert project["policies"][0]["name"] == "no-bad-words"
