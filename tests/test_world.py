from blast_radius.world import COST_EXPLOSION, SCHEMA_DRIFT, BlastRadiusWorld


def test_canonical_graph_is_fixed_eight_node_dag() -> None:
    world = BlastRadiusWorld.from_seed(7)

    assert len(world.nodes) == 8
    assert world.nodes["raw.orders_api"].schema["order_total"] == "FLOAT"
    assert world.nodes["stg.orders"].upstream == ("raw.orders_api", "raw.fx_rates")
    assert world.nodes["mart.marketing_roi"].partition_filter is not None
    assert world.budget_rate == 2.0


def test_zero_latency_tool_emits_delta_without_stability_reward() -> None:
    world = BlastRadiusWorld.from_seed(1)

    result = world.list_tables()

    assert result.tick == 0
    assert result.reward == -0.0005
    assert world.score_total == -0.0005


def test_schema_incident_can_be_diagnosed_and_fixed() -> None:
    world = BlastRadiusWorld.from_seed(2)
    world.wait(world.t_a + 20)

    assert "order_amount" in world.inspect_schema("raw.orders_api").content
    assert any("dash.revenue_health" in alert for alert in world.current_alerts())

    diagnosis = world.submit_diagnosis("raw.orders_api", SCHEMA_DRIFT)
    assert diagnosis.content["correct"] is True
    assert diagnosis.reward > 0

    world.apply_fix(
        {
            "type": "rename_mapping",
            "node": "stg.orders",
            "old_field": "order_total",
            "new_field": "order_amount",
        }
    )
    fix_wait = world.wait(5)

    assert SCHEMA_DRIFT in world.resolved_incidents
    assert not any("dash.revenue_health" in alert for alert in fix_wait.alerts)


def test_cost_incident_alerts_and_fix_restores_partition_filter() -> None:
    world = BlastRadiusWorld.from_seed(3)
    world.wait(world.t_a + 20)
    world.apply_fix(
        {
            "type": "rename_mapping",
            "node": "stg.orders",
            "old_field": "order_total",
            "new_field": "order_amount",
        }
    )
    world.wait(5)
    world.wait(world.t_b + 8 - world.tick)

    assert any("budget_violation" in alert for alert in world.current_alerts())
    assert world.nodes["mart.marketing_roi"].partition_filter is None

    diagnosis = world.submit_diagnosis("mart.marketing_roi", COST_EXPLOSION)
    assert diagnosis.content["correct"] is True

    fix = world.apply_fix(
        {
            "type": "add_partition_filter",
            "node": "mart.marketing_roi",
            "column": "ingest_date",
            "value_expr": "CURRENT_DATE() - 1",
        }
    )

    assert COST_EXPLOSION in world.resolved_incidents
    assert world.nodes["mart.marketing_roi"].partition_filter is not None
    assert not any("budget_violation" in alert for alert in fix.alerts)
    assert fix.reward > 0


def test_wrong_diagnosis_penalty_is_not_decayed() -> None:
    world = BlastRadiusWorld.from_seed(4)
    world.wait(world.t_a + 120)

    result = world.submit_diagnosis("raw.fx_rates", SCHEMA_DRIFT)

    assert result.reward == -2.0


def test_zero_latency_loop_hits_guardrail_penalty() -> None:
    world = BlastRadiusWorld.from_seed(5)
    world.max_tool_calls = 3

    world.list_tables()
    world.list_tables()
    result = world.list_tables()

    assert result.finished is True
    assert result.reward < -20
    assert world.score_total < -20


def test_waiting_while_broken_loses_reward() -> None:
    world = BlastRadiusWorld.from_seed(6)
    world.wait(world.t_a + 20)

    result = world.wait(10)

    assert any("dash.revenue_health" in alert for alert in result.alerts)
    assert result.reward < 0


def test_wrong_fix_scores_worse_than_honest_fix() -> None:
    wrong = BlastRadiusWorld.from_seed(8)
    honest = BlastRadiusWorld.from_seed(8)
    wrong.wait(wrong.t_a + 20)
    honest.wait(honest.t_a + 20)

    wrong_fix = wrong.apply_fix(
        {
            "type": "backfill",
            "node": "dash.revenue_health",
            "from_tick": wrong.tick - 10,
            "to_tick": wrong.tick,
        }
    )
    honest.apply_fix(
        {
            "type": "rename_mapping",
            "node": "stg.orders",
            "old_field": "order_total",
            "new_field": "order_amount",
        }
    )
    honest_fix_resolution = honest.wait(5)

    assert wrong_fix.reward < 0
    assert honest_fix_resolution.reward > wrong_fix.reward
    assert SCHEMA_DRIFT in honest.resolved_incidents
    assert SCHEMA_DRIFT not in wrong.resolved_incidents


def test_cost_alert_appears_after_cost_incident() -> None:
    world = BlastRadiusWorld.from_seed(9)
    world.wait(world.t_a + 20)
    world.apply_fix(
        {
            "type": "rename_mapping",
            "node": "stg.orders",
            "old_field": "order_total",
            "new_field": "order_amount",
        }
    )
    world.wait(5)
    before = world.wait(max(0, world.t_b - world.tick - 1))
    after = world.wait(20)

    assert not any("budget_violation" in alert for alert in before.alerts)
    assert any("budget_violation" in alert for alert in after.alerts)
