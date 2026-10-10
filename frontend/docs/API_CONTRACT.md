# Frontend ↔ backend API contract

The frontend (`src/api/transport.ts`) calls the routes below. **They are implemented** in `backend/app/web_api.py` (`/api/*`) and `backend/app/llm/api.py` (`/llm/*`) and tested in `tests/unit/test_web_api.py`. Without a backend the app runs on an offline snapshot of real engine output (`public/fixtures/`, see README). Switching to the live backend is one setting: `VITE_DATA_MODE=live` (`make web-dev`, or `make web` to serve the built app from FastAPI).

Every response is validated in the browser against `src/api/schema.ts`, which mirrors the Pydantic models in `backend/app/schemas/`. If a response does not match, the UI shows a "contract" error instead of rendering numbers.

## Conventions the UI relies on

- **Serialisation:** `model.model_dump(mode="json")`, with every field present. Missing values are `null` plus a status, never `0` and never omitted.
- **Sign:** savings = before − after. A negative value is an increase (for example electricity after a heat pump).
- **Units:** kWh/year, kg CO₂e/year, GBP.
- **Echo:** `ScenarioResult.request` must echo the request that produced it. The UI rejects a result whose echoed request differs from the one it sent (stale-response guard).
- **Errors:** FastAPI's default `{"detail": ...}`. The UI maps status codes:

| Status | UI meaning |
|---|---|
| 404 | unknown home or route |
| 409 | stale scenario (LLM routes) |
| 422 | invalid request |
| 501 / 503 | service not available (e.g. LLM disabled, data missing) |
| other | generic backend error |

- **CORS:** in development, Vite proxies `/api` and `/llm` to `VITE_DEV_PROXY_TARGET` (default `http://127.0.0.1:8000`), so no CORS is needed. If the frontend is served from another origin, set `VITE_API_BASE_URL` and add that origin to the backend's `CORS_ORIGINS` (comma list; default: the Vite dev and preview ports). `make web` serves the built app from FastAPI on the same origin.
- **Data mode:** `GET /api/health` returns `data_mode` = `york_parquet` (the York build is present) or `demo_homes` (only the three public demo homes, rebuilt from `configs/demo_homes.json`; D43).

## Engine routes (`backend/app/web_api.py`)

| Route | Engine call | Response |
|---|---|---|
| `GET /api/health` | `config.versions()` | `{status: "ok", data_mode: "york_parquet" \| "...", versions: {...}}` |
| `GET /api/demo-homes` | `configs/demo_homes.json` | `[{home_id, case, display_label, why_chosen, rating, property_type, postcode_outward}]` (public fields only) |
| `POST /api/scenario` | `services.api.build(ScenarioRequest)` | `ScenarioResult` |
| `POST /api/packages` body `{home_id, assumptions, user_reading, budget_gbp}` | `services.api.search(home_id, assumptions, budget_gbp=…, user_reading=…)` | `PackageSearch` with `budget_gbp` echoed. The engine keeps packages costing ≤ budget, then picks the featured plans. Used by "Your options" when the user sets a budget |
| `GET /api/portfolio?top_n=100&split=&rank_by=` | `services.api.portfolio(top_n, split, rank_by)` | `{summary, homes}` exactly as `portfolio()` returns, plus `data_mode`, `data_note`. `rank_by`: improvement_potential, fabric_potential, carbon_per_pound, carbon_saving |
| `GET /api/evidence` | `backend/app/evidence.py` | `versions, sources, score, catalogue, emission_factors, simulator_vs_need, value_gate, energy_prices, grants, finance, models, policy_comparison, llm_evaluation` (the snapshot uses the same builder) |

### `POST /api/scenario`

The body is `ScenarioRequest`. The UI always sends:

- `include_packages: true`, `include_sensitivity: true` and `include_uncertainty: true` (about 0.4 s per call with the 300-draw Monte Carlo);
- `measures: null` for the engine default (every measure that is not infeasible);
- an explicit list, in engine order, for a what-if.

The UI never sends an infeasible measure: it disables those controls.

Assumptions the UI can change:

- `impact_level` (low / mid / high);
- `heat_pump_scop` (2.5, catalogue, 3.5);
- `baseline_scale` (0.85 / 1 / 1.15: people at home);
- `gas_price_p`, `elec_price_p` (your tariff, p/kWh; null = the price cap) and `apply_grants`;
- `user_reading` (gas and/or electricity kWh per year).

`ScenarioResult` blocks the UI renders beyond the core: `bills`, `finance` (with `illustrative_loan`), `uncertainty`, `valuation` (range, current value, caveats), `score_after.epc_change`, `install_sequence`, `recommendation_ranking`, and the `EndUses` totals (`gas_total`, `elec_import`, `purchased`).

### `GET /api/evidence` blocks the UI shows as "Evaluation pending"

- `models.status`
- `policy_comparison.status`
- `llm_evaluation.status`

Set these to `"available"` with a `detail` object once results exist. The UI then shows the detail instead of the pending badge.

## LLM routes (`backend/app/llm/api.py`)

| Route | Used for |
|---|---|
| `GET /llm/health` | Natural-language features are enabled only when `enabled && engine_configured` |
| `POST /llm/explain {property_id, measures, expected_scenario_id, template_mode, assumptions, user_reading, include_packages, include_sensitivity, include_uncertainty}` | Explanation of the confirmed scenario. The UI uses `explanation` only; it is discarded unless `explanation.scenario_id` equals the scenario on screen |
| `POST /llm/whatif {property_id, measures, question, expected_scenario_id, assumptions, user_reading, include_*}` | Natural-language what-if. `outcome.kind` is `change_measures`, `change_assumptions`, `question_about_current`, `out_of_scope` or `invalid_request` (with `invalid_reason`). The UI applies `outcome.new_request` (the engine-validated `ScenarioRequest`) through `POST /api/scenario`; numbers never come from this route |

**How the scenario IDs match (D43).** The scenario ID hashes the whole engine request, so the UI sends the rest of the request it is showing with every LLM call; the server runs exactly that request (`configure_engine(runner, request_runner=run_request)` in `backend/app/main.py`). Without those fields the server runs its default request, whose ID differs, and returns 409 when `expected_scenario_id` is set.

## Requests to the backend team

These are not blocking. The UI works without them and says what is missing.

1. ~~**Computed totals.**~~ Done: `EndUses` exports `gas_total`, `elec_import`, `elec_gross` and `purchased`; the UI prints them.
2. **Typed dicts.** Type `home`, `standalone`, `sensitivity`, `audit` and `PackageResult.sensitivity` as models. The UI types them from the engine code today (`src/api/schema.ts`).
3. **Closed lists.** Add closed enums for the strings the UI writes copy for: `Baseline.gas_status/elec_status/source`, `PartScore.status`, simulator `reason_code`s.
4. **Portfolio fields and paging.** Add `rating` and `property_type` to portfolio rows, so the EPC-band and property-type filters can be enabled. For large `top_n`, also add server-side search and paging (`q`, `class`, `offset`, `limit`).

## Situation fields (requested; the UI already collects them)

The guided UI asks optional "Your situation" questions. They are stored only in the browser, and today they change **presentation only**: wording, permission notes, budget flags, and which featured pick is highlighted. To let the engine use them, please add these **optional** fields to `ScenarioRequest`. The UI will send them as soon as the schema accepts them; `extra="forbid"` rejects them today, so nothing is sent yet.

| Field | Type | Engine use |
|---|---|---|
| `budget_gbp` | `float \| null` | Already served by `POST /api/packages` (engine budget search). Adding it to `ScenarioRequest` would also put budget-aware picks in the main result |
| `threshold_pct` | `float \| null` | the package threshold (default 10%) |
| `role` | `"owner" \| "tenant" \| "landlord" \| "leaseholder" \| "manager" \| null` | permission-aware feasibility (e.g. a tenant cannot install without consent) |
| `horizon_years` | `float \| null` | needed for payback over the expected stay |
| ~~`tariff`~~ | done as `Assumptions.gas_price_p` / `elec_price_p` (D26) | bills and payback are engine outputs (`bills`, `finance`) and shown in the UI |

**Occupancy scenarios already use the engine.** "People at home: fewer / as recorded / more" sends `assumptions.baseline_scale` 0.85 / 1.0 / 1.15, the same ±15% range the engine's sensitivity analysis uses.
