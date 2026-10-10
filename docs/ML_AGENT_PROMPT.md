# Prompt for the CLI coding agent (paste everything below the line)

---

You are working in the repository `Commit-ment--Issues` on a machine that has the York/NEED data in `data/` and `dataset/`. This is the Lloyds PS2 Green Home Score project (Megathon X). The deterministic engine (scoring, feasibility, simulator, carbon, packages, bills, grants, uncertainty) is finished on branch `feature/engine-improvements`. Your job is the **ML phase**.

1. `git fetch && git checkout feature/engine-improvements && git pull`.
2. Read these files in full before writing any code, and follow them exactly:
   - `docs/ML_IMPLEMENTATION_PLAN.md` (your specification)
   - `docs/DATA.md`, `docs/LABELS.md`, `docs/DECISIONS.md` (D1–D29), `docs/ENGINE.md`, `docs/SCORE.md`
   - `configs/feature_availability.json` (column roles: what may and may not be a feature)
   - `backend/app/services/scenario_builder.py`, `score.py`, `feasibility.py`, `baseline.py`, `valuation`-related code in `scenario_builder.py`, `schemas/`
3. Execute the plan **milestone by milestone, in order (M0 → M7)**. For each milestone:
   - implement it with unit tests, then run `make test`. The existing 249 unit tests and 9 data checks must stay green;
   - commit on branch `feature/ml` with a clear message and **no AI attribution or Co-Authored-By lines**;
   - push;
   - print a short report: val metrics vs baselines with n, gate pass/fail, deviations from the plan, `git log --oneline -3`.
4. Hard rules:
   - **Privacy:** never load, print, log, commit or return address columns or full postcodes (`restricted_address` role, sales address fields). Drop them right after reading. The outward code and postcode sector are allowed. Never touch `match_audit_sample*.csv`.
   - **No leakage:** features come from `feature_ok` columns (plus text parsed from the certificate) only. Value-model features come from the **at-sale certificate**. Use the existing home splits only. Fit encoders and tuning on train only. The **test split is scored once**, in M7.
   - **Ship only what beats its baseline on validation.** Do not lower a gate. If a model fails, keep the baseline, say so, and continue.
   - **The engine stays the only writer of numbers.** Models plug in as services with `provenance = "modelled"`. Missing stays null plus a status, never 0. Every model version enters `config.versions()`.
   - **Determinism:** seed 42 and deterministic LightGBM settings. Pin `requirements.txt`.
   - **Model artifacts:** LightGBM text plus `meta.json` under `models/` (committed). Big prediction tables go under `data/processed/` (git-ignored).
5. If a column name or table differs from the plan, inspect the schema (not the values of restricted columns), adapt, and record the difference in `docs/ML.md`.
6. If anything is ambiguous, choose the more conservative and more honest option and write it down as a new decision (D30, D31, …) in `docs/DECISIONS.md`.
7. Start now with M0: run the engine calibration commands in M0 step 1, then create `feature/ml`, then write `requirements.txt` and `pipelines/ml/inspect_data.py`.
