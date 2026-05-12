from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class FieldSchema(BaseModel):
    type: str
    required: bool = False
    default: Any = None
    enum: Optional[list[str]] = None
    min_length: Optional[int] = None
    range: Optional[list[float]] = None


class IOSchema(BaseModel):
    schema_: dict[str, FieldSchema] = Field(default_factory=dict, alias="schema")

    model_config = {"populate_by_name": True}


class MemoryConfig(BaseModel):
    strategy: str = "none"
    window_size: int = 10


class TestDefinition(BaseModel):
    type: str
    threshold: Optional[int] = None
    key: Optional[str] = None
    scorer: Optional[str] = None


class AgentSchema(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    model: Optional[str] = None
    prompt: Optional[str] = None
    tools: list[str] = Field(default_factory=list)
    input: Optional[IOSchema] = None
    output: Optional[IOSchema] = None
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    tests: list[TestDefinition] = Field(default_factory=list)


class ToolSchema(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    implementation: str
    function: str = "run"
    input: Optional[IOSchema] = None
    output: Optional[IOSchema] = None
    tests: list[TestDefinition] = Field(default_factory=list)


class PipelineStep(BaseModel):
    name: str
    agent: Optional[str] = None
    tool: Optional[str] = None
    input: Optional[dict[str, Any]] = None


class PipelineSchema(BaseModel):
    name: str
    description: str = ""
    input: Optional[IOSchema] = None
    steps: list[PipelineStep] = Field(default_factory=list)
    output: Optional[dict[str, str]] = None


class ProviderConfig(BaseModel):
    model: str
    api_key: str = ""


class TargetConfig(BaseModel):
    type: str = "local"
    project_id: Optional[str] = None


class ProjectSchema(BaseModel):
    name: str
    version: str = "0.1.0"
    providers: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    targets: dict[str, TargetConfig] = Field(default_factory=dict)