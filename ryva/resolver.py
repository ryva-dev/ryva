from __future__ import annotations
from pathlib import Path
from ryva.utils import load_yaml, parse_ref, console
from ryva.schemas import AgentSchema, ToolSchema, PipelineSchema, ProjectSchema
from pydantic import ValidationError


class ProjectResolver:
    def __init__(self, root: Path):
        self.root = root
        self.agents: dict[str, AgentSchema] = {}
        self.tools: dict[str, ToolSchema] = {}
        self.pipelines: dict[str, PipelineSchema] = {}
        self.project: ProjectSchema | None = None
        self.errors: list[str] = []

    def resolve(self) -> bool:
        self._load_project()
        self._load_agents()
        self._load_tools()
        self._load_pipelines()
        self._validate_refs()
        return len(self.errors) == 0

    def _load_project(self):
        path = self.root / "project.yml"
        try:
            data = load_yaml(path)
            self.project = ProjectSchema(**data)
        except Exception as e:
            self.errors.append(f"project.yml: {e}")

    def _load_agents(self):
        for path in (self.root / "agents").glob("*.yml"):
            try:
                data = load_yaml(path)
                agent = AgentSchema(**data)
                self.agents[agent.name] = agent
            except ValidationError as e:
                self.errors.append(f"agents/{path.name}: {e.error_count()} validation error(s) — {e.errors()[0]['msg']}")
            except Exception as e:
                self.errors.append(f"agents/{path.name}: {e}")

    def _load_tools(self):
        for path in (self.root / "tools").glob("*.yml"):
            try:
                data = load_yaml(path)
                tool = ToolSchema(**data)
                self.tools[tool.name] = tool
            except ValidationError as e:
                self.errors.append(f"tools/{path.name}: {e.error_count()} validation error(s) — {e.errors()[0]['msg']}")
            except Exception as e:
                self.errors.append(f"tools/{path.name}: {e}")

    def _load_pipelines(self):
        for path in (self.root / "pipelines").glob("*.yml"):
            try:
                data = load_yaml(path)
                pipeline = PipelineSchema(**data)
                self.pipelines[pipeline.name] = pipeline
            except ValidationError as e:
                self.errors.append(f"pipelines/{path.name}: {e.error_count()} validation error(s) — {e.errors()[0]['msg']}")
            except Exception as e:
                self.errors.append(f"pipelines/{path.name}: {e}")

    def _validate_refs(self):
        for name, agent in self.agents.items():
            if agent.prompt:
                try:
                    kind, ref_name = parse_ref(agent.prompt)
                    prompt_path = self.root / "prompts" / f"{ref_name}.j2"
                    if not prompt_path.exists():
                        self.errors.append(f"agents/{name}: prompt ref '{agent.prompt}' not found at {prompt_path}")
                except ValueError as e:
                    self.errors.append(f"agents/{name}: {e}")

            for tool_ref in agent.tools:
                try:
                    _, ref_name = parse_ref(tool_ref)
                    if ref_name not in self.tools:
                        self.errors.append(f"agents/{name}: tool ref '{tool_ref}' not found")
                except ValueError as e:
                    self.errors.append(f"agents/{name}: {e}")

    def to_manifest(self) -> dict:
        return {
            "ryva_version": "0.1.0",
            "project": self.project.model_dump() if self.project else {},
            "agents": {n: a.model_dump() for n, a in self.agents.items()},
            "tools": {n: t.model_dump() for n, t in self.tools.items()},
            "pipelines": {n: p.model_dump() for n, p in self.pipelines.items()},
        }