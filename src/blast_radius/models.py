from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


NodeKind = Literal["source", "transform", "leaf"]


@dataclass(frozen=True)
class PartitionSpec:
    column: str
    value_expr: str


@dataclass(frozen=True)
class SLA:
    freshness_ticks: int
    null_rate_field: str | None = None
    max_null_rate: float = 0.0
    required_field: str | None = None


@dataclass
class Node:
    id: str
    kind: NodeKind
    schema: dict[str, str]
    upstream: tuple[str, ...] = ()
    baseline_cost: float = 0.0
    partition_filter: PartitionSpec | None = None
    sla: SLA | None = None
    transform_mappings: dict[str, tuple[str, str]] = field(default_factory=dict)

    def has_field(self, field_name: str) -> bool:
        return field_name in self.schema

    def rename_field(self, old_field: str, new_field: str) -> None:
        field_type = self.schema.pop(old_field)
        self.schema[new_field] = field_type


@dataclass(frozen=True)
class ToolResult:
    content: Any
    reward: float
    finished: bool
    tick: int
    alerts: tuple[str, ...]


@dataclass(frozen=True)
class PendingFix:
    incident_kind: str
    apply_tick: int
    resolve_tick: int
