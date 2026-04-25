from __future__ import annotations

import argparse
import json
from typing import Any

from blast_radius.world import BlastRadiusWorld


def _block_text(tool_output: Any) -> str:
    return "".join(getattr(block, "text", str(block)) for block in tool_output.blocks)


def _record(trace: list[dict[str, Any]], name: str, tool_output: Any) -> None:
    trace.append(
        {
            "tool": name,
            "reward": tool_output.reward,
            "finished": tool_output.finished,
            "content": json.loads(_block_text(tool_output)),
        }
    )


def run_scripted_rollout(
    *,
    base_url: str,
    env_name: str,
    split: str,
    task_index: int,
) -> dict[str, Any]:
    from openreward import OpenReward

    client = OpenReward()
    environment = client.environments.get(name=env_name, base_url=base_url)
    task = environment.list_tasks(split=split)[task_index]
    seed = task.task_spec["seed"]
    schedule = BlastRadiusWorld.from_seed(seed)
    trace: list[dict[str, Any]] = [
        {
            "event": "start",
            "env_name": env_name,
            "split": split,
            "task_index": task_index,
            "task_spec": task.task_spec,
            "t_a": schedule.t_a,
            "t_b": schedule.t_b,
        }
    ]

    with environment.session(task=task) as session:
        prompt = session.get_prompt()
        trace.append({"event": "prompt", "text": prompt[0].text})

        def call(name: str, payload: dict[str, Any]) -> Any:
            output = session.call_tool(name, payload)
            _record(trace, name, output)
            return output

        call("list_tables", {})
        call("wait", {"ticks": schedule.t_a + 20})
        call("trace_lineage", {"table": "dash.revenue_health", "depth": 3})
        call("inspect_schema", {"table": "raw.orders_api"})
        call("tail_logs", {"resource": "raw.orders_api", "lines": 50})
        call(
            "submit_diagnosis",
            {"root_cause_node": "raw.orders_api", "incident_kind": "schema_drift"},
        )
        call(
            "apply_fix",
            {
                "spec": {
                    "type": "rename_mapping",
                    "node": "stg.orders",
                    "old_field": "order_total",
                    "new_field": "order_amount",
                }
            },
        )
        call("wait", {"ticks": 5})
        call("run_data_test", {"table": "dash.revenue_health"})
        current_tick = trace[-1]["content"]["tick"]
        call("wait", {"ticks": max(0, schedule.t_b + 15 - current_tick)})
        jobs = call("get_job_history", {"table": "mart.marketing_roi", "last_n": 20})
        job_id = json.loads(_block_text(jobs))["result"][0]["job_id"]
        call("inspect_query_plan", {"job_id": job_id})
        call(
            "submit_diagnosis",
            {"root_cause_node": "mart.marketing_roi", "incident_kind": "cost_explosion"},
        )
        call(
            "apply_fix",
            {
                "spec": {
                    "type": "add_partition_filter",
                    "node": "mart.marketing_roi",
                    "column": "ingest_date",
                    "value_expr": "CURRENT_DATE() - 1",
                }
            },
        )
        final_tick = trace[-1]["content"]["tick"]
        call("wait", {"ticks": max(0, schedule.max_ticks - final_tick)})

    tool_events = [event for event in trace if "tool" in event]
    trace.append(
        {
            "event": "summary",
            "score_total": sum(event["reward"] for event in tool_events),
            "tool_calls": len(tool_events),
            "finished": tool_events[-1]["finished"],
            "final_tick": tool_events[-1]["content"]["tick"],
        }
    )
    return {"trace": trace}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the competent scripted path through a local ORS server."
    )
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--env-name", default="blastradiusenv")
    parser.add_argument("--split", default="train")
    parser.add_argument("--task-index", type=int, default=0)
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args()

    report = run_scripted_rollout(
        base_url=args.base_url,
        env_name=args.env_name,
        split=args.split,
        task_index=args.task_index,
    )
    print(json.dumps(report, indent=args.indent, sort_keys=True))


if __name__ == "__main__":
    main()
