import json

from blast_radius.ors_env import BlastRadiusEnv, _tasks_for_split


def test_tasks_are_deterministic_for_train_and_eval() -> None:
    train = _tasks_for_split("train")
    eval_tasks = _tasks_for_split("eval")

    assert len(train) == 80
    assert len(eval_tasks) == 20
    assert train[0] == {"id": "seed_0", "seed": 0, "difficulty": "v1"}
    assert eval_tasks[0] == {"id": "seed_80", "seed": 80, "difficulty": "v1"}


def test_env_wraps_world_result_as_text_json() -> None:
    env = BlastRadiusEnv({"id": "seed_0", "seed": 0, "difficulty": "v1"})

    output = env.list_tables()
    payload = json.loads(output.blocks[0].text)

    assert output.reward == -0.0005
    assert output.finished is False
    assert payload["tick"] == 0
    assert "raw.orders_api" in payload["result"]
