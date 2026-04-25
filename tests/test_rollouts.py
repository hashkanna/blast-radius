from blast_radius.rollouts import compare_policies, run_naive_baseline, summary_from_trace


def test_competent_policy_beats_naive_baseline() -> None:
    report = compare_policies(seed=0)
    baseline = report["summary"]["naive_baseline"]
    competent = report["summary"]["competent"]

    assert competent["score_total"] > baseline["score_total"]
    assert report["summary"]["score_delta"] > 50
    assert competent["resolved_incidents"] == ["cost_explosion", "schema_drift"]
    assert baseline["resolved_incidents"] == []


def test_naive_baseline_terminates_from_unfixed_schema_incident() -> None:
    trace = run_naive_baseline(seed=0)
    summary = summary_from_trace(trace)
    bad_fix_events = [
        event
        for event in trace
        if event.get("tool") in {"apply_fix(backfill_leaf)", "apply_fix(rollback_downstream)"}
    ]

    assert summary["finished"] is True
    assert summary["final_tick"] < 250
    assert summary["score_total"] < -50
    assert len(bad_fix_events) == 2
    assert all(event["content"]["accepted"] is False for event in bad_fix_events)
