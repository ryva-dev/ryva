from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FieldSchema(BaseModel):
    type: str
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    min_length: int | None = None
    range: list[float] | None = None


class IOSchema(BaseModel):
    schema_: dict[str, FieldSchema] = Field(default_factory=dict, alias="schema")

    model_config = ConfigDict(populate_by_name=True)


class MemoryConfig(BaseModel):
    strategy: str = "none"
    window_size: int = 10


class TestDefinition(BaseModel):
    type: str
    threshold: int | None = None
    key: str | None = None
    scorer: str | None = None


class AgentSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "1.0.0"
    description: str = ""
    model: str | None = None
    prompt: str | None = None
    tools: list[str] = Field(default_factory=list)
    input: IOSchema | None = None
    output: IOSchema | None = None
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    tests: list[TestDefinition] = Field(default_factory=list)


class ToolSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "1.0.0"
    description: str = ""
    implementation: str
    function: str = "run"
    input: IOSchema | None = None
    output: IOSchema | None = None
    tests: list[TestDefinition] = Field(default_factory=list)


class PipelineStep(BaseModel):
    name: str
    agent: str | None = None
    tool: str | None = None
    input: dict[str, Any] | None = None


class PipelineSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str = ""
    input: IOSchema | None = None
    steps: list[PipelineStep] = Field(default_factory=list)
    output: dict[str, str] | None = None


class ProviderConfig(BaseModel):
    model: str
    api_key: str = ""


class TargetConfig(BaseModel):
    type: str = "local"
    project_id: str | None = None


class ProjectSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    version: str = "0.1.0"
    providers: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    targets: dict[str, TargetConfig] = Field(default_factory=dict)

