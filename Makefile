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

# ---- ML phase (docs/ML.md, docs/EVALUATION.md) ----
.PHONY: ml-inspect
ml-inspect:   # schema-only inventory -> docs/validation/ml_data_inventory.txt
	$(PY) pipelines/ml/inspect_data.py

.PHONY: ml-data ml-train ml-predict ml-explain ml-eval ml
ml-data:      # certificate feature table and counterfactual EPC pairs
	$(PY) pipelines/ml/build_feature_tables.py
	$(PY) pipelines/ml/build_epc_pairs.py

ml-train:     # tune + train every model on train, gates on val only (writes models/, configs/model_registry.json)
	$(PY) pipelines/ml/train_sap_model.py
	$(PY) pipelines/ml/train_value_model.py
	$(PY) pipelines/ml/train_energy_model.py
	$(PY) pipelines/ml/train_recommender.py

ml-predict:   # York predictions with the shipped models (data/processed, git-ignored)
	$(PY) pipelines/ml/predict_energy_york.py
	$(PY) pipelines/ml/score_recommender_york.py

ml-explain:   # SHAP and validation slices
	$(PY) pipelines/ml/explain_models.py

ml-eval:      # test split scored ONCE, value coverage check, test predictions
	$(PY) pipelines/ml/evaluate_models.py
	$(PY) pipelines/ml/write_test_predictions.py
	$(PY) pipelines/ml/write_evaluation_md.py

ml: ml-data ml-train ml-predict ml-explain ml-eval

# ---- LLM layer and API (docs/LLM_EVALUATION.md) ----
.PHONY: api llm-eval
api:          # FastAPI on :8000 (works without an LLM key: template explainer)
	$(PY) -m uvicorn backend.app.main:app --port 8000

llm-eval:     # held-out question set -> docs/validation/llm_eval.json + docs/LLM_EVALUATION.md (LLM if a key is set)
	$(PY) pipelines/llm/evaluate_llm.py
