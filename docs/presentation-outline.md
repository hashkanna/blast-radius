# BlastRadius Presentation Outline

Target: 2-3 minutes.

## Slide 1: Capability Thesis

**BlastRadius:** a non-stationary RL environment for diagnosing systems whose causal structure you cannot directly observe.

One sentence to say:

> Most agent benchmarks give a static repo and a failing test. BlastRadius gives the agent a running data platform where the graph is hidden, symptoms are delayed, and fixes can make the system worse.

## Slide 2: Environment Shape

Show:

- Eight-node synthetic DAG.
- GCP skin: BigQuery schemas, job history, query plans, Cloud Logging-style logs, dashboards.
- Hidden incidents:
  - `raw.orders_api.order_total` becomes `order_amount`.
  - `mart.marketing_roi` loses its partition filter.

One sentence to say:

> The GCP interface is just a skin; the real environment is an abstract stochastic DAG, which keeps it tractable and deterministic for evaluation.

## Slide 3: Why It Is Hard

Show three bullets:

- Partial observability: `trace_lineage` is useful but incomplete.
- Delayed feedback: source drift appears later as a dashboard SLA violation.
- Wrong fixes are plausible: backfills and leaf fixes look helpful but do not remove the upstream cause.

One sentence to say:

> The capability tangent is causal-structure inference under partial observability and non-stationarity.

## Slide 4: Demo Result

Use `artifacts/demo_summary_seed0.json`.

| Policy | Score | Tool calls | Outcome |
|---|---:|---:|---|
| Naive baseline | -164.9057 | 10 | fixes symptoms, terminates early |
| Competent path | 5.6135 | 15 | diagnoses and fixes both incidents |

One sentence to say:

> The baseline fails exactly the way we want weak agents to fail: it repairs the dashboard instead of the upstream cause, then the cascade returns.

## Slide 5: OpenReward + Roadmap

Show:

- ORS environment server with 80 train / 20 eval seeds.
- Programmatic reward deltas, no LLM grader.
- Tools map cleanly to model function calls.
- Roadmap: larger DAGs, overlapping incidents, adversarial drift.

Close:

> The v1 is intentionally small enough to ship, but the design scales naturally into hundreds-of-tool-call episodes by increasing graph size, incident overlap, and verification windows.

## Live Demo Commands

```bash
PYTHONPATH=src python3 scripts/baseline_vs_competent.py --seed 0
PYTHONPATH=src python3 scripts/analyze_trace.py artifacts/baseline_vs_competent_seed0.json
```

If showing the server:

```bash
pip install -e ".[ors]"
python3 server.py --port 8080
```

In another terminal:

```bash
PYTHONPATH=src python3 scripts/ors_scripted_rollout.py --base-url http://localhost:8080
```
