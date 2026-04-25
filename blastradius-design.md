# BlastRadius — Technical Design

**Pitch:** A non-stationary RL environment for diagnosing systems whose causal structure you cannot directly observe. The agent is dropped into a running data platform, given partial-observability tools, and must reconstruct hidden lineage from delayed and ambiguous symptoms before it can act effectively. Skinned as GCP (BigQuery / Dataflow / Dataform / Cloud Logging) for legibility; the substrate is an abstract stochastic DAG.

**Hackathon:** Complex Worlds (London) — General Reasoning + Entrepreneurs First + Air Street Capital. Built on OpenReward / ORS.

**Author:** Kannappan (solo). v0.1.

---

## 1. Capability thesis

The hosts asked for three things: long horizon, capability tangent, hard-but-tractable. BlastRadius is built around one capability tangent that subsumes the rest: **causal-structure inference under partial observability and non-stationarity.**

Subcapabilities this probes:

- **Lineage reconstruction from partial signals** — the dependency graph is hidden; symptoms surface at leaves; the agent must triangulate upstream causes from logs, schemas, and data samples.
- **Reasoning under delayed feedback** — actions produce consequences many ticks later, after aggregation windows and downstream refreshes. Naive credit assignment fails.
- **Symptom-vs-root-cause discrimination** — a freshness alert on a dashboard is rarely the bug. Agents that fix the symptom are penalized later when the cascade returns.
- **Acting under non-stationarity** — the system keeps drifting while the agent diagnoses. Static snapshots of state become stale within a few ticks.

This is explicitly *not* "SWE-bench for data engineering." SWE-bench is one-shot static debugging. BlastRadius is a continuously evolving world where standing still is itself a choice with consequences.

**Why the horizon grows naturally:** lineage discovery is a sequence of inspect → sample → log → upstream-inspect → hypothesis → test. The hackathon v1 target is a tractable 40–120 tool calls per episode: two incidents, an eight-node graph, noisy lineage, and required post-fix verification. The benchmark trajectory is 200–800 calls by increasing the graph to 20–50 nodes, overlapping 4–6 incidents, and longer verification windows. Do not claim 2000-call episodes until the larger curriculum exists.

---

## 2. Architecture: abstract substrate, GCP skin

The most important design discipline in this project: **the simulator is abstract underneath; GCP is a skin.** This is the single biggest predictor of whether this ships in 48 hours.

### 2.1 Substrate

The world is a directed acyclic graph `G = (V, E)` where each node `v ∈ V` has:

```
Node:
  id: str
  kind: "source" | "transform" | "leaf"
  schema: Schema           # typed fields, mutable
  produces_per_tick: int   # row volume
  cost_per_tick: float     # baseline operational cost
  transform_fn: Optional[TransformSpec]  # references upstream fields
  partition_filter: Optional[PartitionSpec]  # affects cost
  sla: Optional[SLA]       # freshness/correctness/budget bounds
```

Edges represent data flow. Each node's output schema is a function of its inputs and its transform spec. When an upstream schema drifts in a way the transform doesn't handle, the downstream output silently degrades (NULLs, type coercion, dropped rows).

### 2.2 Drift process

At each tick, a stochastic mutation may fire:

- **Schema rename** — `field.name := f(field.name)`. Probability `p_rename` per source node per tick.
- **Partition filter loss** — a transform's `partition_filter` becomes `None`. Probability `p_partloss` per transform per tick.

For v1 these are scheduled (deterministic per seed) rather than truly stochastic — gives reproducibility for evaluation. Stochastic version is stretch.

### 2.3 GCP skin (presentation layer only)

Mappings, applied only at the tool / observation layer:

| Substrate | GCP skin |
|---|---|
| Source node | GCS bucket + Cloud Run ingest |
| Transform node | BigQuery scheduled query / Dataform model |
| Leaf node | "Dashboard" with SLA |
| Schema | BigQuery table schema (JSON) |
| Logs | Cloud Logging entries |
| Cost meter | BigQuery billing |
| Drift event | Underlying API change / config drift |

The agent sees BigQuery-shaped schema JSON, Cloud-Logging-shaped log lines, BigQuery-shaped query history. **None of it talks to real GCP.** It's all string templating over the substrate.

### 2.4 What we are NOT building

Explicitly out of scope, even if tempting:

- A real BigQuery emulator
- Real Dataform / dbt SQL parsing
- Real IAM model
- Real Dataflow execution graph
- Realistic data volumes
- Anything that makes a tool call slower than ~10ms

If during Saturday a design choice pulls toward any of the above, the answer is no.

### 2.5 Canonical v1 graph

The v1 implementation uses one fixed eight-node DAG. Seeds change incident timing, stale-cache behavior, log noise, and partial-lineage omissions; they do not change the node set. This keeps the simulator deterministic enough to finish and test.

| Node id | Kind | Upstream | Schema / output | Baseline cost | SLA / role |
|---|---|---|---|---:|---|
| `raw.orders_api` | source | — | `order_id`, `customer_id`, `order_total`, `currency`, `order_ts`, `ingest_date` | 0.1/tick | Incident A drift source |
| `raw.ad_spend` | source | — | `campaign_id`, `spend`, `spend_date`, `ingest_date` | 0.1/tick | Marketing spend input |
| `raw.fx_rates` | source | — | `currency`, `rate_to_usd`, `effective_date`, `ingest_date` | 0.05/tick | Join input / distractor |
| `stg.orders` | transform | `raw.orders_api`, `raw.fx_rates` | `order_id`, `customer_id`, `order_total_usd`, `order_date`, `ingest_date` | 0.3/tick | Owns the schema-drift fix |
| `mart.daily_revenue` | transform | `stg.orders` | `revenue_date`, `total_revenue_usd`, `order_count` | 0.4/tick | Revenue aggregate |
| `mart.marketing_roi` | transform | `stg.orders`, `raw.ad_spend` | `spend_date`, `total_spend`, `attributed_revenue`, `roi` | 0.5/tick | Incident B partition-filter target |
| `dash.revenue_health` | leaf | `mart.daily_revenue` | Dashboard metrics | 0.05/tick | freshness <30 ticks; `total_revenue_usd` NULL rate <1% |
| `dash.marketing_health` | leaf | `mart.marketing_roi` | Dashboard metrics | 0.05/tick | freshness <30 ticks; ROI present for last window |

Edges:

```
raw.orders_api ─┬─> stg.orders ─┬─> mart.daily_revenue ─> dash.revenue_health
raw.fx_rates ───┘               └─> mart.marketing_roi ─> dash.marketing_health
raw.ad_spend ──────────────────────^
```

Fixed v1 incident targets:

- **Incident A:** at `T_A`, `raw.orders_api.order_total` becomes `order_amount`. `stg.orders` still reads `order_total`, so `order_total_usd` degrades to NULL and `dash.revenue_health` fails after the aggregation delay. Correct fix: `rename_mapping` on `stg.orders` from `order_total` to `order_amount`.
- **Incident B:** at `T_B`, `mart.marketing_roi.partition_filter` is removed. Query output remains correct, but cost increases by ~50x and the budget alert fires. Correct fix: `add_partition_filter` on `mart.marketing_roi` with `ingest_date = CURRENT_DATE() - 1`.

---

## 3. State and observation model

### 3.1 Hidden state (simulator only)

```
WorldState:
  graph: DAG
  tick: int
  tool_calls: int
  pending_drifts: List[ScheduledDrift]
  cost_accumulated: float
  active_violations: List[SLAViolation]  # not directly visible
  drift_history: List[DriftEvent]        # hidden
```

### 3.2 Observation (what the agent gets)

The agent never receives `WorldState`. Each tool call returns a fragment of observation:

- **Alerts** — surfaced as a feed: `"[tick 73] freshness_violation: mart.daily_revenue (expected <30min, observed 95min)"`. Vague by design — they say *what's broken*, not *why*.
- **Cost meter** — running total visible.
- **Tool results** — partial views of the world, with noise (see §4).
- **Tick counter** — agent knows simulated time.

The agent does NOT receive:
- The DAG structure (only inferable through tool use)
- Drift events (only their downstream symptoms)
- Ground-truth lineage between alerts and root causes
- The schedule or rate of future drifts

This partial-observability layer is the heart of the environment. Without it, the problem collapses to a planning toy.

---

## 4. Tool surface

Tools are first-class. Each has cost (sim-budget), latency (advances tick counter), and noise (returns incomplete or stale information). Cost and latency are what force agents to actually plan rather than spam.

### 4.1 Inspection tools

```
list_tables() -> List[str]
  cost: 0.01, latency: 0 ticks, noise: none

inspect_schema(table: str) -> Schema
  cost: 0.05, latency: 0, noise: schema may be cached up to 2 ticks stale

query_sample(table: str, n: int = 10) -> List[Row]
  cost: 0.1 + 0.01*n, latency: 1 tick, noise: random sampling

get_job_history(table: str, last_n: int = 20) -> List[JobRun]
  cost: 0.05, latency: 0, noise: success/fail visible; query SQL truncated

tail_logs(resource: str, lines: int = 50) -> List[LogLine]
  cost: 0.02, latency: 0, noise: ~30% of relevant lines dropped or arrive
                                  late; many irrelevant lines included

inspect_query_plan(job_id: str) -> QueryPlan
  cost: 0.1, latency: 0, noise: clean — but you have to know which job

trace_lineage(table: str, depth: int = 2) -> PartialLineage
  cost: 0.5, latency: 1 tick, noise: returns lineage edges OBSERVED IN
                                      RECENT TRAFFIC ONLY. May miss
                                      edges that haven't fired recently.
                                      Critical: this is not ground truth.
```

`trace_lineage` is the most important tool design choice. It's deliberately *useful but unreliable* — it accelerates the agent but doesn't bypass the capability probe.

### 4.2 Diagnostic tools

```
run_data_test(table: str) -> TestResult
  cost: 0.2, latency: 1 tick
  Returns: {freshness_ok, row_count_ok, schema_ok, sample_correctness}

submit_diagnosis(root_cause_node: str, incident_kind: str)
  cost: 0, latency: 0
  Used for milestone scoring (§5). Can be called multiple times.
  First correct submission per incident scores the milestone.
```

### 4.3 Action tools

```
apply_fix(spec: FixSpec) -> FixResult
  cost: 1.0, latency: 2 ticks
  FixSpec variants:
    - {type: "rename_mapping", node, old_field, new_field}
    - {type: "add_partition_filter", node, column, value_expr}
    - {type: "backfill", node, from_tick, to_tick}
    - {type: "rollback_schema", node, to_version}

wait(ticks: int) -> None
  cost: 0, latency: ticks
  Sometimes the correct action. Verifying a fix requires waiting.
```

### 4.4 Tool surface forces long episodes

A single incident's diagnosis path looks like:

1. `alert observed` (free)
2. `list_tables` → orient
3. `trace_lineage(leaf)` → partial graph
4. `inspect_schema(leaf)` → looks fine
5. `inspect_schema(upstream_1)` → looks fine
6. `query_sample(upstream_1)` → field looks normal
7. `tail_logs(upstream_1)` → maybe relevant line
8. `inspect_schema(upstream_2)` → field renamed!
9. `get_job_history(upstream_2)` → confirm rename happened at tick X
10. `submit_diagnosis(upstream_2, "schema_drift")` → milestone
11. `apply_fix(rename_mapping ...)` → +2 ticks
12. `wait(5)` → let cascade clear
13. `run_data_test(leaf)` → verify

That's ~13 calls for one clean incident. In the eight-node v1, two incidents plus stale schemas, noisy logs, partial lineage, wrong hypotheses, and mandatory post-fix waits should produce roughly 40–120 calls for a serious run. The 200–800-call version is a curriculum extension, not the Saturday dependency: larger graphs, 4–6 incidents, overlapping cascades, and longer verification windows.

---

## 5. Reward function (hybrid)

This is where every previous design round flinched. Locking it now.

### 5.1 Decomposition and emission

ORS tool results must emit **reward deltas**, not cumulative score. The simulator keeps `score_total` internally, but each `ToolOutput.reward` is only the reward produced since the previous tool call.

Per tool call:

```
old_tick = world.tick
world.tool_calls += 1
positive_event_delta, penalty_event_delta = apply_action_and_collect_event_rewards(action)
world.advance(latency_ticks)
stability_delta = sum(
  R_stability(t) * ramp(t)
  for t in range(old_tick + 1, world.tick + 1)
)
action_penalty = -0.05 * tool_cost(action)

reward_delta =
  positive_event_delta * decay(world.tick)
  + penalty_event_delta
  + stability_delta
  + action_penalty
```

Definitions:

- `positive_event_delta`: sparse, large, paid for diagnosis/fix correctness. Front-loaded by `decay`.
- `penalty_event_delta`: sparse negative rewards for wrong diagnoses and harmful fixes. Not decayed; bad actions should not become cheap late in the episode.
- `R_stability`: dense, small, paid per elapsed tick for system health. Back-loaded by `ramp`.
- `decay(t)`: 1.0 for `t < 50`, linear to 0.2 by `t = 150`, then 0.2.
- `ramp(t)`: 0.2 for `t < 50`, linear to 1.0 by `t = 150`, then 1.0.
- `action_penalty`: applied once per tool call, including zero-latency tools. A zero-latency tool does not receive stability reward because no ticks elapsed.

Rationale: early-episode reward incentivizes *finding* the bug; late-episode reward incentivizes *keeping the system stable*. An agent that diagnoses fast but then breaks something else loses points. An agent that maintains stability without ever diagnosing the root cause underperforms an agent that does both.

### 5.2 Milestone components

For each incident `i` in the episode:

```
R_milestone_i =
  + 5.0  if first correct submit_diagnosis(correct_node, correct_kind) within 50 ticks of trigger
  + 3.0  if first correct submit_diagnosis(correct_node, correct_kind) within 100 ticks
  + 0.0  thereafter
  + 8.0  if applied fix resolves incident (paid once when simulator observes resolution)
  - 2.0  per incorrect submit_diagnosis
  - 5.0  per applied fix that breaks a previously healthy node
```

The fix-resolution reward may be emitted by a later `wait` or `run_data_test` call if the downstream cascade needs time to clear.

### 5.3 Stability components (per-tick)

```
R_stability(t) =
  - 1.0  per active SLA violation at tick t
  - 0.5  per tick of cost overrun (cost > budget_rate)
  + 0.02 per leaf node currently passing all data tests
```

### 5.4 Hack resistance — explicit analysis

Each obvious failure mode and why it doesn't pay:

| Hack attempt | Why it fails |
|---|---|
| **Drop all tables → no SLA violations** | Dropped leaf table = max-severity SLA breach (-1.0/tick); worse than the original incident. |
| **Disable alerts** | Not an available action. Alerts are simulator-side. |
| **Do nothing while system healthy** | Correct behavior; small positive from healthy-leaf bonus. Fine. |
| **Do nothing while system broken** | -1.0/tick stability penalty accumulates. |
| **Spam `submit_diagnosis` with all node names** | -2.0 per wrong submission; expected loss on guess. |
| **Tool spam to look busy** | Every tool pays an action penalty; nonzero-latency tools also advance time, so drift may bite before action. |
| **Zero-latency loop to avoid time passing** | `max_tool_calls` terminates the episode with a guardrail penalty; action penalties make this worse than honest play. |
| **Apply fixes blindly** | -5.0 per fix that breaks a healthy node; expected loss without diagnosis. |
| **Truncate the episode by triggering fatal violation** | Fatal violation = -50 terminal penalty. Strictly worse than playing out. |
| **Game the milestone window by submitting at tick 49** | Only correct submissions score; wrong = -2.0. |

The reward is bounded: best possible per episode ≈ +25–35 (two clean diagnoses + fixes + steady stability), worst ≈ -200 (cascading failures).

### 5.5 Calibration

Pre-Saturday: write 4 unit tests covering the highest-risk hack rows above, asserting the hack scores worse than honest play.

---

## 6. Two incident types — full spec

### 6.1 Incident A: Schema drift

**Trigger:** tick `T_A`, sampled from `[40, 80]` per task seed.

**Mechanism:** A source node renames one field in its emitted schema. E.g., `orders.order_total` → `orders.order_amount`. Source node continues emitting; downstream transform still references `order_total` and produces NULLs in that column.

**Symptom delay:** Cascade reaches leaf node ~15–25 ticks later (based on `produces_per_tick` and aggregation windows). Leaf SLA fires when row counts or correctness checks fail.

**Diagnosis path (canonical):** alert on leaf → `trace_lineage` (partial) → `inspect_schema` upstream chain → spot the renamed field → `get_job_history` to identify when rename occurred → `submit_diagnosis`.

**Correct fix:** `apply_fix({type: "rename_mapping", node: "stg.orders", old_field: "order_total", new_field: "order_amount"})`. Simulator updates the transform spec; downstream cascade clears within 5–10 ticks.

**Common wrong fixes (penalized):**
- Renaming the *source* field back (impossible — agent doesn't own source)
- Dropping the leaf node (SLA breach)
- Backfilling without fixing the transform (NULLs return after backfill)

### 6.2 Incident B: Cost explosion

**Trigger:** tick `T_B`, sampled from `[100, 150]`.

**Mechanism:** A scheduled transform loses its partition filter. `partition_filter` field becomes `None`. Query still succeeds — but `cost_per_tick` for that node multiplies by ~50x (simulating full-table scan vs partition scan).

**Symptom delay:** Cost meter has a budget rate of `B/tick`. Alert fires when cumulative cost exceeds `1.5 * B * tick`. Typically 8–15 ticks after trigger.

**Diagnosis path:** cost alert → `get_job_history` → identify high-cost job → `inspect_query_plan` → spot missing partition filter → `submit_diagnosis`.

**Correct fix:** `apply_fix({type: "add_partition_filter", node: "mart.marketing_roi", column: "ingest_date", value_expr: "CURRENT_DATE() - 1"})`. Cost reverts to baseline.

**Common wrong fixes:**
- Disabling the job (downstream SLA breach)
- Reducing `produces_per_tick` (incorrect; symptom is per-query cost, not volume)

### 6.3 Why this pair

Different signatures: one is a correctness incident (schema drift produces wrong data), one is an operational incident (cost explosion produces no data error but breaks the budget). Different tools dominate the diagnosis path. Both require lineage reasoning. Both have plausible-but-wrong fixes the agent must avoid.

---

## 7. Episode structure

```
Episode parameters:
  seed: int
  max_ticks: 250
  max_tool_calls: 200
  num_incidents: 2 (A then B)
  T_A ~ Uniform(40, 80)
  T_B ~ Uniform(100, 150)
  budget_rate: 2.0 / tick
  drift_noise_seed: int

Episode lifecycle:
  tick 0:        warmup, system healthy
  tick T_A:      Incident A fires (hidden)
  tick T_A+~20:  symptoms surface
  tick T_B:      Incident B fires (hidden)
  tick T_B+~10:  cost alert
  tick 250:      episode end OR earlier on fatal violation

Termination conditions:
  - tick == max_ticks
  - tool_calls == max_tool_calls                  (guardrail; -25 if before max_ticks or incidents unresolved)
  - cumulative_cost > 5 * budget_rate * max_ticks  (fatal: -50)
  - any leaf SLA violation duration > 100 ticks    (fatal: -50)
```

There is no voluntary early-finish tool in v1. If the agent believes the system is stable, the correct behavior is to keep monitoring or `wait(...)` until `max_ticks`. `max_tool_calls` is only a safety guardrail for ORS sessions; a good v1 run should stay well below it, and hitting it early applies the guardrail penalty.

For evaluation, hold out seeds with `T_A`/`T_B` near boundaries (e.g., `T_A < 45` to test fast-onset cases).

---

## 8. ORS / OpenReward integration

ORS is an HTTP protocol for RL environments. It is aligned with MCP-style tool calling, but it is not an MCP extension. The environment server exposes tools, tasks, splits, prompts, numeric reward deltas, and `finished` signals.

```python
# Pseudocode aligned with the current OpenReward / ORS shape.
# Pin the package version before implementation and verify import names locally.

from pydantic import BaseModel
from openreward.environments import (
    Environment,
    JSONObject,
    Server,
    Split,
    TextBlock,
    ToolOutput,
    tool,
)


class InspectSchemaInput(BaseModel):
    table: str


class BlastRadius(Environment):
    def __init__(self, task_spec: JSONObject = {}, secrets: dict[str, str] = {}):
        super().__init__(task_spec or {}, secrets or {})
        self.world = WorldState.from_seed(task_spec["seed"])

    @classmethod
    def list_splits(cls):
        return [
            Split(name="train", type="train"),
            Split(name="eval", type="test"),
        ]

    @classmethod
    def list_tasks(cls, split: str):
        seeds = range(80) if split == "train" else range(80, 100)
        return [
            {"id": f"seed_{s}", "seed": s, "difficulty": "v1"}
            for s in seeds
        ]

    def get_prompt(self):
        return [TextBlock(text=(
            "You are diagnosing a simulated GCP-shaped data platform. "
            "Use the available tools to infer hidden lineage, diagnose incidents, "
            "apply fixes, and keep the system healthy until the episode ends."
        ))]

    @tool
    async def inspect_schema(self, params: InspectSchemaInput) -> ToolOutput:
        schema = self.world.get_schema(params.table, allow_stale=True)
        reward = self._reward_delta(tool_cost=0.05, latency_ticks=0)
        return ToolOutput(
            blocks=[TextBlock(text=schema.to_json())],
            reward=reward,
            finished=self.world.is_terminal(),
        )

    # ... other tools ...

if __name__ == "__main__":
    Server([BlastRadius]).run(port=8080)
```

100 seeds = 100 tasks. 80 train / 20 eval. Tunable difficulty via seed-derived `T_A`, `T_B`, stale-cache behavior, dropped log lines, and partial-lineage omissions.

`wait(ticks)` is just another tool with a side effect: it advances the simulator by `ticks`, emits the integrated reward delta for those elapsed ticks, and returns the current alert/cost summary. No special ORS primitive is required.

---

## 9. Saturday execution plan (solo, time-boxed)

### Friday night (pre-event prep)

| Time | Task |
|---|---|
| 1.0h | Read docs.openreward.ai end-to-end, especially ORS spec and tasks/splits |
| 0.5h | Run one hosted OpenReward env locally to confirm SDK works |
| 1.5h | Pre-write substrate: `Node`, `DAG`, `WorldState`, drift schedule, cost meter |
| 1.0h | Pre-write reward function with the 4 hack-resistance unit tests |
| 0.5h | Skeleton repo: pyproject.toml, structure, README stub |

If Friday is short: the reward function and the simulator skeleton are the two non-negotiables.

### Saturday

| Hour | Task | Definition of done |
|---|---|---|
| 0–1 | Wire skeleton into ORS scaffolding | Empty env loads, one no-op tool callable |
| 1–3 | Implement Incident A end-to-end | One hardcoded seed runs, cascade fires, alert surfaces |
| 3–5 | Implement inspection tools (schema, sample, logs, history, lineage, plan) | All tools return realistic-shaped outputs from substrate |
| 5–6 | Implement `apply_fix` + `submit_diagnosis` + `wait` | Manual run-through of canonical Incident A diagnosis path scores correctly |
| 6–7 | First end-to-end frontier-model run, single episode | Agent completes one episode; reward signal looks sane |
| 7–9 | Implement Incident B (cost explosion) | Both incidents fire in one episode; both can be diagnosed |
| 9–10 | Add 5–10 task variants (different seeds, T_A, T_B) | `list_tasks()` returns 10+ deterministic task dicts |
| 10–11 | Reward polish + run hack-resistance tests | All 4 unit tests pass |
| 11–13 | Demo prep: baseline-vs-prompted comparison, slides | 2-minute demo recorded |
| 13–14 | Buffer / polish / submit | Final repo pushed, application demo link ready |

**The Hour 6–7 first end-to-end run is non-negotiable.** If by hour 7 you don't have a frontier model completing one episode, cut Incident B and ship a clean Incident A.

### What to cut if behind schedule

In order:
1. Drop Incident B → ship single-incident environment (still solid)
2. Drop the noise on `tail_logs` → cleaner but easier
3. Drop `trace_lineage` → forces pure inspection (still works, more painful)
4. Drop the GCP skin → just call them "node_1, node_2" (last resort; loses demo legibility)

What you do *not* cut: the reward function, partial observability, the abstract substrate, the two-phase reward decay/ramp.

---

## 10. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Simulator scope creep | High | Hard discipline: substrate is abstract. Pre-written Friday. |
| Reward hacking discovered live | Medium | Unit tests Friday night. Bounded reward. |
| OpenReward SDK gotchas | Medium | Read docs Friday, run hello-world. Discord channel for questions. |
| Frontier model can't solve any episode | Medium | Tunable difficulty knobs (drift rate, log noise, symptom delay). Have an "easy mode" seed for demo. |
| Frontier model trivially solves it | Low | Two incidents, partial observability, cost penalty on tool spam. |
| Solo bandwidth | High | Aggressive scope cuts in §9. One incident shipped clean > two half-baked. |
| Demo doesn't land | Medium | Pre-record baseline failure case + smarter prompt success case. Story > metrics. |

---

## 11. Stretch / future work

For the application form and pitch, mention these as roadmap, not commitments:

- **More incident types:** IAM permission loss, GCS duplicate ingestion, Dataflow backpressure
- **Multi-incident overlap:** two cascades active simultaneously
- **Adversarial drift:** drift schedule adapts to agent behavior
- **Larger DAGs:** 50+ nodes vs ~8 in v1
- **Cross-tenant scenarios:** multiple "teams" sharing a substrate
- **Agent-vs-agent:** one agent breaks, another fixes

---

## 12. Pitch lines (for application form / demo)

Top: **"BlastRadius — a non-stationary RL environment for diagnosing systems whose causal structure you cannot directly observe."**

Long form: "Most agent benchmarks give the agent a static repo and a failing test. BlastRadius drops the agent into a running data platform where the dependency graph is hidden, schemas drift while the agent acts, and the symptoms of a fault surface many ticks after the fault occurs. Built on OpenReward, skinned as GCP for legibility, abstract underneath for tractability. The capability tangent is causal-structure inference under partial observability — tractable in an eight-node hackathon v1, and designed to scale into hundreds-of-tool-call evaluation seeds."

Demo arc (2 minutes):
1. *Show the world.* "Eight nodes, two of them about to drift. Agent doesn't see the drift schedule."
2. *Show a naive baseline.* "Agent sees the alert, fixes the symptom, score crashes when the cascade re-fires."
3. *Show a competent run.* "Agent traces lineage, finds the upstream rename, applies the right fix, watches the cascade clear."
4. *Show the reward curve.* "Stability reward kicks in late — the agent has to keep the system alive after the diagnosis."
5. *Show one held-out seed.* "Different timing, different incident order, same capability probe."

---

## 13. Open questions for Friday

Things to resolve before Saturday morning:

1. Pin the `openreward` package version and confirm the exact import paths in a local venv.
2. How are tasks/splits surfaced to the calling agent? Does the agent see the task ID?
3. What's the recommended way to log tool-call traces for the demo: OpenReward rollout logging, local JSON traces, or both?
4. Is there a hosted environment most similar to BlastRadius I can read for reference?
5. What public seeds should be easy-mode demo seeds vs held-out eval seeds?
