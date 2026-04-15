# MooseGlove — Tier 2 Retrieval Rewrite Runbook

> **Read this end-to-end before you start.** The steps are ordered and
> the ordering matters. Most steps can be paused and resumed; a few
> (marked ⚠️) cannot.

## What changed

This branch rewrites the Graph RAG retrieval layer to fix the
"top diagnosis correct but `graph_path` empty" failure mode seen on
the T2DM baseline. New shape:

1. **Vector search** now returns only **phenotype seeds** (diseases
   are filtered out at the Qdrant payload level).
2. **`app/core/retrieval.py`** runs a phenotype intersection Cypher
   query: "give me the diseases that share the MOST of the patient's
   phenotypes," ordered by overlap. Each candidate carries its own
   matched edges.
3. **`app/core/lab_rules.py`** applies rules from
   **`data/clinical_rules.yaml`** as score multipliers on existing
   candidates, or as fallback seeds only when the graph pool is too
   thin. Rule-only candidates are explicitly tagged `source=clinical_rule`.
4. **`graph_traversal.expand_candidates`** enriches the top candidates
   with 1-hop context (related phenotypes, genes, drugs) for the LLM.
5. **`prompts/differential_v3.yaml`** + `context_builder.build_messages_v3`
   serializes per-candidate evidence blocks so the LLM can cite specific
   edges in its `graph_path` output.

Plus Tier 1 hygiene:

- `qdrant-client` pinned to `1.12.x` to match server (warning gone)
- `guardrails-ai` removed (was dead code)
- `services/api/Dockerfile` rewritten: pre-bakes the fastembed model,
  no pip-compile at build time, non-root `tini`-managed runtime
- `services/api/requirements.txt` now committed with `--generate-hashes`
- `primekg_loader.py` adds `name` indexes on Disease/Phenotype/Drug/Gene

Plus Phase 0 baseline:

- `eval/metrics.py` adds MRR + graph_path_rate, token-set name matcher
- `eval/run_eval.py` supports `--only-holdout`, `--only-train`, `--diff`
- `eval/cases/` has 20 hand-written clinical cases (15 train, 5 holdout)
- `tests/unit/` has 85 unit tests (all green)
- `tests/integration/test_diagnose_smoke.py` hits a live backend

## Zero-dollar guarantee checklist

Nothing below touches the Oracle "Always Free" boundary. No new
managed services, no paid tiers, no data transfer spikes. Neo4j and
Qdrant stay on the existing Docker volumes; no re-ingestion needed
unless you want the new Phenotype name index.

---

## Step 0 — Before you start

On your **local** machine (not the VM):

```powershell
# Merge the feature branch into main via GitHub.
# Open in browser:
#   https://github.com/othmanmohammad/ai-clinical-differential-diagnosis-engine/pulls
# Merge the PR for claude/free-llm-medical-nlp-8aJET → main
```

The rest of this runbook runs on the VM. SSH in:

```powershell
ssh mooseglove
```

All VM commands below assume you start in `~/mooseglove/app`.

---

## Step 1 — Pull the new code

```bash
cd ~/mooseglove/app
git fetch origin
git checkout main
git pull origin main

# Spot-check that the new files landed
ls services/api/app/core/retrieval.py \
   services/api/app/core/lab_rules.py \
   services/api/app/services/disease_index.py \
   data/clinical_rules.yaml \
   prompts/differential_v3.yaml \
   eval/cases/case_01_t2dm_classic.json \
   tests/unit/test_retrieval.py
```

All 7 files should list. If any are missing, the merge or the pull
didn't pick up the latest main — re-check GitHub.

---

## Step 2 — Capture the PRE-Tier-2 baseline

> ⚠️ **This step is critical. Do NOT skip it.** If you rebuild the
> API image before running eval, there is no baseline to compare
> against and you will have shipped blind.

The idea: run the eval harness against the **currently running
backend** (which is still the old pipeline, because you haven't
rebuilt yet) and save the result as the baseline.

```bash
cd ~/mooseglove/app

# Make sure the API container is still running the OLD code
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env ps

# Install the eval runner's deps in a throwaway venv (takes ~30s)
python3 -m venv /tmp/eval-venv
/tmp/eval-venv/bin/pip install --quiet httpx

# Get the API key
API_KEY=$(grep ^API_KEY= ~/mooseglove/.env | cut -d= -f2-)

# Run the baseline — 20 cases, roughly 4-5 seconds each = ~100s total
mkdir -p eval/results
PYTHONPATH=. /tmp/eval-venv/bin/python -m eval.run_eval \
  --api-url http://127.0.0.1:8080 \
  --api-key "$API_KEY" \
  --output eval/results/baseline_pre_tier2.json \
  --label "baseline_pre_tier2"
```

You'll see one line per case, then a summary block:

```
=== baseline_pre_tier2 ===
  Success rate:     XXX%
  MRR:              0.XXX
  Top-1 accuracy:   XX%
  Top-3 accuracy:   XX%
  Top-5 accuracy:   XX%
  Graph-path rate:  XX%       ← this is what Tier 2 is fixing
  Mean latency:     XXXXms
  P95 latency:      XXXXms
```

**Save the baseline.** It's already in `eval/results/baseline_pre_tier2.json`
but you can also print it for the chat:

```bash
cat eval/results/baseline_pre_tier2.json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d['metrics'], indent=2))"
```

**Important:** the baseline is what we compare the rewrite against.
Paste me the summary block (not the full JSON) when you're done with
this step so I have the "before" numbers on record.

---

## Step 3 — Rebuild and restart the API container

Now we actually deploy the Tier 2 code.

```bash
cd ~/mooseglove/app

# Stop and remove the current API container
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env stop api
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env rm -f api

# Rebuild. The new Dockerfile:
#   - installs deps from committed requirements.txt (no pip-compile)
#   - pre-downloads the fastembed model into /opt/fastembed
#   - uses tini for clean PID 1 signal handling
# First rebuild will take ~3-5 min (model download).
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env build api

# Start it
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env up -d api

# Watch the logs until you see pathodx_started
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env logs -f api
```

**Expected startup sequence** (new things vs. old pipeline in **bold**):

```
starting_pathodx
neo4j_driver_initialized
qdrant_client_initialized
preloading_models
nlp_pipeline_preloaded
**loading_embedding_model  model=BAAI/bge-small-en-v1.5  cache_dir=/opt/fastembed**
embedding_model_preloaded                          ← no HF Hub fetch, instant
**clinical_rules_loaded  count=12  path=/app/data/clinical_rules.yaml**
**disease_index_loaded  count=~17000  elapsed_ms=<300**
pathodx_started
Uvicorn running on http://0.0.0.0:8080
```

**Things that should NOT appear:**

- `Warning: You are sending unauthenticated requests to the HF Hub` ❌
- `Qdrant client version 1.17.x is incompatible with server 1.12.0` ❌
- `Failed to read hub registry at /app/.guardrails/hub_registry.json` ❌
- `embedder_preload_failed` ❌

If any of those appear, stop and paste me the logs.

Press **Ctrl+C** to exit the log follower once you see `pathodx_started`.

---

## Step 4 — Smoke test the Tier 2 pipeline on one request

Before running the full eval, sanity-check a single T2DM request:

```bash
API_KEY=$(grep ^API_KEY= ~/mooseglove/.env | cut -d= -f2-)

curl -sS -X POST http://127.0.0.1:8080/api/v1/diagnose \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "symptoms": ["polyuria", "polydipsia", "fatigue", "blurred vision"],
    "age": 52,
    "sex": "male",
    "medical_history": ["hypertension", "obesity"],
    "medications": [],
    "labs": {"glucose": 287, "hba1c": 9.2},
    "free_text": ""
  }' | tee /tmp/diag.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
diagnoses = d.get('diagnoses', [])
if not diagnoses:
    print('ERROR: empty diagnoses', d)
    sys.exit(1)
top = diagnoses[0]
print(f\"top            : {top['disease_name']}\")
print(f\"confidence     : {top['confidence']}\")
print(f\"verified_in_graph: {top['verified_in_graph']}\")
print(f\"graph_path     : {top['graph_path']}\")
print(f\"graph_path_len : {len(top['graph_path'])}\")
print(f\"evidence count : {len(top['supporting_evidence'])}\")
print(f\"prompt_version : {d.get('prompt_version')}\")
print(f\"model_used     : {d.get('model_used')}\")
"
```

**What to look for:**

- `top` contains "Diabetes" (either ordering of the tokens)
- `verified_in_graph` is `True`
- `graph_path` is **NOT empty** ← this is the whole point of Tier 2
- `prompt_version` is `3.0`
- HTTP 200 with reasonable latency (~3-5 seconds total)

If `graph_path` is empty, Tier 2 has a bug — paste me the full
`/tmp/diag.json` and the API logs (`docker compose logs --tail 100 api`)
and don't run the full eval yet.

---

## Step 5 — Run the POST-Tier-2 eval

```bash
cd ~/mooseglove/app
API_KEY=$(grep ^API_KEY= ~/mooseglove/.env | cut -d= -f2-)

PYTHONPATH=. /tmp/eval-venv/bin/python -m eval.run_eval \
  --api-url http://127.0.0.1:8080 \
  --api-key "$API_KEY" \
  --output eval/results/post_tier2.json \
  --label "post_tier2" \
  --diff eval/results/baseline_pre_tier2.json
```

Note the `--diff` flag: it compares against the baseline and prints
the delta inline.

Expected output tail:

```
=== post_tier2 ===
  Success rate:     XXX%
  MRR:              0.XXX    ← should be higher than baseline
  Top-1 accuracy:   XX%
  Top-3 accuracy:   XX%
  Top-5 accuracy:   XX%
  Graph-path rate:  XX%      ← should be WAY higher (this is the fix)
  Mean latency:     XXXXms
  P95 latency:      XXXXms

=== train split ===
  ...

=== holdout split ===
  ...

=== Baseline → Current ===
  MRR:             0.XXX → 0.XXX  (+0.XXX)
  Top-1 accuracy:  XX.X% → XX.X%  (+X.X%)
  Top-3 accuracy:  XX.X% → XX.X%  (+X.X%)
  Graph-path rate: XX.X% → XX.X%  (+XX.X%)   ← target: +30% or more
  Mean latency:    XXXXms → XXXXms
```

## Step 5 — Shipping gate

The rewrite is considered a success if:

1. **`graph_path_rate` goes up significantly** (≥+30 percentage points
   over baseline). This is the explicit bug we're fixing.
2. **`MRR` goes up** (+0.05 or more). Proves the ranking didn't regress.
3. **`Top-1 accuracy` is ≥ baseline** on both `train` and `holdout`
   splits. No overfitting to the training cases.
4. **No regression in success_rate** (HTTP 200 rate). Proves we didn't
   introduce crashes.
5. **P95 latency is within 2x of baseline**. Perf acceptable.

If any of those fail, we roll back (Step 8) and debug.

**Paste me the full `=== Baseline → Current ===` block** from Step 5
when you're done. That's my objective shipping signal.

---

## Step 6 — Integration smoke test (optional but fast)

If you want a belt-and-suspenders check before calling it done, run
the integration smoke tests:

```bash
cd ~/mooseglove/app

# Install pytest in the throwaway venv
/tmp/eval-venv/bin/pip install --quiet pytest

API_KEY=$(grep ^API_KEY= ~/mooseglove/.env | cut -d= -f2-)

MOOSEGLOVE_API_URL=http://127.0.0.1:8080 \
MOOSEGLOVE_API_KEY="$API_KEY" \
PYTHONPATH=. /tmp/eval-venv/bin/pytest tests/integration/ -v
```

Expected: 5 tests pass (`test_health`, `test_ready`,
`test_diagnose_t2dm_golden_case`, `test_diagnose_without_api_key_rejected`,
`test_diagnose_rate_limit_enforced`).

The rate limit test is the flaky one — if it fails, run it once more.

---

## Step 7 — Tighten the Neo4j name indexes (optional, recommended)

The new `primekg_loader.py` creates `name` indexes on Disease, Phenotype,
Drug, Gene. You ingested with the old loader so those indexes don't
exist yet. Adding them now (without re-ingesting) makes the retrieval
layer's rule-seed lookups O(1) instead of label scans.

```bash
NEO4J_PASSWORD=$(grep ^NEO4J_PASSWORD= ~/mooseglove/.env | cut -d= -f2-)

docker exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" << 'EOF'
CREATE INDEX IF NOT EXISTS FOR (n:Disease) ON (n.name);
CREATE INDEX IF NOT EXISTS FOR (n:Phenotype) ON (n.name);
CREATE INDEX IF NOT EXISTS FOR (n:Drug) ON (n.name);
CREATE INDEX IF NOT EXISTS FOR (n:Gene) ON (n.name);
SHOW INDEXES;
EOF
```

You should see 4 new indexes in the `SHOW INDEXES` output. They'll
auto-populate (takes ~30 seconds for ~50k nodes — Neo4j does it in
the background). Re-running the smoke test from Step 4 should be
noticeably faster.

---

## Step 8 — Rollback procedure (only if Step 5 fails)

If the Tier 2 eval is worse than baseline, roll back the API container
to the pre-Tier-2 image. The old image is still in Docker's local
cache under a previous hash.

```bash
# Find the previous image
docker images mooseglove-api --format "table {{.ID}}\t{{.CreatedAt}}" | head -5

# Tag the previous one as latest (replace <OLD_HASH> with the older hash)
# docker tag <OLD_HASH> mooseglove-api:latest

# Restart
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env up -d api

# Or alternatively: revert the code
cd ~/mooseglove/app
git reset --hard <COMMIT_SHA_BEFORE_TIER_2>
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env build api
docker compose -f docker-compose.prod.yml --env-file ~/mooseglove/.env up -d api
```

No data changes were made — Neo4j and Qdrant are untouched. Rollback
is a pure code revert.

---

## Step 9 — What to paste back

When you reach the end, paste me:

1. **Baseline summary block** from Step 2 (the `=== baseline_pre_tier2 ===` box)
2. **Smoke test Python output** from Step 4 (the 8 lines showing top/confidence/graph_path_len/...)
3. **Full diff block** from Step 5 (the `=== Baseline → Current ===` box)
4. **Any warnings or errors** from the API startup logs in Step 3

That's the objective shipping signal and I can verify on my end that
the numbers justify moving on to Session 3.

---

## What comes next

After Tier 2 ships cleanly:

**Session 3** (deferred from the deployment plan):

1. `Caddyfile` + Cloudflare Origin Certificate — api.mooseglove.com
2. Cloudflare Pages setup for the React frontend
3. DNS cutover (Namecheap → Cloudflare nameservers)
4. GitHub Actions CI/CD — test + build + SSH deploy
5. Keep-alive cron workflow
6. Launch checklist + SSL Labs grade sweep

Everything in Session 3 is purely edge/deploy work — no more code
rewrites to the retrieval layer.
