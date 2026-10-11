# Frontend integration: plan, implementation and verification

The web app from branch `frontend` now lives in `frontend/` and runs on the engine, ML models and LLM layer in this repository. Decision record: `docs/DECISIONS.md` D43. Route contract: `frontend/docs/API_CONTRACT.md`.

## 1. Starting point

| Side | State before integration |
|---|---|
| Frontend (`frontend` branch) | React 19 + TypeScript + Vite. One API client with two transports: `live`, which calls `/api/*` and `/llm/*`, and `fixtures`, an offline snapshot. Zod contract mirroring the engine's older Pydantic models. 62 Vitest tests. |
| Backend (`main`) | FastAPI with `/scenario`, `/explain`, `/whatif`, `/portfolio`, `/homes/{id}/score` and `/llm/*`. No `/api/*` routes and no CORS. It needs `data/processed` (not in git) to load any home. |

| Gap found | Effect if left |
|---|---|
| The frontend calls `/api/health`, `/api/demo-homes`, `/api/scenario`, `/api/packages`, `/api/portfolio` and `/api/evidence`; none existed | Live mode fails on every page |
| A fresh clone has no York data | Every live request returns 500 |
| The LLM routes ran their own default request (no sensitivity), but the scenario ID hashes the whole request | Every LLM explanation returns 409 stale, so the UI always shows the template |
| What-if outcomes can now be `change_assumptions` / `invalid_request` | Contract error in the what-if box |
| Engine v3 and ML outputs were not in the contract (bills, grants, payback, loan, Monte Carlo ranges, value range, indicative EPC, totals) | Key results invisible; "bills not modelled" claims on screen were wrong |
| The snapshot came from an older engine (demo A 44 → 75, loft feasible) | Offline numbers disagree with the engine (now 44 → 70; flat roof, so loft is infeasible under D20) |
| `value_gate.coverage_check` is now an object | "[object Object]" on Method & Evidence |

## 2. Plan (executed in this order)

1. **Bring the app in without touching its history.** `frontend/` on branch `feature/frontend-integration` from `main`. Loose planning notes stay local (`frontend/docs/notes/` is git-ignored). The 14 MB screencast stays on the `frontend` branch.
2. **Backend routes for the contract** (`backend/app/web_api.py`, prefix `/api`). These are thin wrappers over `services/api.py` with the address guard on every response.
3. **Run without the York data** (`backend/app/data/demo_homes.py`, `loaders.data_mode()`). The three public demo homes are rebuilt from `configs/demo_homes.json` plus the certificate fields documented in `tests/fixtures/hand_calc_demo.py`. Gate: they must reproduce `tests/fixtures/scenario_{a,b,c}.json` exactly.
4. **Align the LLM routes.** They take the rest of the engine request (assumptions, reading, `include_*`) and rerun exactly that request. What-ifs that change prices, grants or readings go through `request_runner`.
5. **CORS and serving.** `CORS_ORIGINS` (default: the Vite dev and preview ports). FastAPI serves `frontend/dist` with a fallback to the single-page app.
6. **Contract update** (`frontend/src/api/schema.ts`) to the current Pydantic models: new assumptions and request flags, `bills`, `finance`, `uncertainty`, `recommendation_ranking`, `install_sequence`, `epc_change`, valuation fields, `EndUses` totals, new package fields, new what-if kinds.
7. **Regenerate the offline snapshot** from this engine (`make web-fixtures`; parity-checked). The contract test reads the hand-calculated fixtures directly.
8. **Show the new engine outputs, computing nothing in the browser:**
   - bills, grants and payback panel with the illustrative loan;
   - Monte Carlo P10–P90 table;
   - value range with caveats;
   - indicative EPC band change;
   - gas and electricity after;
   - cost after grants and bill change on plan cards and in the Decision Studio;
   - plan check "Can I afford it?" from engine finance;
   - tariff and grants controls in the Scenario Lab;
   - what-if applies the validated `new_request`;
   - Method & Evidence renders the model registry and LLM evaluation tables;
   - decision record includes bills, finance, ranges, value and EPC change.
9. **Verify** at every layer (section 4), then document (this file, D43, both READMEs, API contract) and add Make targets.

## 3. What changed

| Area | Files |
|---|---|
| Backend | `backend/app/web_api.py` (new), `backend/app/evidence.py` (new), `backend/app/data/demo_homes.py` (new), `backend/app/data/loaders.py` (demo fallback, `data_mode`), `backend/app/llm/api.py` (request fields, `request_runner`), `backend/app/main.py` (router, CORS, static serving) |
| Backend tests | `tests/unit/test_web_api.py`, 9 tests: demo parity, every `/api` route and its errors, address guard, LLM scenario-ID match, what-if through the engine |
| Frontend contract | `src/api/schema.ts`, `src/api/transport.ts` (full request to LLM routes), `src/hooks/useScenarioLab.ts` (`applyRequest`, uncertainty), `src/hooks/useExplanation.ts` |
| Frontend UI | `components/energy/MoneyPanel.tsx` (new), `EnergyBalance.tsx`, `pages/myhome/OptionsTab.tsx`, `components/packages/DecisionStudio.tsx`, `components/plan/PlanCheck.tsx`, `components/whatif/ScenarioLab.tsx` (`TariffForm`, what-if kinds), `pages/MethodEvidence.tsx`, `components/layout/AppShell.tsx` (demo-only note), `utils/{evidence,scenarioDiff,decisionRecord,labels}.ts` |
| Frontend tests | `contract.test.ts` (reads hand-calc fixtures), `transport.test.ts` (+2: full request to LLM routes, new what-if kinds), `app.test.tsx` (+1: money panel; value and EPC test rewritten), `guided.test.tsx`, `scenarioLab.test.tsx`, updated for the current engine |
| Snapshot | `frontend/scripts/generate_fixtures.py` uses the in-repo engine and demo source; `frontend/public/fixtures/` regenerated (198 scenario files, 5.3 MB) |
| Tooling and docs | `Makefile` (`web-install`, `web-dev`, `web-test`, `web-build`, `web`, `web-fixtures`), `readme.md`, `frontend/README.md`, `frontend/docs/API_CONTRACT.md`, `docs/DECISIONS.md` D43 |

## 4. Verification (2026-10-11)

| Check | Result |
|---|---|
| Backend `pytest` (whole suite, Python 3.13 venv) | 691 passed, 37 skipped (real-data tests; `data/` is not in git), 0 failed |
| `tests/unit/test_web_api.py` | 9 / 9 pass |
| Frontend `npm run typecheck`, `npm run lint` (oxlint) | Clean |
| Frontend `npm test` (Vitest) | 65 / 65 pass |
| Frontend `npm run build` | OK (live and snapshot modes) |
| Snapshot parity | Demo A 44 → 70, gas +20,957 kWh, electricity −4,865 kWh, carbon 3,120 kg: identical to `tests/fixtures/scenario_a.json`; B and C identical |
| Live browser run (Chromium, built app served by FastAPI, demo-home mode, no LLM key) | 48 / 48 checks. Live status; money panel (bills £3,023 → £2,633, £16,537 after £7,500 grant, loan disclaimer, P10–P90); value range; EPC E → C; explanation bound to the same scenario ID (no 409); measure toggle, tariff and natural-language what-if all recalculate through `/api/scenario`; homes B and C (bills "not estimated", never 0); portfolio; Method & Evidence tables; no horizontal overflow on 5 pages at 1440 / 1024 / 768 / 375 px; no console errors |
| Vite dev proxy and CORS | `/api/*` and `/llm/*` reach FastAPI through `:5173`; preflight from `http://localhost:5173` returns 200 |

## 5. How to run

```bash
make web-install        # once
make web                # http://127.0.0.1:8000: app + API, one process
make api & make web-dev # development: http://localhost:5173 with hot reload
make web-test           # frontend checks; `make test` for the backend
```

With the York build in `data/processed/region=york/` the same commands serve all 65,872 homes; `/api/health` reports `york_parquet`. With a provider key in `.env`, explanations and what-if parsing use the LLM (D39, D41). Without one they use the template and keyword parser.

## 6. Not done, and why

- **Live-LLM run:** no provider key in this environment. The UI and routes are exercised with the template and keyword parser.
- **York-wide portfolio:** needs the York build, which is not in git. The code path is the same; only the demo-home source was exercised here.
- **Portfolio EPC-band and property-type filters:** need `rating` / `property_type` in portfolio rows (contract request 4).
- **`ScenarioRequest` situation fields** (role, horizon, budget in the main request): still presentation-only in the UI (contract "Situation fields").
