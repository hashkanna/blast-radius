from blast_radius.rollouts import compare_policies, run_competent_rollout, run_naive_baseline
from blast_radius.trace_analysis import analyze_trace_artifact


def test_analyzes_competent_event_trace() -> None:
    report = analyze_trace_artifact(run_competent_rollout(seed=0))

    assert report["kind"] == "event_trace"
    assert report["missing_incidents"] == []
    assert report["first_failure"] is None
    assert report["schema_alert_seen"] is True
    assert report["budget_alert_seen"] is True


def test_analyzes_naive_event_trace_failure() -> None:
    report = analyze_trace_artifact(run_naive_baseline(seed=0))

    assert report["missing_incidents"] == ["cost_explosion", "schema_drift"]
    assert report["wrong_diagnosis_count"] == 2
    assert report["bad_fix_count"] == 2
    assert "wrong diagnosis" in report["first_failure"]
    assert report["recommendations"]


def test_analyzes_comparison_artifact() -> None:
    report = analyze_trace_artifact(compare_policies(seed=0))

    assert report["kind"] == "comparison"
    assert report["policies"]["competent"]["missing_incidents"] == []
    assert report["policies"]["naive_baseline"]["bad_fix_count"] == 2


def test_analyzes_openai_trace_shape() -> None:
    trace = {
        "model": "test-model",
        "steps": [
            {
                "tool_results": [
                    {
                        "name": "submit_diagnosis",
                        "reward": -2.0,
                        "finished": False,
                        "output": '{"tick": 80, "alerts": [], "result": {"correct": false, "incident_kind": "schema_drift"}}',
                    }
                ]
            }
        ],
        "summary": {"finished": False, "tool_calls": 1, "score_total": -2.0, "turns": 1},
    }

    report = analyze_trace_artifact(trace)

    assert report["kind"] == "openai_trace"
    assert report["first_failure"] == "wrong diagnosis: schema_drift"
    assert "schema_drift" in report["missing_incidents"]
