from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from blast_radius.models import Node, PartitionSpec, PendingFix, SLA, ToolResult


SCHEMA_DRIFT = "schema_drift"
COST_EXPLOSION = "cost_explosion"


def _decay(tick: int) -> float:
    if tick < 50:
        return 1.0
    if tick >= 150:
        return 0.2
    return 1.0 - 0.8 * ((tick - 50) / 100)


def _ramp(tick: int) -> float:
    if tick < 50:
        return 0.2
    if tick >= 150:
        return 1.0
    return 0.2 + 0.8 * ((tick - 50) / 100)


def _canonical_nodes() -> dict[str, Node]:
    return {
        "raw.orders_api": Node(
            id="raw.orders_api",
            kind="source",
            schema={
                "order_id": "STRING",
                "customer_id": "STRING",
                "order_total": "FLOAT",
                "currency": "STRING",
                "order_ts": "TIMESTAMP",
                "ingest_date": "DATE",
            },
            baseline_cost=0.1,
        ),
        "raw.ad_spend": Node(
            id="raw.ad_spend",
            kind="source",
            schema={
                "campaign_id": "STRING",
                "spend": "FLOAT",
                "spend_date": "DATE",
                "ingest_date": "DATE",
            },
            baseline_cost=0.1,
        ),
        "raw.fx_rates": Node(
            id="raw.fx_rates",
            kind="source",
            schema={
                "currency": "STRING",
                "rate_to_usd": "FLOAT",
                "effective_date": "DATE",
                "ingest_date": "DATE",
            },
            baseline_cost=0.05,
        ),
        "stg.orders": Node(
            id="stg.orders",
            kind="transform",
            upstream=("raw.orders_api", "raw.fx_rates"),
            schema={
                "order_id": "STRING",
                "customer_id": "STRING",
                "order_total_usd": "FLOAT",
                "order_date": "DATE",
                "ingest_date": "DATE",
            },
            baseline_cost=0.3,
            partition_filter=PartitionSpec("ingest_date", "CURRENT_DATE() - 1"),
            transform_mappings={
                "order_total_usd": ("raw.orders_api", "order_total"),
                "order_date": ("raw.orders_api", "order_ts"),
            },
        ),
        "mart.daily_revenue": Node(
            id="mart.daily_revenue",
            kind="transform",
            upstream=("stg.orders",),
            schema={
                "revenue_date": "DATE",
                "total_revenue_usd": "FLOAT",
                "order_count": "INTEGER",
            },
            baseline_cost=0.4,
            partition_filter=PartitionSpec("ingest_date", "CURRENT_DATE() - 1"),
        ),
        "mart.marketing_roi": Node(
            id="mart.marketing_roi",
            kind="transform",
            upstream=("stg.orders", "raw.ad_spend"),
            schema={
                "spend_date": "DATE",
                "total_spend": "FLOAT",
                "attributed_revenue": "FLOAT",
                "roi": "FLOAT",
            },
            baseline_cost=0.5,
            partition_filter=PartitionSpec("ingest_date", "CURRENT_DATE() - 1"),
        ),
        "dash.revenue_health": Node(
            id="dash.revenue_health",
            kind="leaf",
            upstream=("mart.daily_revenue",),
            schema={"status": "STRING", "total_revenue_usd": "FLOAT"},
            baseline_cost=0.05,
            sla=SLA(
                freshness_ticks=30,
                null_rate_field="total_revenue_usd",
                max_null_rate=0.01,
            ),
        ),
        "dash.marketing_health": Node(
            id="dash.marketing_health",
            kind="leaf",
            upstream=("mart.marketing_roi",),
            schema={"status": "STRING", "roi": "FLOAT"},
            baseline_cost=0.05,
            sla=SLA(freshness_ticks=30, required_field="roi"),
        ),
    }


@dataclass
class BlastRadiusWorld:
    seed: int
    nodes: dict[str, Node]
    t_a: int
    t_b: int
    max_ticks: int = 250
    max_tool_calls: int = 200
    budget_rate: float = 2.0
    tick: int = 0
    tool_calls: int = 0
    cost_accumulated: float = 0.0
    score_total: float = 0.0
    drift_history: list[dict[str, Any]] = field(default_factory=list)
    correct_diagnoses: set[str] = field(default_factory=set)
    resolved_incidents: set[str] = field(default_factory=set)
    pending_fixes: list[PendingFix] = field(default_factory=list)
    terminal_penalty_paid: bool = False

    @classmethod
    def from_seed(cls, seed: int) -> "BlastRadiusWorld":
        rng = random.Random(seed)
        return cls(
            seed=seed,
            nodes=_canonical_nodes(),
            t_a=rng.randint(40, 80),
            t_b=rng.randint(100, 150),
        )

    @property
    def table_ids(self) -> tuple[str, ...]:
        return tuple(self.nodes)

    def list_tables(self) -> ToolResult:
        return self._tool_result(
            tool_cost=0.01,
            latency_ticks=0,
            action=lambda: (tuple(self.nodes), 0.0, 0.0),
        )

    def inspect_schema(self, table: str) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            node = self._require_node(table)
            return dict(node.schema), 0.0, 0.0

        return self._tool_result(tool_cost=0.05, latency_ticks=0, action=action)

    def query_sample(self, table: str, n: int = 10) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            self._require_node(table)
            rows = [self._sample_row(table, i) for i in range(n)]
            return rows, 0.0, 0.0

        return self._tool_result(
            tool_cost=0.1 + 0.01 * n,
            latency_ticks=1,
            action=action,
        )

    def get_job_history(self, table: str, last_n: int = 20) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            self._require_node(table)
            cost = self._node_cost(table)
            history = [
                {
                    "job_id": f"job_{table}_{max(0, self.tick - idx)}",
                    "table": table,
                    "tick": max(0, self.tick - idx),
                    "status": "SUCCESS",
                    "slot_ms": int(cost * 1000),
                    "query": self._query_text(table, truncated=True),
                }
                for idx in range(min(last_n, 5))
            ]
            return history, 0.0, 0.0

        return self._tool_result(tool_cost=0.05, latency_ticks=0, action=action)

    def tail_logs(self, resource: str, lines: int = 50) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            self._require_node(resource)
            logs = [
                f"[tick {self.tick}] {resource}: heartbeat ok",
                f"[tick {self.tick}] {resource}: emitted {lines} sampled log lines",
            ]
            if resource == "raw.orders_api" and self._schema_drift_fired:
                rng = random.Random((self.seed * 1009) + self.tick)
                if rng.random() >= 0.3:
                    logs.append(
                        f"[tick {self.t_a}] raw.orders_api: upstream payload changed: "
                        "order_total missing, order_amount present"
                    )
            if resource == "mart.marketing_roi" and self._cost_explosion_fired:
                logs.append(
                    f"[tick {self.t_b}] mart.marketing_roi: partition predicate absent"
                )
            return logs[-lines:], 0.0, 0.0

        return self._tool_result(tool_cost=0.02, latency_ticks=0, action=action)

    def inspect_query_plan(self, job_id: str) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            table = self._table_from_job_id(job_id)
            node = self._require_node(table)
            plan = {
                "job_id": job_id,
                "table": table,
                "partition_filter": (
                    None
                    if node.partition_filter is None
                    else {
                        "column": node.partition_filter.column,
                        "value_expr": node.partition_filter.value_expr,
                    }
                ),
                "estimated_cost": self._node_cost(table),
            }
            return plan, 0.0, 0.0

        return self._tool_result(tool_cost=0.1, latency_ticks=0, action=action)

    def trace_lineage(self, table: str, depth: int = 2) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            self._require_node(table)
            edges = self._lineage_edges(table, depth)
            rng = random.Random((self.seed * 9176) + (self.tick * 37) + len(table))
            observed = [
                edge for edge in edges if rng.random() > 0.2 or edge[1] == table
            ]
            return {"table": table, "observed_edges": observed}, 0.0, 0.0

        return self._tool_result(tool_cost=0.5, latency_ticks=1, action=action)

    def run_data_test(self, table: str) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            self._require_node(table)
            result = {
                "freshness_ok": table not in self._active_sla_tables(),
                "row_count_ok": True,
                "schema_ok": True,
                "sample_correctness": table not in self._active_sla_tables(),
            }
            return result, 0.0, 0.0

        return self._tool_result(tool_cost=0.2, latency_ticks=1, action=action)

    def submit_diagnosis(self, root_cause_node: str, incident_kind: str) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            positive = 0.0
            penalty = 0.0
            correct = self._is_correct_diagnosis(root_cause_node, incident_kind)
            if correct:
                if incident_kind not in self.correct_diagnoses:
                    self.correct_diagnoses.add(incident_kind)
                    trigger = self._trigger_tick(incident_kind)
                    age = self.tick - trigger
                    if age <= 50:
                        positive = 5.0
                    elif age <= 100:
                        positive = 3.0
                content = {"correct": True, "incident_kind": incident_kind}
            else:
                penalty = -2.0
                content = {"correct": False, "incident_kind": incident_kind}
            return content, positive, penalty

        return self._tool_result(tool_cost=0.0, latency_ticks=0, action=action)

    def apply_fix(self, spec: dict[str, Any]) -> ToolResult:
        def action() -> tuple[Any, float, float]:
            if self._is_schema_fix(spec):
                self.pending_fixes.append(
                    PendingFix(
                        incident_kind=SCHEMA_DRIFT,
                        apply_tick=self.tick + 2,
                        resolve_tick=self.tick + 7,
                    )
                )
                return {"accepted": True, "pending": SCHEMA_DRIFT}, 0.0, 0.0
            if self._is_cost_fix(spec):
                self.pending_fixes.append(
                    PendingFix(
                        incident_kind=COST_EXPLOSION,
                        apply_tick=self.tick + 2,
                        resolve_tick=self.tick + 2,
                    )
                )
                return {"accepted": True, "pending": COST_EXPLOSION}, 0.0, 0.0
            return {"accepted": False, "reason": "fix broke a healthy path"}, 0.0, -5.0

        return self._tool_result(tool_cost=1.0, latency_ticks=2, action=action)

    def wait(self, ticks: int) -> ToolResult:
        bounded_ticks = max(0, min(ticks, self.max_ticks - self.tick))
        return self._tool_result(
            tool_cost=0.0,
            latency_ticks=bounded_ticks,
            action=lambda: ({"waited": bounded_ticks}, 0.0, 0.0),
        )

    def _tool_result(
        self,
        *,
        tool_cost: float,
        latency_ticks: int,
        action: Callable[[], tuple[Any, float, float]],
    ) -> ToolResult:
        old_tick = self.tick
        self.tool_calls += 1
        content, positive_event, penalty_event = action()
        stability_delta, timed_positive, timed_penalty = self._advance(latency_ticks)
        reward = (
            (positive_event + timed_positive) * _decay(self.tick)
            + penalty_event
            + timed_penalty
            + stability_delta
            - (0.05 * tool_cost)
        )
        reward += self._terminal_penalty()
        self.score_total += reward
        if self.tick == old_tick:
            self._apply_drifts_for_tick()
        return ToolResult(
            content=content,
            reward=reward,
            finished=self.is_terminal(),
            tick=self.tick,
            alerts=tuple(self.current_alerts()),
        )

    def _advance(self, ticks: int) -> tuple[float, float, float]:
        stability_delta = 0.0
        positive_event = 0.0
        penalty_event = 0.0
        for _ in range(ticks):
            if self.is_terminal():
                break
            self.tick += 1
            self._apply_drifts_for_tick()
            positive_event += self._apply_pending_fixes_for_tick()
            current_cost = sum(self._node_cost(node_id) for node_id in self.nodes)
            self.cost_accumulated += current_cost
            stability_delta += self._stability_reward(current_cost) * _ramp(self.tick)
        return stability_delta, positive_event, penalty_event

    def _apply_drifts_for_tick(self) -> None:
        if self.tick == self.t_a and not self._schema_drift_fired:
            self.nodes["raw.orders_api"].rename_field("order_total", "order_amount")
            self.drift_history.append(
                {
                    "tick": self.tick,
                    "kind": SCHEMA_DRIFT,
                    "node": "raw.orders_api",
                    "old_field": "order_total",
                    "new_field": "order_amount",
                }
            )
        if self.tick == self.t_b and not self._cost_explosion_fired:
            self.nodes["mart.marketing_roi"].partition_filter = None
            self.drift_history.append(
                {
                    "tick": self.tick,
                    "kind": COST_EXPLOSION,
                    "node": "mart.marketing_roi",
                }
            )

    def _apply_pending_fixes_for_tick(self) -> float:
        reward = 0.0
        remaining: list[PendingFix] = []
        for fix in self.pending_fixes:
            if fix.incident_kind == SCHEMA_DRIFT and self.tick >= fix.apply_tick:
                self.nodes["stg.orders"].transform_mappings["order_total_usd"] = (
                    "raw.orders_api",
                    "order_amount",
                )
            if fix.incident_kind == COST_EXPLOSION and self.tick >= fix.apply_tick:
                self.nodes["mart.marketing_roi"].partition_filter = PartitionSpec(
                    "ingest_date",
                    "CURRENT_DATE() - 1",
                )
            if self.tick >= fix.resolve_tick:
                if fix.incident_kind not in self.resolved_incidents:
                    self.resolved_incidents.add(fix.incident_kind)
                    reward += 8.0
            else:
                remaining.append(fix)
        self.pending_fixes = remaining
        return reward

    def _stability_reward(self, current_cost: float) -> float:
        active_sla_count = len(self._active_sla_tables())
        cost_overrun = 1 if current_cost > self.budget_rate else 0
        healthy_leaf_count = sum(
            1
            for node_id, node in self.nodes.items()
            if node.kind == "leaf" and node_id not in self._active_sla_tables()
        )
        return (
            (-1.0 * active_sla_count)
            + (-0.5 * cost_overrun)
            + (0.02 * healthy_leaf_count)
        )

    def current_alerts(self) -> list[str]:
        alerts: list[str] = []
        if "dash.revenue_health" in self._active_sla_tables():
            alerts.append(
                f"[tick {self.tick}] correctness_violation: dash.revenue_health "
                "total_revenue_usd null rate above 1%"
            )
        if "dash.marketing_health" in self._active_sla_tables():
            alerts.append(
                f"[tick {self.tick}] freshness_violation: dash.marketing_health"
            )
        if (
            COST_EXPLOSION not in self.resolved_incidents
            and self.tick > 0
            and self.cost_accumulated > 1.5 * self.budget_rate * self.tick
        ):
            alerts.append(
                f"[tick {self.tick}] budget_violation: cumulative BigQuery cost "
                f"{self.cost_accumulated:.2f} exceeds threshold"
            )
        return alerts

    def is_terminal(self) -> bool:
        return (
            self.tick >= self.max_ticks
            or self.tool_calls >= self.max_tool_calls
            or self.cost_accumulated > 5 * self.budget_rate * self.max_ticks
            or self._fatal_sla_violation()
        )

    def _terminal_penalty(self) -> float:
        if self.terminal_penalty_paid:
            return 0.0
        penalty = 0.0
        if self.cost_accumulated > 5 * self.budget_rate * self.max_ticks:
            penalty = -50.0
        elif self._fatal_sla_violation():
            penalty = -50.0
        elif self.tool_calls >= self.max_tool_calls and (
            self.tick < self.max_ticks or not self._all_incidents_resolved()
        ):
            penalty = -25.0
        if penalty:
            self.terminal_penalty_paid = True
        return penalty

    def _fatal_sla_violation(self) -> bool:
        if not self._schema_violation_active:
            return False
        return self.tick - (self.t_a + 20) > 100

    def _active_sla_tables(self) -> set[str]:
        active: set[str] = set()
        if self._schema_violation_active:
            active.add("dash.revenue_health")
        return active

    def _sample_row(self, table: str, index: int) -> dict[str, Any]:
        if table == "raw.orders_api":
            amount_field = "order_amount" if self._schema_drift_fired else "order_total"
            return {
                "order_id": f"ord_{self.tick}_{index}",
                "customer_id": f"cust_{index}",
                amount_field: 100.0 + index,
                "currency": "USD",
                "order_ts": f"tick_{self.tick}",
                "ingest_date": "CURRENT_DATE()",
            }
        if table == "stg.orders":
            return {
                "order_id": f"ord_{self.tick}_{index}",
                "customer_id": f"cust_{index}",
                "order_total_usd": None if self._schema_violation_active else 100.0 + index,
                "order_date": "CURRENT_DATE()",
                "ingest_date": "CURRENT_DATE()",
            }
        return {field: self._fake_value(field_type, index) for field, field_type in self.nodes[table].schema.items()}

    def _lineage_edges(self, table: str, depth: int) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []
        frontier = [(table, 0)]
        seen = {table}
        while frontier:
            node_id, node_depth = frontier.pop(0)
            if node_depth >= depth:
                continue
            node = self.nodes[node_id]
            for upstream in node.upstream:
                edges.append((upstream, node_id))
                if upstream not in seen:
                    seen.add(upstream)
                    frontier.append((upstream, node_depth + 1))
        return edges

    def _query_text(self, table: str, *, truncated: bool) -> str:
        if table == "mart.marketing_roi":
            predicate = (
                ""
                if self.nodes[table].partition_filter is None
                else "WHERE ingest_date = CURRENT_DATE() - 1"
            )
            query = f"SELECT spend_date, total_spend, attributed_revenue, roi FROM stg.orders JOIN raw.ad_spend {predicate}"
        else:
            query = f"SELECT * FROM {table}"
        return query[:80] + "..." if truncated and len(query) > 80 else query

    def _node_cost(self, node_id: str) -> float:
        node = self.nodes[node_id]
        if node_id == "mart.marketing_roi" and node.partition_filter is None:
            return node.baseline_cost * 50
        return node.baseline_cost

    def _is_correct_diagnosis(self, root_cause_node: str, incident_kind: str) -> bool:
        if incident_kind == SCHEMA_DRIFT:
            return self._schema_drift_fired and root_cause_node == "raw.orders_api"
        if incident_kind == COST_EXPLOSION:
            return self._cost_explosion_fired and root_cause_node == "mart.marketing_roi"
        return False

    def _is_schema_fix(self, spec: dict[str, Any]) -> bool:
        return (
            self._schema_drift_fired
            and spec.get("type") == "rename_mapping"
            and spec.get("node") == "stg.orders"
            and spec.get("old_field") == "order_total"
            and spec.get("new_field") == "order_amount"
        )

    def _is_cost_fix(self, spec: dict[str, Any]) -> bool:
        return (
            self._cost_explosion_fired
            and spec.get("type") == "add_partition_filter"
            and spec.get("node") == "mart.marketing_roi"
            and spec.get("column") == "ingest_date"
        )

    def _trigger_tick(self, incident_kind: str) -> int:
        if incident_kind == SCHEMA_DRIFT:
            return self.t_a
        if incident_kind == COST_EXPLOSION:
            return self.t_b
        raise ValueError(f"unknown incident kind: {incident_kind}")

    def _table_from_job_id(self, job_id: str) -> str:
        if job_id.startswith("job_"):
            rest = job_id.removeprefix("job_")
            for node_id in self.nodes:
                if rest.startswith(node_id):
                    return node_id
        if job_id in self.nodes:
            return job_id
        raise KeyError(f"unknown job id: {job_id}")

    def _require_node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"unknown node: {node_id}") from exc

    def _fake_value(self, field_type: str, index: int) -> Any:
        if field_type == "FLOAT":
            return float(index)
        if field_type == "INTEGER":
            return index
        if field_type == "DATE":
            return "CURRENT_DATE()"
        if field_type == "TIMESTAMP":
            return f"tick_{self.tick}"
        return f"value_{index}"

    def _all_incidents_resolved(self) -> bool:
        return {SCHEMA_DRIFT, COST_EXPLOSION}.issubset(self.resolved_incidents)

    @property
    def _schema_drift_fired(self) -> bool:
        return any(event["kind"] == SCHEMA_DRIFT for event in self.drift_history)

    @property
    def _cost_explosion_fired(self) -> bool:
        return any(event["kind"] == COST_EXPLOSION for event in self.drift_history)

    @property
    def _schema_violation_active(self) -> bool:
        return (
            self._schema_drift_fired
            and SCHEMA_DRIFT not in self.resolved_incidents
            and self.tick >= self.t_a + 20
        )
