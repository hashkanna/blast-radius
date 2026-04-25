from __future__ import annotations

from typing import Any

from blast_radius.models import ToolResult
from blast_radius.world import COST_EXPLOSION, SCHEMA_DRIFT, BlastRadiusWorld


Trace = list[dict[str, Any]]


def record_tool(trace: Trace, name: str, result: ToolResult) -> None:
    trace.append(
        {
            "type": "tool",
            "tool": name,
            "tick": result.tick,
            "reward": result.reward,
            "finished": result.finished,
            "alerts": list(result.alerts),
            "content": result.content,
        }
    )


def summarize_world(world: BlastRadiusWorld, policy: str) -> dict[str, Any]:
    return {
        "type": "summary",
        "policy": policy,
        "score_total": world.score_total,
        "tool_calls": world.tool_calls,
        "resolved_incidents": sorted(world.resolved_incidents),
        "final_tick": world.tick,
        "finished": world.is_terminal(),
    }


def _start_event(world: BlastRadiusWorld, policy: str) -> dict[str, Any]:
    return {
        "type": "start",
        "policy": policy,
        "seed": world.seed,
        "t_a": world.t_a,
        "t_b": world.t_b,
        "max_ticks": world.max_ticks,
    }


def run_competent_rollout(seed: int) -> Trace:
    world = BlastRadiusWorld.from_seed(seed)
    trace: Trace = [_start_event(world, "competent")]

    record_tool(trace, "list_tables", world.list_tables())
    record_tool(trace, "wait_to_schema_symptom", world.wait(world.t_a + 20 - world.tick))
    record_tool(trace, "trace_lineage(revenue)", world.trace_lineage("dash.revenue_health", depth=3))
    record_tool(trace, "inspect_schema(raw.orders_api)", world.inspect_schema("raw.orders_api"))
    record_tool(trace, "tail_logs(raw.orders_api)", world.tail_logs("raw.orders_api"))
    record_tool(trace, "submit_diagnosis(schema)", world.submit_diagnosis("raw.orders_api", SCHEMA_DRIFT))
    record_tool(
        trace,
        "apply_fix(schema)",
        world.apply_fix(
            {
                "type": "rename_mapping",
                "node": "stg.orders",
                "old_field": "order_total",
                "new_field": "order_amount",
            }
        ),
    )
    record_tool(trace, "wait_for_schema_clear", world.wait(5))
    record_tool(trace, "run_data_test(revenue)", world.run_data_test("dash.revenue_health"))

    record_tool(trace, "wait_to_cost_symptom", world.wait(world.t_b + 15 - world.tick))
    jobs = world.get_job_history("mart.marketing_roi")
    record_tool(trace, "get_job_history(marketing_roi)", jobs)
    job_id = jobs.content[0]["job_id"]
    record_tool(trace, "inspect_query_plan(marketing_roi)", world.inspect_query_plan(job_id))
    record_tool(
        trace,
        "submit_diagnosis(cost)",
        world.submit_diagnosis("mart.marketing_roi", COST_EXPLOSION),
    )
    record_tool(
        trace,
        "apply_fix(cost)",
        world.apply_fix(
            {
                "type": "add_partition_filter",
                "node": "mart.marketing_roi",
                "column": "ingest_date",
                "value_expr": "CURRENT_DATE() - 1",
            }
        ),
    )
    record_tool(trace, "wait_to_end", world.wait(world.max_ticks - world.tick))
    trace.append(summarize_world(world, "competent"))
    return trace


def run_naive_baseline(seed: int) -> Trace:
    world = BlastRadiusWorld.from_seed(seed)
    trace: Trace = [_start_event(world, "naive_baseline")]

    record_tool(trace, "list_tables", world.list_tables())
    record_tool(trace, "wait_to_first_alert", world.wait(world.t_a + 20 - world.tick))
    record_tool(trace, "run_data_test(revenue)", world.run_data_test("dash.revenue_health"))
    record_tool(
        trace,
        "submit_diagnosis(leaf)",
        world.submit_diagnosis("dash.revenue_health", SCHEMA_DRIFT),
    )
    record_tool(
        trace,
        "apply_fix(backfill_leaf)",
        world.apply_fix(
            {
                "type": "backfill",
                "node": "dash.revenue_health",
                "from_tick": max(0, world.tick - 24),
                "to_tick": world.tick,
            }
        ),
    )
    record_tool(trace, "wait_for_symptom_to_return", world.wait(20))
    record_tool(trace, "trace_lineage(shallow)", world.trace_lineage("dash.revenue_health", depth=1))
    record_tool(
        trace,
        "submit_diagnosis(downstream_transform)",
        world.submit_diagnosis("mart.daily_revenue", SCHEMA_DRIFT),
    )
    record_tool(
        trace,
        "apply_fix(rollback_downstream)",
        world.apply_fix(
            {
                "type": "rollback_schema",
                "node": "mart.daily_revenue",
                "to_version": "previous",
            }
        ),
    )
    record_tool(trace, "wait_until_terminal", world.wait(world.max_ticks - world.tick))
    trace.append(summarize_world(world, "naive_baseline"))
    return trace


def summary_from_trace(trace: Trace) -> dict[str, Any]:
    for event in reversed(trace):
        if event.get("type") == "summary":
            return event
    raise ValueError("trace has no summary event")


def compare_policies(seed: int) -> dict[str, Any]:
    baseline = run_naive_baseline(seed)
    competent = run_competent_rollout(seed)
    baseline_summary = summary_from_trace(baseline)
    competent_summary = summary_from_trace(competent)
    return {
        "seed": seed,
        "summary": {
            "naive_baseline": baseline_summary,
            "competent": competent_summary,
            "score_delta": competent_summary["score_total"] - baseline_summary["score_total"],
        },
        "traces": {
            "naive_baseline": baseline,
            "competent": competent,
        },
    }
