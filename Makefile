# Data stage for the Lloyds Green Home Score project (City of York).
# Requires .venv (python -m venv .venv && .venv/bin/pip install pandas pyarrow duckdb rapidfuzz odfpy openpyxl tabulate pytest "pydantic>=2.7")
PY ?= .venv/bin/python

.PHONY: data-check data-rebuild data-test

data-check:
	$(PY) pipelines/check_data.py

# Rebuild everything downstream of the raw files, in dependency order.
# Inputs that must already exist: dataset/ (raw), data/processed/need_4m.parquet, need_50k.parquet, ppd.parquet.
data-rebuild:
	$(PY) pipelines/build_region.py --reuse-extract
	$(PY) pipelines/build_catalogue.py
	$(PY) pipelines/freeze_score_params.py
	$(PY) pipelines/tag_homes.py
	$(PY) pipelines/build_feature_availability.py
	$(PY) pipelines/select_demo_homes.py
	$(PY) pipelines/make_monthly_demo.py
	$(PY) pipelines/audit_sales_matches.py

data-test:
	$(PY) -m pytest -q tests/unit tests/data

# ---- engine (backend/app/services) ----
.PHONY: score test
score:
	$(PY) pipelines/score_homes.py

test:
	$(PY) -m pytest -q

.PHONY: validate-sim
validate-sim:
	$(PY) pipelines/validate_simulator.py

# ---- engine refinements (D16, D17) ----
.PHONY: elec-split combo-cal
elec-split:   # needs data/processed/region=york/benchmarks.parquet
	$(PY) pipelines/build_electric_heating_split.py

combo-cal:    # needs only docs/validation/simulator_vs_need.json
	$(PY) pipelines/build_combination_calibration.py

# ---- engine-v3 calibration (D15 rev., D21, D22, D23, D28): needs data/processed/ and the York build ----
.PHONY: engine-cal
engine-cal:
	$(PY) pipelines/build_engine_calibration.py
