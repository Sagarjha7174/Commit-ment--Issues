
hi
## Reproduce the data

Data stage for the Lloyds PS2 Green Home Score (City of York). Details: `docs/DATA.md`, `docs/LABELS.md`, `docs/DECISIONS.md`.

**Setup:** `python3 -m venv .venv && .venv/bin/pip install pandas pyarrow duckdb rapidfuzz odfpy openpyxl tabulate pytest`

**Inputs that must already exist:** `dataset/` (raw EPC zip, NEED, Impact of measures, Land Registry, DESNZ GHG) and
`data/processed/need_4m.parquet`, `need_50k.parquet`, `ppd.parquet`. Note: the scripts that produced these three
parquet files are not in the repo at present (see docs/DATA.md 1.2 and 1.4 for their rules).

| Command (Linux/macOS) | Windows | What it does | Typical runtime |
|---|---|---|---|
| `make data-check` | `scripts\run_data.ps1 data-check` | 9 integrity/leakage checks, PASS/FAIL table | ~2 s |
| `make data-rebuild` | `scripts\run_data.ps1 data-rebuild` | reruns the pipelines below in order | ~2 min (reusing the EPC extract); ~5 min if `epc_certs_all.parquet` is absent (re-streams the 8.3 GB zip) |
| `make data-test` | `scripts\run_data.ps1 data-test` | `pytest tests/unit tests/data` | ~1 s |

**Rebuild order** (all deterministic, seed 42):
1. `pipelines/build_region.py --reuse-extract` -> `data/processed/region=york/` (homes, certificates, history, recommendations, sales, benchmarks, quality report)
2. `pipelines/build_catalogue.py` -> `configs/retrofit_catalogue.json` (cat-v2)
3. `pipelines/freeze_score_params.py` -> `configs/score_params.json` (TRAIN only)
4. `pipelines/tag_homes.py` -> `homes_tagged.parquet` (provenance, flags)
5. `pipelines/build_feature_availability.py` -> `configs/feature_availability.json`
6. `pipelines/select_demo_homes.py` -> `configs/demo_homes.json`, `docs/DEMO_HOMES.md`
7. `pipelines/make_monthly_demo.py` -> `monthly_synthetic.parquet` (SYNTHETIC, annualisation demo only)
8. `pipelines/audit_sales_matches.py` -> `configs/value_gate.json` (reads the manual audit in `match_audit_sample.csv`)

Rerunning gives identical outputs (build_region compares a fingerprint with the previous run; homes_tagged content hash verified).

## ML phase (models, evaluation)
Data notes and model cards `docs/ML.md`; decisions `docs/DECISIONS.md` (D30+); results `docs/EVALUATION.md`.

```bash
.venv/bin/pip install -r requirements.txt
make ml-inspect   # schema-only inventory (no address columns are ever loaded)
make ml-data      # certificate features + counterfactual EPC pairs
make ml-train     # SAP, value, energy (NEED) and recommender models; gates on validation only
make ml-predict   # York energy and recommender predictions (data/processed, git-ignored)
make ml-explain   # SHAP and validation slices
make ml-eval      # test split scored ONCE, value coverage check, eval/test_predictions.csv, docs/EVALUATION.md
make test
```
Trained models are committed under `models/` (LightGBM text + meta.json); only models listed as shipped in
`configs/model_registry.json` are loaded, and every model version enters the scenario id.

## API and LLM explanations
```bash
cp .env.example .env            # optional: add ANTHROPIC_API_KEY (or GROQ_API_KEY / GEMINI_API_KEY); without a key
                                # every route works with the deterministic template explainer
make api                        # http://localhost:8000/docs
curl -s localhost:8000/explain -H 'content-type: application/json' \
     -d '{"home_id": "U100050529765", "question": "How much could I save?"}'
curl -s localhost:8000/whatif -H 'content-type: application/json' \
     -d '{"home_id": "U100050529765", "question": "What if electricity was on a 15p tariff?"}'
make llm-eval                   # held-out question set -> docs/LLM_EVALUATION.md (real LLM when a key is set)
```
Answers return `{answer, cited_values, scenario_id, grounded}`; every number comes from the engine (`docs/DECISIONS.md` D39).

## Web app (frontend/)
React + TypeScript + Vite. Every number on screen comes from the engine through `/api/*` and `/llm/*`
(`frontend/docs/API_CONTRACT.md`, `docs/FRONTEND_INTEGRATION.md`, decision D43).
```bash
make web-install                # npm ci in frontend/
make web                        # build in live mode, then FastAPI serves app + API on http://127.0.0.1:8000
# or, for development with hot reload (two terminals):
make api                        # FastAPI on :8000
make web-dev                    # Vite on :5173, proxying /api and /llm to :8000
make web-test                   # typecheck, lint, 65 Vitest tests
make web-fixtures               # regenerate the offline snapshot from this engine (parity-checked)
```
Without the York build (`data/` is not in git) the API serves the three public demo homes and says so; with no LLM key,
explanations and what-ifs use the deterministic template and keyword parser.
