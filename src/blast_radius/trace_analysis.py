from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from blast_radius.world import COST_EXPLOSION, SCHEMA_DRIFT


EXPECTED_INCIDENTS = {COST_EXPLOSION, SCHEMA_DRIFT}


def load_trace(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def analyze_trace_artifact(artifact: Any) -> dict[str, Any]:
    if isinstance(artifact, list):
        return _analyze_event_trace(artifact)
    if isinstance(artifact, dict) and "steps" in artifact:
        return _analyze_openai_trace(artifact)
    if isinstance(artifact, dict) and "trace" in artifact:
        return _analyze_ors_scripted_trace(artifact["trace"])
    if isinstance(artifact, dict) and "traces" in artifact:
        return {
            "kind": "comparison",
            "policies": {
                name: _analyze_event_trace(trace)
                for name, trace in artifact["traces"].items()
            },
            "summary": artifact.get("summary", {}),
        }
    raise ValueError("unsupported trace artifact shape")


def analyze_trace_file(path: str | Path) -> dict[str, Any]:
    return analyze_trace_artifact(load_trace(path))


def _analyze_event_trace(trace: list[dict[str, Any]]) -> dict[str, Any]:
    tool_events = [event for event in trace if event.get("type") == "tool"]
    summary = _last_event(trace, "summary") or {}
    diagnosis_events = [event for event in tool_events if event["tool"].startswith("submit_diagnosis")]
    fix_events = [event for event in tool_events if event["tool"].startswith("apply_fix")]
    alerts = [alert for event in tool_events for alert in event.get("alerts", [])]
    resolved = set(summary.get("resolved_incidents", []))
    bad_fixes = [
        event
        for event in fix_events
        if isinstance(event.get("content"), dict) and event["content"].get("accepted") is False
    ]
    wrong_diagnoses = [
        event
        for event in diagnosis_events
        if isinstance(event.get("content"), dict) and event["content"].get("correct") is False
    ]

    return {
        "kind": "event_trace",
        "policy": summary.get("policy") or _first_event(trace, "start", {}).get("policy"),
        "score_total": summary.get("score_total", _sum_rewards(tool_events)),
        "tool_calls": summary.get("tool_calls", len(tool_events)),
        "final_tick": summary.get("final_tick", _last_tick(tool_events)),
        "finished": summary.get("finished", bool(tool_events and tool_events[-1].get("finished"))),
        "resolved_incidents": sorted(resolved),
        "missing_incidents": sorted(EXPECTED_INCIDENTS - resolved),
        "wrong_diagnosis_count": len(wrong_diagnoses),
        "bad_fix_count": len(bad_fixes),
        "budget_alert_seen": any("budget_violation" in alert for alert in alerts),
        "schema_alert_seen": any("dash.revenue_health" in alert for alert in alerts),
        "first_failure": _first_failure(tool_events, wrong_diagnoses, bad_fixes, resolved),
        "recommendations": _recommendations(
            finished=summary.get("finished", bool(tool_events and tool_events[-1].get("finished"))),
            missing=EXPECTED_INCIDENTS - resolved,
            wrong_diagnoses=wrong_diagnoses,
            bad_fixes=bad_fixes,
            budget_alert_seen=any("budget_violation" in alert for alert in alerts),
            tool_calls=summary.get("tool_calls", len(tool_events)),
        ),
    }


def _analyze_ors_scripted_trace(trace: list[dict[str, Any]]) -> dict[str, Any]:
    tool_events = [event for event in trace if "tool" in event]
    summary = _last_event(trace, "summary") or {}
    alerts = [
        alert
        for event in tool_events
        for alert in event.get("content", {}).get("alerts", [])
    ]
    accepted_fixes = [
        event
        for event in tool_events
        if event["tool"] == "apply_fix"
        and event.get("content", {}).get("result", {}).get("accepted") is True
    ]

    return {
        "kind": "ors_scripted_trace",
        "score_total": summary.get("score_total", _sum_rewards(tool_events)),
        "tool_calls": summary.get("tool_calls", len(tool_events)),
        "final_tick": summary.get("final_tick", _last_nested_tick(tool_events)),
        "finished": summary.get("finished", bool(tool_events and tool_events[-1].get("finished"))),
        "accepted_fix_count": len(accepted_fixes),
        "budget_alert_seen": any("budget_violation" in alert for alert in alerts),
        "schema_alert_seen": any("dash.revenue_health" in alert for alert in alerts),
    }


def _analyze_openai_trace(trace: dict[str, Any]) -> dict[str, Any]:
    tool_results = [
        result
        for step in trace.get("steps", [])
        for result in step.get("tool_results", [])
    ]
    summary = trace.get("summary", {})
    tool_names = [result.get("name", "") for result in tool_results]
    parsed_outputs = [_parse_tool_output(result.get("output", "")) for result in tool_results]
    alerts = [
        alert
        for output in parsed_outputs
        for alert in output.get("alerts", [])
    ]
    diagnoses = [
        output.get("result", {})
        for name, output in zip(tool_names, parsed_outputs, strict=False)
        if name == "submit_diagnosis"
    ]
    fixes = [
        output.get("result", {})
        for name, output in zip(tool_names, parsed_outputs, strict=False)
        if name == "apply_fix"
    ]
    correct_kinds = {
        diagnosis.get("incident_kind")
        for diagnosis in diagnoses
        if diagnosis.get("correct") is True
    }
    accepted_fix_count = sum(1 for fix in fixes if fix.get("accepted") is True)
    wrong_diagnosis_count = sum(1 for diagnosis in diagnoses if diagnosis.get("correct") is False)
    bad_fix_count = sum(1 for fix in fixes if fix.get("accepted") is False)
    finished = bool(summary.get("finished"))
    missing = EXPECTED_INCIDENTS - correct_kinds

    return {
        "kind": "openai_trace",
        "model": trace.get("model"),
        "score_total": summary.get("score_total", _sum_rewards(tool_results)),
        "tool_calls": summary.get("tool_calls", len(tool_results)),
        "turns": summary.get("turns", len(trace.get("steps", []))),
        "finished": finished,
        "called_tools": tool_names,
        "unique_tools": sorted(set(tool_names)),
        "diagnosed_incidents": sorted(correct_kinds),
        "missing_incidents": sorted(missing),
        "accepted_fix_count": accepted_fix_count,
        "wrong_diagnosis_count": wrong_diagnosis_count,
        "bad_fix_count": bad_fix_count,
        "budget_alert_seen": any("budget_violation" in alert for alert in alerts),
        "schema_alert_seen": any("dash.revenue_health" in alert for alert in alerts),
        "first_failure": _openai_first_failure(
            tool_names=tool_names,
            diagnoses=diagnoses,
            fixes=fixes,
            finished=finished,
            missing=missing,
        ),
        "recommendations": _recommendations(
            finished=finished,
            missing=missing,
            wrong_diagnoses=[diagnosis for diagnosis in diagnoses if diagnosis.get("correct") is False],
            bad_fixes=[fix for fix in fixes if fix.get("accepted") is False],
            budget_alert_seen=any("budget_violation" in alert for alert in alerts),
            tool_calls=summary.get("tool_calls", len(tool_results)),
        ),
    }


def _parse_tool_output(output: str) -> dict[str, Any]:
    try:
        parsed = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return {"raw_output": output}
    return parsed if isinstance(parsed, dict) else {"result": parsed}


def _first_failure(
    tool_events: list[dict[str, Any]],
    wrong_diagnoses: list[dict[str, Any]],
    bad_fixes: list[dict[str, Any]],
    resolved: set[str],
) -> str | None:
    if wrong_diagnoses:
        return f"wrong diagnosis at tick {wrong_diagnoses[0].get('tick')}"
    if bad_fixes:
        return f"bad fix at tick {bad_fixes[0].get('tick')}"
    missing = EXPECTED_INCIDENTS - resolved
    if missing:
        return f"missing incidents: {', '.join(sorted(missing))}"
    if tool_events and not tool_events[-1].get("finished"):
        return "trace stopped before environment finished"
    return None


def _openai_first_failure(
    *,
    tool_names: list[str],
    diagnoses: list[dict[str, Any]],
    fixes: list[dict[str, Any]],
    finished: bool,
    missing: set[str],
) -> str | None:
    if not tool_names:
        return "model made no tool calls"
    for diagnosis in diagnoses:
        if diagnosis.get("correct") is False:
            return f"wrong diagnosis: {diagnosis.get('incident_kind')}"
    for fix in fixes:
        if fix.get("accepted") is False:
            return "bad fix"
    if missing:
        return f"missing incidents: {', '.join(sorted(missing))}"
    if not finished:
        return "model stopped before environment finished"
    return None


def _recommendations(
    *,
    finished: bool,
    missing: set[str],
    wrong_diagnoses: list[Any],
    bad_fixes: list[Any],
    budget_alert_seen: bool,
    tool_calls: int,
) -> list[str]:
    recommendations: list[str] = []
    if wrong_diagnoses:
        recommendations.append("Improve prompt/tool descriptions around root cause vs symptom.")
    if bad_fixes:
        recommendations.append("Emphasize that fixes should target upstream transforms, not leaves.")
    if COST_EXPLOSION in missing and not budget_alert_seen:
        recommendations.append("Ensure the agent waits/monitors long enough for the cost incident.")
    if missing:
        recommendations.append(f"Missing incident coverage: {', '.join(sorted(missing))}.")
    if not finished:
        recommendations.append("Increase max_turns or investigate why the model stopped early.")
    if tool_calls >= 180:
        recommendations.append("Tool usage is near max_tool_calls; check for loops or low-value inspection.")
    return recommendations


def _first_event(trace: list[dict[str, Any]], event_type: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    for event in trace:
        if event.get("type") == event_type or event.get("event") == event_type:
            return event
    return default or {}


def _last_event(trace: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    for event in reversed(trace):
        if event.get("type") == event_type or event.get("event") == event_type:
            return event
    return None


def _last_tick(tool_events: list[dict[str, Any]]) -> int | None:
    if not tool_events:
        return None
    return tool_events[-1].get("tick")


def _last_nested_tick(tool_events: list[dict[str, Any]]) -> int | None:
    if not tool_events:
        return None
    return tool_events[-1].get("content", {}).get("tick")


def _sum_rewards(events: list[dict[str, Any]]) -> float:
    return sum(float(event.get("reward", 0.0)) for event in events)
