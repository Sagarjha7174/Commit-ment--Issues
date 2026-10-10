
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
