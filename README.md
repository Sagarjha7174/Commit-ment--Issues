# Green Home Score: Retrofit Decision Studio (frontend)

React + TypeScript + Vite frontend for the Lloyds PS2 Green Home Score engine (Megathon X). A homeowner sees how green their home is and compares three retrofit plans, each built for a different objective. They can change the plan and watch the engine recalculate, and inspect where every number comes from.

**Every number on screen comes from the engine.** The browser formats values, draws charts and compares two engine results side by side. It never calculates savings, carbon, scores or rankings.

## Quick start

```bash
npm install
npm run dev            # http://localhost:5173, offline snapshot mode
```

With no backend running, the app uses the **offline engine snapshot** in `public/fixtures/`. This is real output of `scenario_builder.build()` from `feature/engine-core` for the three public demo homes. A banner says so on every page.

### Live backend

```bash
cp .env.example .env.local
# set VITE_DATA_MODE=live, then start the FastAPI app on :8000
npm run dev
```

The dev server proxies `/api` and `/llm` to `VITE_DEV_PROXY_TARGET`. The routes the frontend expects are specified in [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md). If the backend is unreachable, the banner offers a one-click switch back to the snapshot.

| Variable | Default | Meaning |
|---|---|---|
| `VITE_DATA_MODE` | `fixtures` | `fixtures` (offline snapshot) or `live` |
| `VITE_API_BASE_URL` | empty | FastAPI base URL; empty = same origin via the dev proxy |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Dev proxy target for `/api` and `/llm` |

No secrets belong in these variables: everything prefixed `VITE_` is shipped to the browser. LLM keys stay on the backend.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Dev server |
| `npm run typecheck` | `tsc -b` (app, tests, config) |
| `npm run lint` | oxlint |
| `npm test` | Vitest: contract, units, scenario state, transport, full-app integration |
| `npm run build` | Typecheck + production build to `dist/` |
| `npm run preview` | Serve the production build |

## Made for anyone: the guided flow

My Home opens as five short steps, sticky at the top of the page. Each step fits about one screen and ends with a "Next" button:

1. **Your home.**
   - The score in plain words, e.g. "Homes scoring 30–49 are classed poor", from the engine's own bands.
   - Gas, electricity and carbon a year, each marked *benchmark* or *your reading*.
   - What lets the home down, and what we don't know.
   - The tappable blueprint.
   - A location & climate card. Flood and overheating risk show "not checked yet".
2. **Your options.**
   - The engine's three plans in plain words: cost, carbon, gas, and whether electricity goes up.
   - **The budget filters the plans.** Pick "spend now, up to £1k / £5k / £15k" and the engine re-runs its package search with that limit (`packages.search(budget_gbp)`). The three cards become the best plans you can afford, each noting what it would pick without a limit. "Compare with no budget limit" switches back.
   - The plan matching your priority is highlighted.
   - Permission needs for your role and stability ("still the pick in 9 of 10 what-if tests").
   - "Choose this plan" recalculates and moves to step 4.
3. **Try changes.**
   - Add or remove improvements with one button each.
   - "People at home: fewer / as recorded / more", run by the engine through `baseline_scale`.
   - Heat-pump efficiency in plain words, and your meter reading.
   - "What changed" shows the before → after numbers from the two engine results.
4. **Your plan.**
   - Six questions to ask before you start: Can I do it? Can I afford it now? Will it work for me? What if things change? How do I know it's real? What happens after installation?
   - Answered from engine results plus your situation; unknowns are said plainly.
   - A ready-made letter to your landlord or building committee.
   - Save named plans in this browser; reopening one re-runs the engine.
   - Download a decision record (JSON), or print.
5. **Expert details.** Everything below this section, unchanged.

**Your situation** is five optional questions, shown one at a time with big buttons and skippable: role, how long you'll stay, budget now, what matters most, expected changes.
- It never asks for income, employer or bank details.
- Answers are saved only in this browser and change presentation, never the engine's numbers. See `docs/API_CONTRACT.md` → "Situation fields" for how the engine can use them later.

**Help with jargon.** Words like EPC, kWh, CO₂e, heat pump and SCOP are underlined; tap or hover for a plain definition.

**Permissions.** Permission notes are general UK guidance, always marked unverified, and never override the engine's feasibility (which is a hard gate). Method & Evidence → section K lists how each idea from the product-concept documents is covered, and what is not modelled yet (bills, climate hazards, maintenance).

## What is in the app

**My Home → Expert details** (`/home/:homeId?tab=expert`), in eight numbered sections. A sticky **scenario dock** always says whether the numbers on screen are confirmed, recalculating or failed.

1. **Property intelligence.** Identity, headline score, and the most important thing the data cannot tell us. Also the **Retrofit Blueprint**: an architectural elevation (house or flat) with one numbered callout per measure. Callouts are keyboard-operable and toggle the measure; a "not suitable" callout explains why instead.
2. **Score & diagnosis.** Score scale with class bands, missing-data range and after-retrofit marker. Seven sub-score rows (today vs after) with provenance.
3. **Energy & carbon.** Per-fuel savings. Electricity rising after a heat pump is shown as a negative saving, in words and colour. End-use chart, carbon by fuel, property value status.
4. **Retrofit controls.** All seven measures, each with:
   - feasible / needs-verification / not-suitable status, with the engine's reason and any missing inputs;
   - its effect in this plan and on its own;
   - indicative cost, validation status and dependencies.
5. **Retrofit Decision Studio.** The engine's three featured plans side by side, under their literal objective labels, with consistent metric bars, "why it qualifies", conditional flags and sensitivity survival rings. Below them sit a Pareto chart and a matrix of every package the engine searched; any package can be loaded into the lab.
6. **Live Scenario Lab.**
   - Inputs: measure toggles, assumption presets, a meter reading, and natural-language what-ifs when the LLM service is up.
   - Results: a before/after diff of the two engine results, "did the recommendation change?", and a scenario timeline.
7. **Explanation.** LLM text when available and bound to the same scenario ID; otherwise a deterministic template. Includes a template-mode switch.
8. **Decision audit.** Uncertainty kept in three parts (data completeness, model uncertainty, assumption sensitivity), a decision-stability matrix (each sensitivity run × each objective), and the engine's generated audit.

**"Why this number?"** drawers on every major result show inputs and their provenance, method, assumptions, missing data, validation status, limitations, sources, versions and scenario ID.

**Homes Needing Help** (`/homes-needing-help`) is the engine's portfolio: Poor and Very poor homes ranked by improvement potential. It has a summary strip, search, filters, sorting and paging, and links into My Home. It is labelled as an opportunity view, not a credit decision.

**Method & Evidence** (`/method`) covers sections A–J: sources, score formula, catalogue and feasibility rules, NEED-measured vs assumed impacts, and simulator vs NEED combination gaps. Model results, the policy comparison and regret show **Evaluation pending** until real results exist.

## Architecture

```
src/
  app/            App, routes (lazy secondary pages), QueryClient
  api/            schema.ts (zod contract mirroring Pydantic), transport.ts (one client: live | fixtures),
                  errors.ts, config.ts (data mode), queries.ts (TanStack Query hooks), TransportProvider
  hooks/          useScenarioLab (confirmed / draft / in-flight / failure kept separate), useExplanation
  components/     layout, common (provenance, evidence drawer, states), home (hero, blueprint), score,
                  energy, retrofits, packages (studio, matrix, Pareto), whatif (lab, dock), explanation,
                  decision-audit
  pages/          MyHome, HomesNeedingHelp, MethodEvidence, NotFound
  utils/          format (units, signs, missing values), labels, evidence, scenarioDiff, explainTemplate
  styles/         tokens.css (design tokens, light + dark), base.css
  tests/          Vitest suites + helpers (serve public/fixtures through a stubbed fetch)
```

**Scenario state.**

- **Confirmed result, draft and in-flight request are separate.** Each change is debounced and sent with a sequence number and an AbortController. A response is accepted only if it is the latest request and echoes the request that was sent. Then everything swaps at once: previous ← confirmed ← result.
- **Failures keep the last confirmed scenario on screen,** with the failed change named and Retry / Discard actions.

## Offline engine snapshot

`scripts/generate_fixtures.py` regenerates `public/fixtures/` from an engine checkout. It needs Python with `pydantic`, `pandas` and `pyarrow`.

```bash
git archive origin/feature/engine-core | tar -x -C ../engine-core
python scripts/generate_fixtures.py --engine-dir ../engine-core --engine-commit <sha>
```

**How it builds the inputs.** The York parquet is not distributed. The three demo homes are rebuilt from `configs/demo_homes.json` plus a few non-public EPC fields. Those fields are documented in the engine's own `tests/fixtures/hand_calc_demo.py`.

**Parity check.** The script refuses to write unless the engine reproduces the hand-calculated acceptance values (A: 44 → 75 and 3,292 kg CO₂e; B: 61, Moderate; C: unavailable, 1/7).

**What the snapshot contains:**

- every measure combination for each home (default assumptions);
- the assumption presets with the engine's default selection;
- one meter-reading preset for home A;
- the portfolio code run over the three demo homes only;
- the evidence configs.

Anything else returns an explicit "needs the live engine" message.

## Testing

`npm test` runs 62 tests:

- every snapshot file validated against the contract;
- demo-home acceptance values;
- units and sign conventions;
- stale and out-of-order responses, failures, revert and retry in the scenario lab;
- live-transport error mapping (mocked fetch);
- full-app integration on all three demo homes: what-if recalculation, featured plans, meter reading, `fixture_miss`, LLM fallback and scenario-ID binding, evidence drawer, navigation, portfolio and Method & Evidence.

Browser checks (system Chrome via `playwright-core`, not a project dependency) were run by hand: the what-if loop, keyboard operation of the blueprint, the evidence drawer, and no horizontal overflow at 1440 / 1024 / 768 / 375 px on every page.

## Known limitations

- **No backend routes yet.** The live transport is tested against mocked responses only; the engine owner implements `docs/API_CONTRACT.md`.
- **The snapshot covers three demo homes.** Custom meter readings, and assumption changes on a custom selection, need the live engine.
- **The portfolio covers three homes.** In snapshot mode it runs over the demo homes, not all 65,872 York homes. EPC-band and property-type filters wait for those fields.
- **The LLM layer is not connected.** It exists on `feature/llm-layer` but runs on a fake engine (see API_CONTRACT "integration risks"). Until it is wired to the real engine, explanations use the deterministic template.
- **"Gas after" and "electricity after" totals are not printed** until the backend serialises them (the frontend will not add end uses together itself).
