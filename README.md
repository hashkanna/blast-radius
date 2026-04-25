# BlastRadius

[![OpenReward Environment](https://img.shields.io/badge/OpenReward-Environment-f7e6cc)](https://openreward.ai/)

## Description

BlastRadius is a non-stationary RL environment for diagnosing a simulated data platform whose causal structure is hidden from the agent. The agent sees a GCP-shaped interface with BigQuery schemas, Cloud Logging-style logs, job history, query plans, partial lineage, alerts, and a cost meter; underneath is a deterministic abstract DAG. The environment evaluates whether an agent can infer hidden lineage, distinguish symptoms from root causes, and keep a drifting system healthy over a multi-tool episode.

## Capabilities

- Causal-structure inference under partial observability.
- Long-horizon diagnosis with delayed and ambiguous symptoms.
- Root-cause discrimination: fixing upstream drift rather than downstream alerts.
- Acting under non-stationarity while the system continues to evolve.
- Budget and data-quality tradeoff management with noisy operational tools.

## Compute Requirements

BlastRadius does not require an execution sandbox, GPU, network access, or external services during an episode. It runs as a normal ORS/OpenReward environment server with in-memory Python state.

## License

MIT. See `LICENSE`.

## Tasks

There are 100 deterministic tasks:

- `train`: 80 seeds, `seed_0` through `seed_79`.
- `eval`: 20 held-out seeds, `seed_80` through `seed_99`.

Each task instantiates the same eight-node canonical data-platform DAG with seed-derived incident timing and observation noise. The v1 episode contains two hidden incidents: schema drift in `raw.orders_api` and partition-filter loss in `mart.marketing_roi`.

## Reward Structure

Each tool call emits a reward delta. The simulator combines:

- Sparse milestone rewards for correct diagnosis and verified fixes.
- Dense per-tick stability reward for healthy leaf dashboards.
- Per-tick penalties for active SLA violations and budget overruns.
- Action penalties for tool cost.
- Guardrail penalties for fatal cost/SLA failures or `max_tool_calls`.

Rewards are fully programmatic; there is no LLM grader. Correct behavior requires diagnosing and fixing both incidents, then monitoring until episode termination at tick 250.

## Data

All data is synthetic and generated deterministically from task seeds. No real GCP services, customer data, production logs, or external datasets are used.

## Tools

The agent receives these tools:

- `list_tables`
- `inspect_schema`
- `query_sample`
- `get_job_history`
- `tail_logs`
- `inspect_query_plan`
- `trace_lineage`
- `run_data_test`
- `submit_diagnosis`
- `apply_fix`
- `wait`

Tools have different costs, latencies, and reliability. `trace_lineage` is intentionally partial: it returns recently observed lineage edges, not ground truth.

## Time Horizon

Hackathon v1 targets roughly 40-120 natural tool calls for a serious model run, depending on how much the agent explores and verifies. The scripted competent demonstration path uses 15 tool calls, while the naive baseline terminates early after 10 calls because it repeatedly fixes symptoms rather than root causes.

## Environment Difficulty

Seed 0 scripted calibration:

| Policy | Score | Tool calls | Final tick | Resolved incidents |
|---|---:|---:|---:|---|
| Naive baseline | -164.9057 | 10 | 185 | none |
| Competent path | 5.6135 | 15 | 250 | `schema_drift`, `cost_explosion` |

The checked-in traces are in `artifacts/`.

## Other Environment Requirements

For local development:

```bash
pip install -e ".[dev]"
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Run the ORS server:

```bash
pip install -e ".[ors]"
python3 server.py --port 8080
```

Run deterministic demo traces:

```bash
PYTHONPATH=src python3 scripts/baseline_vs_competent.py --seed 0
PYTHONPATH=src python3 scripts/analyze_trace.py artifacts/baseline_vs_competent_seed0.json
```

Run an OpenAI model against a local server:

```bash
pip install -e ".[agent]"
OPENAI_MODEL=<model> python3 scripts/openai_sample_agent.py \
  --base-url http://localhost:8080 \
  --output artifacts/openai_seed0.json
```

## Safety

The environment is low risk. It exposes only synthetic observations and in-memory simulator actions; no real cloud resources or external systems are modified. The main safety concern is reward misspecification, mitigated with explicit penalties for destructive fixes, zero-latency tool loops, and symptom-only repairs.

## Citations

```bibtex
@misc{blastradius2026,
  author = {Kannappan},
  title = {BlastRadius: Hidden-Lineage Incident Diagnosis for Agentic RL},
  year = {2026},
  publisher = {OpenReward},
  url = {https://openreward.ai/}
}
```
