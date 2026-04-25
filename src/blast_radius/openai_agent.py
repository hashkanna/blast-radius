from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def block_text(tool_output: Any) -> str:
    return "".join(getattr(block, "text", str(block)) for block in tool_output.blocks)


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def output_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            content_text = getattr(content, "text", None)
            if content_text:
                chunks.append(content_text)
    return "\n".join(chunks)


def run_openai_agent(
    *,
    base_url: str,
    env_name: str,
    split: str,
    task_index: int,
    model: str,
    max_turns: int = 80,
) -> dict[str, Any]:
    from openai import OpenAI
    from openreward import OpenReward

    openreward_client = OpenReward()
    openai_client = OpenAI()

    environment = openreward_client.environments.get(name=env_name, base_url=base_url)
    task = environment.list_tasks(split=split)[task_index]
    tools = environment.list_tools(format="openai")

    trace: dict[str, Any] = {
        "environment": {
            "base_url": base_url,
            "env_name": env_name,
            "split": split,
            "task_index": task_index,
            "task_spec": task.task_spec,
        },
        "model": model,
        "steps": [],
        "summary": {},
    }

    with environment.session(task=task) as session:
        prompt = session.get_prompt()
        input_items: list[Any] = [{"role": "user", "content": prompt[0].text}]
        trace["prompt"] = prompt[0].text

        finished = False
        total_reward = 0.0
        tool_calls = 0

        for turn in range(max_turns):
            response = openai_client.responses.create(
                model=model,
                tools=tools,
                input=input_items,
            )
            input_items += list(response.output)

            step: dict[str, Any] = {
                "turn": turn,
                "response_id": response.id,
                "model_output": to_jsonable(response.output),
                "text": output_text(response),
                "tool_results": [],
            }

            function_calls = [
                item
                for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                step["stop_reason"] = "no_function_call"
                trace["steps"].append(step)
                break

            for function_call in function_calls:
                name = function_call.name
                arguments = json.loads(function_call.arguments or "{}")
                tool_result = session.call_tool(name, arguments)
                tool_calls += 1
                total_reward += tool_result.reward
                finished = bool(tool_result.finished)

                tool_output = {
                    "type": "function_call_output",
                    "call_id": function_call.call_id,
                    "output": block_text(tool_result),
                }
                input_items.append(tool_output)

                step["tool_results"].append(
                    {
                        "name": name,
                        "arguments": arguments,
                        "reward": tool_result.reward,
                        "finished": tool_result.finished,
                        "output": block_text(tool_result),
                    }
                )

                if finished:
                    break

            trace["steps"].append(step)
            if finished:
                break

        trace["summary"] = {
            "finished": finished,
            "tool_calls": tool_calls,
            "score_total": total_reward,
            "turns": len(trace["steps"]),
        }
    return trace


def write_trace(trace: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n")
