# Project TODOs

- [x] Implement `HomesNeedingHelp.tsx`
- [x] Implement `MethodEvidence.tsx`
- [x] Start the development server (npm run dev)
- [x] Write mid-submission summary for frontend implementation
- [x] Typed contract mirroring the engine's Pydantic schemas (`src/api/schema.ts`, zod)
- [x] One API client with live / offline-snapshot transports (`src/api/transport.ts`)
- [x] Offline snapshot of real engine output for demo homes A/B/C (`scripts/generate_fixtures.py`, parity-checked)
- [x] My Home: hero + Retrofit Blueprint, score, energy & carbon, 7 measures, Decision Studio, Scenario Lab, explanation, decision audit
- [x] Homes Needing Help and Method & Evidence on engine data (pending states where results do not exist)
- [x] Tests (Vitest, 45) + browser checks (loop, keyboard, overflow at 4 widths)
- [x] docs/API_CONTRACT.md for the backend team
- [x] Implement User Personas and enhance overall UI aesthetics and UX.
- [x] Guided 5-step My Home (Your home → Your options → Try changes → Your plan → Expert details), plain language + glossary
- [x] "Your situation" intake (role, stay, budget, priority, changes) — browser-only, presentation-only
- [x] Permission guidance per role (never "confirmed"), six-question plan check, landlord/committee letter
- [x] Saved plans (re-run the engine on open) + downloadable decision record
- [x] Occupancy scenario via engine `baseline_scale` (snapshot covers default set + the 3 featured plans)
- [x] Method & Evidence section K: coverage of the product-concept documents

## Next (depends on other workstreams)
- [ ] Backend: implement `/api/*` routes from docs/API_CONTRACT.md, then run with `VITE_DATA_MODE=live`
- [ ] LLM: wire `configure_engine` to the real engine so `/llm/explain` scenario IDs match `/api/scenario`
- [ ] Backend: serialise EndUses totals; add `rating`/`property_type` to portfolio rows
- [ ] Re-run `scripts/generate_fixtures.py` whenever the engine or configs change (then restart `npm run dev`: Vite caches public/)
- [ ] Backend: accept the optional situation fields in ScenarioRequest (budget, role, horizon, tariff → bills/payback)
