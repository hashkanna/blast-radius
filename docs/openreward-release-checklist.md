# OpenReward Release Checklist

Use this checklist before the hackathon presentation.

## Local Verification

```bash
pip install -e ".[dev]"
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
PYTHONPATH=src python3 scripts/baseline_vs_competent.py --seed 0
PYTHONPATH=src python3 scripts/analyze_trace.py artifacts/baseline_vs_competent_seed0.json
```

Expected seed 0 result:

```text
naive_baseline  -164.9057
competent          5.6135
score_delta=170.5192
```

## Local ORS Server

```bash
pip install -e ".[ors]"
python3 server.py --port 8080
```

In another terminal:

```bash
PYTHONPATH=src python3 scripts/ors_scripted_rollout.py --base-url http://localhost:8080
```

## Docker

The Dockerfile is intended for an OpenReward environment server, not a sandbox image.

```bash
docker build --platform linux/amd64 -t blast-radius:local .
docker run --rm -p 8080:8080 blast-radius:local
```

Then run the local ORS scripted rollout against `http://localhost:8080`.

## Public OpenReward Environment

The repository is intended to be deployed from:

```text
https://github.com/hashkanna/blast-radius
```

OpenReward's GitHub deployment flow requires creating the environment first, then linking it to a GitHub repository. With `OPENREWARD_API_KEY` set:

```bash
pip install openreward
orwd create blast-radius --description "Hidden-lineage incident diagnosis for agentic RL"
orwd link <namespace>/blast-radius hashkanna/blast-radius --cpu-memory 1:4 --max-scale 3
orwd update <namespace>/blast-radius --public
orwd deployments <namespace>/blast-radius
```

If using the web UI instead:

1. Open `https://openreward.ai/{username}/blast-radius`.
2. Click `Connect GitHub`.
3. Select `hashkanna/blast-radius`.
4. Use default branch `main`.
5. Use `1:4` CPU/memory unless the hosted smoke test shows otherwise.
6. Deploy and wait for build status `deployed`.
7. Ensure the environment is public.
8. Confirm the OpenReward page renders this README as the environment card.
9. Confirm `blastradiusenv` exposes:
   - splits: `train`, `eval`
   - 80 train tasks, 20 eval tasks
   - all eleven tools
10. Run one hosted task and save the trace URL or screenshot for the presentation.

Reference docs:

- <https://docs.openreward.ai/deployment/github-integration>
- <https://docs.openreward.ai/environments/using-the-cli>
- <https://docs.openreward.ai/rollouts/recording-rollouts>

## Presentation Artifacts

Use:

- `docs/presentation-outline.md`
- `docs/blastradius-hackathon-presentation.pptx`
- `docs/presentation-previews/montage.png`
- `artifacts/demo_summary_seed0.json`
- `artifacts/baseline_seed0.json`
- `artifacts/competent_seed0.json`

Regenerate the deck and previews:

```bash
NODE_PATH=/Users/kanna/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules \
  /Users/kanna/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  scripts/build_presentation.mjs
```

If a real model run is available, also include:

- `artifacts/openai_seed0.json`
- analyzer output from `scripts/analyze_trace.py artifacts/openai_seed0.json`
