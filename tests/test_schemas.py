from __future__ import annotations

import pytest
from pydantic import ValidationError

from ryva.schemas import (
    AgentSchema,
    FieldSchema,
    IOSchema,
    PipelineSchema,
    ProjectSchema,
    TestDefinition,
    ToolSchema,
)


class TestAgentSchema:
    def test_minimal(self):
        agent = AgentSchema(name="my-agent")
        assert agent.name == "my-agent"
        assert agent.version == "1.0.0"
        assert agent.description == ""
        assert agent.tools == []
        assert agent.tags == []

    def test_full(self):
        agent = AgentSchema(
            name="summarizer",
            version="2.0.0",
            description="Summarizes text",
            model="claude-sonnet-4-5",
            prompt="ref(prompts/summarize)",
            tools=["ref(tools/search)"],
            tags=["nlp", "prod"],
        )
        assert agent.model == "claude-sonnet-4-5"
        assert len(agent.tools) == 1
        assert len(agent.tags) == 2

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            AgentSchema()

    def test_default_memory_strategy(self):
        agent = AgentSchema(name="a")
        assert agent.memory.strategy == "none"
        assert agent.memory.window_size == 10

    def test_with_tests(self):
        agent = AgentSchema(
            name="a",
            tests=[{"type": "schema"}, {"type": "latency_under_ms", "threshold": 3000}],
        )
        assert len(agent.tests) == 2
        assert agent.tests[1].threshold == 3000


class TestToolSchema:
    def test_minimal(self):
        tool = ToolSchema(name="search", implementation="tools.search")
        assert tool.function == "run"
        assert tool.version == "1.0.0"

    def test_missing_implementation_raises(self):
        with pytest.raises(ValidationError):
            ToolSchema(name="search")

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ToolSchema(implementation="tools.search")


class TestPipelineSchema:
    def test_minimal(self):
        pipeline = PipelineSchema(name="my-pipeline")
        assert pipeline.steps == []
        assert pipeline.description == ""

    def test_with_steps(self):
        pipeline = PipelineSchema(
            name="pipeline",
            steps=[
                {"name": "step1", "agent": "ref(agents/summarizer)"},
                {"name": "step2", "tool": "ref(tools/search)"},
            ],
        )
        assert len(pipeline.steps) == 2
        assert pipeline.steps[0].name == "step1"
        assert pipeline.steps[1].tool == "ref(tools/search)"

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            PipelineSchema()


class TestProjectSchema:
    def test_minimal(self):
        project = ProjectSchema(name="my-project")
        assert project.version == "0.1.0"
        assert project.providers == {}
        assert project.runtime == {}

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ProjectSchema()


class TestFieldSchema:
    def test_basic(self):
        field = FieldSchema(type="str")
        assert field.required is False
        assert field.default is None

    def test_with_enum(self):
        field = FieldSchema(type="str", enum=["a", "b", "c"])
        assert field.enum == ["a", "b", "c"]

    def test_with_range(self):
        field = FieldSchema(type="float", range=[0.0, 1.0])
        assert field.range == [0.0, 1.0]


class TestIOSchema:
    def test_empty(self):
        io = IOSchema(**{"schema": {}})
        assert io.schema_ == {}

    def test_with_fields(self):
        io = IOSchema(**{"schema": {"topic": {"type": "str", "required": True}}})
        assert "topic" in io.schema_
        assert io.schema_["topic"].type == "str"
        assert io.schema_["topic"].required is True


class TestTestDefinition:
    def test_schema_type(self):
        t = TestDefinition(type="schema")
        assert t.type == "schema"
        assert t.threshold is None

    def test_latency_with_threshold(self):
        t = TestDefinition(type="latency_under_ms", threshold=5000)
        assert t.threshold == 5000
