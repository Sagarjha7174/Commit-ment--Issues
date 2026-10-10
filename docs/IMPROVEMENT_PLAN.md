# Improvement plan (engine-v3)

Based on the engine review of 2026-10-10. Every item below was found by running the engine (evidence column), not by
reading alone. Status: ✅ implemented on `feature/engine-improvements`, 🔧 implemented but needs `make engine-cal` on
the data machine to switch on, ⏸ deferred (reason given).

## Phase A: correctness (things the engine currently gets wrong)

| # | Problem | Evidence | Change | Decision | Status |
|---|---|---|---|---|---|
| A1 | PV saving scales with heat-pump electricity | Demo A PV: 415 kWh alone, 904 kWh after a heat pump (2.2x), same panels | PV % applies to the home's baseline electricity (before any retrofit), capped at current import | D19 | ✅ |
| A2 | Loft insulation offered for flat roofs, rooms in roof, rafter-insulated and thatched roofs ("High") | rule test: all returned feasible / High | roof type parsed from the EPC description: flat -> infeasible; roof room / rafters / thatched / unknown type -> needs_verification; loft depth (mm) drives suitability; >= 270 mm -> infeasible | D20 | ✅ |
| A3 | Energy-intensity sawtooth inside a NEED floor-area band | same kWh: 151 m² -> 3.3 score pts, 199 m² -> 10.6 | benchmark scaled within its band by (area / band reference area)^β, β fitted on NEED across bands; score params refrozen (v2) on scaled baselines | D21 | 🔧 |
| A4 | Missing part scored 50 | PV unrecorded = +5.0 points vs PV none; 5,735 train homes | missing part scored at the train mean of that part (renewables split by EPC age); range stays 0-100 | D22 | 🔧 (50 until built) |
| A5 | Segment effects added although EPC band, age and type are correlated (D15) | solid wall, pre-1919 mid-terrace E: 2.8% vs headline 17.3% | default: region + the largest single non-region adjustment ("max" rule); with data: backfitted additive effects whose York-weighted marginals match the NEED segment medians | D15 rev. | ✅ max rule, 🔧 backfit |
| A6 | Partial glazing priced as a full replacement | demo A (87% double): 210 kWh/yr for £4,900 | cost x single-glazed share | D23 | ✅ |
| A7 | Heat-pump SCOP 3.0 above UK field evidence | Electrification of Heat: median SPF 2.80, cold-day 2.44 | SCOP low/mid/high = 2.44 / 2.80 / 3.5 (engine_params overrides catalogue) | D24 | ✅ |
| A8 | Thermostat saving ignores existing controls | 672 kWh for none, timer and full | none -> brief high (10%), timer -> mid (7.5%), full -> low (5%); sensitivity still shifts one level | D25 | ✅ |
| A9 | No planning flag for pre-1919 homes (York conservation areas) | n/a | reason text asks to check conservation-area / listed status for solid wall and PV on pre-1919 homes | D20 | ✅ |

## Phase B: money (what a customer decides on)

| # | Addition | Design | Decision | Status |
|---|---|---|---|---|
| B1 | Annual bills per fuel | `configs/energy_prices.json` (Ofgem cap 1 Oct - 31 Dec 2026, Direct Debit): electricity 26.32p/kWh + 54.83p/day, gas 7.97p/kWh + 29.68p/day. Bill = unit costs + standing charges; gas standing charge removed only if no gas is left. PV export not credited (conservative). Price what-ifs via `Assumptions.gas_price_p` / `elec_price_p` (e.g. a heat-pump tariff) | D26 | ✅ |
| B2 | Grants | `configs/grants.json`: Boiler Upgrade Scheme £7,500 for air-source heat pumps; £9,000 for off-gas homes for applications 21 Jul 2026 - 31 Mar 2027; evaluated at a fixed `as_of` date so results stay reproducible. Net cost = gross - grants; package selection uses net cost (`Assumptions.apply_grants`, default on); "no grants" sensitivity run | D27 | ✅ |
| B3 | Payback and finance | simple payback = net cost / annual bill saving (none if the bill does not fall); monthly repayment at an illustrative APR and term (`configs/finance.json`, not a Lloyds offer) vs monthly bill saving | D27 | ✅ |
| B4 | Costs scaled by home size | cost x (floor area / York reference area)^γ per measure (loft 1.0, glazing 1.0, walls 0.75, heat pump 0.3, PV/thermostat 0), clamped 0.5-2.0; γ values are assumptions | D23 | 🔧 (needs York reference area) |
| B5 | Lifetime carbon with projected grid factors | needs the DESNZ Green Book data tables (only 2040 = 0.015 and 2050 = 0.002 kg/kWh long-run factors found, on a different basis from the 2026 reporting factor) | n/a | ⏸ until the official tables are downloaded |

## Phase C: method

| # | Upgrade | Design | Decision | Status |
|---|---|---|---|---|
| C1 | Uncertainty ranges | Monte Carlo over model inputs for this home: headline impact (triangular low/mid/high), segment adjustment (empirical-Bayes posterior sd), brief ranges (uniform), SCOP (triangular 2.44/2.80/3.5), boiler efficiency (±0.05), space/water split (0.65-0.85), baseline per fuel (lognormal from NEED cell IQR, when calibrated). Deterministic seed from the scenario id. Reports P10/P50/P90 of savings, carbon and bill, P(carbon cut >= 10%), P(bill falls). NEED household spread is shown per measure as context, not compounded. `ScenarioRequest.include_uncertainty` | D28 | ✅ |
| C2 | Portfolio ranking | per flagged home: fabric/controls-only potential, with-heat-pump potential, net cost, bill saving, £ per tonne; `rank_by` = improvement_potential (brief default) / fabric_potential / carbon_per_pound | D29 | ✅ |

## Phase D: deferred (not algorithm fixes)
- **Post-retrofit SAP model** (parked ML branch): fixes "EPC not re-assessed" in the after-score and unlocks the value model.
- **Property value model**, **energy model**, **recommender** (ML 20%), **LLM layer** (15%), **API + dashboard**.
- **Planning data**: City of York conservation-area / listed-building layers would turn A9's note into a rule.
- **Lifetime carbon** (B5).

## Data-machine steps (after pulling this branch)
```bash
make engine-cal     # A3, A4, A5 backfit, B4 reference area, C1 baseline spread; refreezes score params v2
make elec-split     # D16 electric heating split
.venv/bin/python tests/fixtures/hand_calc_demo.py
make test && make validate-sim && make score
git add configs/ && git commit -m "Engine calibration from York/NEED data" && git push
```
