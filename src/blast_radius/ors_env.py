from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from blast_radius.models import ToolResult
from blast_radius.world import BlastRadiusWorld

try:  # pragma: no cover - exercised when the OpenReward SDK is installed.
    from openreward.environments import (
        Environment,
        JSONObject,
        Server,
        Split,
        TextBlock,
        ToolOutput,
        tool,
    )

    OPENREWARD_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - local test fallback.
    OPENREWARD_AVAILABLE = False
    JSONObject = dict[str, Any]

    class Environment:  # type: ignore[no-redef]
        def __init__(self, task_spec: JSONObject | None = None, secrets: dict[str, str] | None = None):
            self.task_spec = task_spec or {}
            self.secrets = secrets or {}

    class Server:  # type: ignore[no-redef]
        def __init__(self, envs: list[type[Environment]]):
            self.envs = envs

        def run(self, port: int = 8080) -> None:
            raise RuntimeError(
                "OpenReward SDK is not installed. Install with `pip install -e .[ors]`."
            )

    class Split:  # type: ignore[no-redef]
        def __init__(self, name: str, type: str):
            self.name = name
            self.type = type

    class TextBlock:  # type: ignore[no-redef]
        def __init__(self, text: str, type: str = "text"):
            self.text = text
            self.type = type

    class ToolOutput:  # type: ignore[no-redef]
        def __init__(self, blocks: list[TextBlock], reward: float, finished: bool):
            self.blocks = blocks
            self.reward = reward
            self.finished = finished

    def tool(func):  # type: ignore[no-redef]
        return func


class BlastRadiusTaskSpec(BaseModel):
    id: str
    seed: int
    difficulty: str = "v1"


class TableParams(BaseModel):
    table: str


class QuerySampleParams(BaseModel):
    table: str
    n: int = Field(default=10, ge=1, le=100)


class JobHistoryParams(BaseModel):
    table: str
    last_n: int = Field(default=20, ge=1, le=100)


class TailLogsParams(BaseModel):
    resource: str
    lines: int = Field(default=50, ge=1, le=200)


class QueryPlanParams(BaseModel):
    job_id: str


class TraceLineageParams(BaseModel):
    table: str
    depth: int = Field(default=2, ge=1, le=5)


class DiagnosisParams(BaseModel):
    root_cause_node: str
    incident_kind: str


class FixParams(BaseModel):
    spec: dict[str, Any]


class WaitParams(BaseModel):
    ticks: int = Field(ge=0, le=250)


def _tasks_for_split(split: str) -> list[JSONObject]:
    if split == "train":
        seeds = range(80)
    elif split in {"eval", "test"}:
        seeds = range(80, 100)
    else:
        raise ValueError(f"unknown split: {split}")
    return [
        {"id": f"seed_{seed}", "seed": seed, "difficulty": "v1"}
        for seed in seeds
    ]


def _to_tool_output(result: ToolResult) -> ToolOutput:
    payload = {
        "tick": result.tick,
        "alerts": list(result.alerts),
        "result": result.content,
    }
    return ToolOutput(
        blocks=[TextBlock(type="text", text=json.dumps(payload, indent=2, sort_keys=True))],
        reward=result.reward,
        finished=result.finished,
    )


class BlastRadiusEnv(Environment):
    """ORS environment wrapper for the BlastRadius core simulator."""

    def __init__(self, task_spec: JSONObject | None = None, secrets: dict[str, str] | None = None):
        super().__init__(task_spec or {}, secrets or {})
        self.config = BlastRadiusTaskSpec.model_validate(task_spec or {"id": "seed_0", "seed": 0})
        self.world = BlastRadiusWorld.from_seed(self.config.seed)

    @classmethod
    def list_splits(cls) -> list[Split]:
        return [
            Split(name="train", type="train"),
            Split(name="eval", type="test"),
        ]

    @classmethod
    def list_tasks(cls, split: str) -> list[JSONObject]:
        return _tasks_for_split(split)

    def get_prompt(self) -> list[TextBlock]:
        prompt = (
            "You are diagnosing BlastRadius, a simulated GCP-shaped data platform. "
            "The true data lineage and drift events are hidden. Use tools to inspect "
            "schemas, samples, logs, job history, query plans, and partial lineage. "
            "Diagnose root causes, apply fixes, and keep the system healthy until "
            "the episode finishes. Do not assume trace_lineage is complete."
        )
        return [TextBlock(type="text", text=prompt)]

    @tool
    def list_tables(self) -> ToolOutput:
        """List visible BigQuery-shaped tables and dashboards."""
        return _to_tool_output(self.world.list_tables())

    @tool
    def inspect_schema(self, params: TableParams) -> ToolOutput:
        """Inspect a table schema. Results may be slightly stale."""
        return _to_tool_output(self.world.inspect_schema(params.table))

    @tool
    def query_sample(self, params: QuerySampleParams) -> ToolOutput:
        """Query a random sample from a table."""
        return _to_tool_output(self.world.query_sample(params.table, params.n))

    @tool
    def get_job_history(self, params: JobHistoryParams) -> ToolOutput:
        """Inspect recent jobs for a table, including truncated SQL and cost hints."""
        return _to_tool_output(self.world.get_job_history(params.table, params.last_n))

    @tool
    def tail_logs(self, params: TailLogsParams) -> ToolOutput:
        """Tail Cloud-Logging-shaped lines for a resource. Relevant lines may be dropped."""
        return _to_tool_output(self.world.tail_logs(params.resource, params.lines))

    @tool
    def inspect_query_plan(self, params: QueryPlanParams) -> ToolOutput:
        """Inspect a known job's query plan."""
        return _to_tool_output(self.world.inspect_query_plan(params.job_id))

    @tool
    def trace_lineage(self, params: TraceLineageParams) -> ToolOutput:
        """Return recent observed lineage edges only. This is not ground truth."""
        return _to_tool_output(self.world.trace_lineage(params.table, params.depth))

    @tool
    def run_data_test(self, params: TableParams) -> ToolOutput:
        """Run freshness, row count, schema, and sample correctness tests for a table."""
        return _to_tool_output(self.world.run_data_test(params.table))

    @tool
    def submit_diagnosis(self, params: DiagnosisParams) -> ToolOutput:
        """Submit an incident diagnosis for milestone reward."""
        return _to_tool_output(
            self.world.submit_diagnosis(params.root_cause_node, params.incident_kind)
        )

    @tool
    def apply_fix(self, params: FixParams) -> ToolOutput:
        """Apply a fix specification to the simulated platform."""
        return _to_tool_output(self.world.apply_fix(params.spec))

    @tool
    def wait(self, params: WaitParams) -> ToolOutput:
        """Advance simulated time, useful for verification after a fix."""
        return _to_tool_output(self.world.wait(params.ticks))


def run_server(port: int = 8080) -> None:
    if not OPENREWARD_AVAILABLE:
        raise RuntimeError(
            "OpenReward SDK is not installed. Install with `pip install -e .[ors]`."
        )
    Server([BlastRadiusEnv]).run(port=port)
