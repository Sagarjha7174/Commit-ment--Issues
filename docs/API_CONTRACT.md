# Frontend ↔ backend API contract

The frontend (`src/api/transport.ts`) calls the routes below. Until they exist it runs on an offline snapshot of real engine output (`public/fixtures/`, see README). Switching to the live backend is one setting: `VITE_DATA_MODE=live`.

Every response is validated in the browser against `src/api/schema.ts`, which mirrors the Pydantic models in `backend/app/schemas/` on `feature/engine-core`. If a response does not match, the UI shows a "contract" error instead of rendering numbers.

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

- **CORS:** in development, Vite proxies `/api` and `/llm` to `VITE_DEV_PROXY_TARGET` (default `http://127.0.0.1:8000`), so no CORS is needed. If the frontend is served from another origin, set `VITE_API_BASE_URL` and allow that origin.

## Engine routes (to be added in `backend/app/main.py`)

| Route | Engine call | Response |
|---|---|---|
| `GET /api/health` | `config.versions()` | `{status: "ok", data_mode: "york_parquet" \| "...", versions: {...}}` |
| `GET /api/demo-homes` | `configs/demo_homes.json` | `[{home_id, case, display_label, why_chosen, rating, property_type, postcode_outward}]` (public fields only) |
| `POST /api/scenario` | `services.api.build(ScenarioRequest)` | `ScenarioResult` |
| `POST /api/packages` body `{home_id, assumptions, user_reading, budget_gbp}` | `services.api.search(home_id, assumptions, budget_gbp=…, user_reading=…)` | `PackageSearch` with `budget_gbp` echoed. The engine keeps packages costing ≤ budget, then picks the featured plans. Used by "Your options" when the user sets a budget |
| `GET /api/portfolio?top_n=100&split=` | `services.api.portfolio(top_n, split)` | `{summary, homes}` exactly as `portfolio()` returns |
| `GET /api/evidence` | configs and validation files | see `evidence` in `scripts/generate_fixtures.py`: `versions, sources, score, catalogue, emission_factors, simulator_vs_need, value_gate, models, policy_comparison, llm_evaluation` |

### `POST /api/scenario`

The body is `ScenarioRequest`. The UI always sends:

- `include_packages: true` and `include_sensitivity: true` (about 6–50 ms per call, according to `docs/ENGINE.md`);
- `measures: null` for the engine default (every measure that is not infeasible);
- an explicit list, in engine order, for a what-if.

The UI never sends an infeasible measure: it disables those controls.

Assumptions the UI can change:

- `impact_level` (low / mid / high);
- `heat_pump_scop` (2.5, catalogue, 3.5);
- `user_reading` (gas and/or electricity kWh per year).

### `GET /api/evidence` blocks the UI shows as "Evaluation pending"

- `models.status`
- `policy_comparison.status`
- `llm_evaluation.status`

Set these to `"available"` with a `detail` object once results exist. The UI then shows the detail instead of the pending badge.

## LLM routes (exist on `feature/llm-layer`, `backend/app/llm/api.py`)

| Route | Used for |
|---|---|
| `GET /llm/health` | Natural-language features are enabled only when `enabled && engine_configured` |
| `POST /llm/explain {property_id, measures, expected_scenario_id, template_mode}` | Explanation of the confirmed scenario. The UI uses `explanation` only; it is discarded unless `explanation.scenario_id` equals the scenario on screen |
| `POST /llm/whatif {property_id, measures, question, expected_scenario_id}` | Natural-language what-if. The UI applies `outcome.new_measures` through `POST /api/scenario`; numbers never come from this route |

**Integration risks for the API owner:**

1. **Scenario shape.** `configure_engine(runner)` currently runs on `tests/llm/fake_engine.py`, whose scenario dict follows the plan's illustrative JSON, not `ScenarioResult`. The real runner must return a scenario whose `scenario_id` equals the one `POST /api/scenario` returns for the same request. Otherwise every explanation is rejected as stale, and the UI falls back to its template.
2. **Measures only.** The LLM routes accept a measure selection only. For scenarios with changed assumptions or a meter reading, the UI does not call the LLM and uses the deterministic template, saying why.

## Requests to the backend team

These are not blocking. The UI works without them and says what is missing.

1. **Computed totals.** Serialise `EndUses.gas_total`, `elec_import` and `purchased` as Pydantic `computed_field`s. Today the UI shows the end-use parts and the engine's savings, but cannot print "gas after" without adding numbers itself, which it refuses to do.
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
| `tariff` | `{gas_p_per_kwh, elec_p_per_kwh, gas_standing_p_per_day, elec_standing_p_per_day} \| null` | → `bill_change_gbp` and payback. The UI shows "not estimated" until these exist |

**Occupancy scenarios already use the engine.** "People at home: fewer / as recorded / more" sends `assumptions.baseline_scale` 0.85 / 1.0 / 1.15, the same ±15% range the engine's sensitivity analysis uses.
