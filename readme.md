# HABI — Green Home Score (Lloyds PS2, Megathon X)

## Requirements

- Python 3.14 (3.13 also works)
- Node.js 22 or newer
- GNU Make

Run every command from the repository root.

## 1. Download the data

The data is not included in the repository. Download it and extract it at the repository root:

**Project data (processed York build, ~170 MB):** https://drive.google.com/file/d/1c7r9Rfmo-o2rHwgGTbz244gTtOXkh4JU/view?usp=sharing

After extracting, these paths must exist:

```text
data/processed/region=york/homes_tagged.parquet
data/processed/need_4m.parquet
data/processed/need_50k.parquet
data/processed/ppd.parquet
```

The app also runs without the data (on three demo homes only).

### Original public sources (only needed to rebuild the data from scratch into `dataset/`)

| Dataset | Link |
|---|---|
| EPC domestic certificates and recommendations (MHCLG) | https://get-energy-performance-data.communities.gov.uk |
| NEED anonymised data 2026 (DESNZ) | https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026 |
| NEED Impact of measures 2026 (DESNZ) | https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-impact-of-measures-data-tables-2026 |
| HM Land Registry Price Paid Data 2025–2026 | https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads |
| DESNZ GHG conversion factors 2026 | https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026 |
| ECUK 2026 end-use tables (DESNZ) | https://www.gov.uk/government/statistics/energy-consumption-in-the-uk-2026 |

## 2. Model weights

The trained models are included under `models/`. No download is needed.

## 3. Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make web-install
```

## 4. Configure (optional)

```bash
cp .env.example .env
```

Add any of `GROQ_API_KEY`, `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` to `.env`. Without keys, everything still runs.

## 5. Run

```bash
make web
```

Open http://127.0.0.1:8000.

Example home ids: `U100050529765`, `A012dcfda4e502be0`, `U100050565716`
(e.g. http://127.0.0.1:8000/home/U100050529765).

Development mode with hot reload (two terminals):

```bash
make api        # API on http://127.0.0.1:8000 (docs at /docs)
make web-dev    # web app on http://localhost:5173
```

## 6. Test

```bash
make test        # backend tests
make web-test    # frontend typecheck, lint and tests
make data-check  # data integrity checks (needs the data)
make data-test   # unit + data-integrity tests
```

## 7. Rebuild the data (optional)

Place the original sources in `dataset/`, then:

```bash
make data-rebuild
```

## 8. All commands

| Command | Purpose |
|---|---|
| `make web-install` | install frontend dependencies |
| `make web-build` | build the web app (live mode) into `frontend/dist` |
| `make web` | build the web app and serve app + API on :8000 |
| `make api` | API only on :8000 |
| `make web-dev` | web app dev server on :5173 |
| `make web-test` | frontend typecheck, lint and tests |
| `make web-fixtures` | regenerate the web app's offline snapshot |
| `make test` | backend tests |
| `make data-check` | data integrity checks |
| `make data-test` | unit + data-integrity tests |
| `make data-rebuild` | rebuild the processed data from `dataset/` |
| `make score` | score every home |
| `make validate-sim` | validate the simulator against measured data |
| `make elec-split` | build the electric-heating split |
| `make combo-cal` | build the combination calibration |
| `make engine-cal` | build the engine calibration |
| `make ml-inspect` | data inventory (schema only) |
| `make ml-data` | build ML feature tables |
| `make ml-train` | train the models |
| `make ml-predict` | predictions with the shipped models |
| `make ml-explain` | model explanations and slices |
| `make ml-eval` | final test evaluation (runs once) |
| `make ml` | full ML pipeline (long) |
| `make llm-eval` | LLM evaluation (uses your API keys) |

Windows (data steps only): `scripts\run_data.ps1 data-check | data-rebuild | data-test`
