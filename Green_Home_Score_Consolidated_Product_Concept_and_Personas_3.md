# Green Home Score
## Consolidated Product Concept, User Personas, and Day-to-Day Use Cases

**Status:** Consolidated product-discovery document  
**Challenge context:** Lloyds PS2 Green Home Score / Megathon X  
**Scope:** This document combines the outcomes of our discussions. It describes a product vision and proposed capabilities, not a claim that every feature is already implemented.

## 1. Executive summary

Green Home Score is envisioned as a **property-aware, occupant-aware retrofit decision-support system**. It helps users understand a property's energy performance, identify improvements, check physical and legal feasibility, estimate energy/carbon/cost consequences, compare complete retrofit packages, and test whether recommendations remain worthwhile as circumstances change.

The product should answer:

> Given this building, location, ownership situation, intended use, financial constraints, and plausible future changes, which improvements are feasible and worthwhile for this particular decision-maker?

It should not merely rank upgrades by theoretical energy savings. It must expose assumptions, distinguish measured data from estimates, separate verified facts from inferences, and explain when missing information limits confidence.

### Core principles

1. **Property-aware:** construction, floor, orientation, shared walls, roof access, and systems matter.
2. **Occupant-aware:** occupancy, comfort preferences, appliance use, and household changes affect outcomes.
3. **Role-aware:** tenants, owners, landlords, managers, and housing societies have different rights and incentives.
4. **Location-aware:** climate, tariffs, carbon intensity, hazards, costs, incentives, and rules vary by place.
5. **Constraint-first:** known legal, physical, and safety constraints are checked before ranking options.
6. **Lifecycle-aware:** account for moving, sale, vacancy, future occupants, equipment replacement, and other changes.
7. **Transparent:** estimates should have traceable inputs, assumptions, sources, units, and versions.
8. **Robust under uncertainty:** compare plausible futures and identify fragile recommendations.
9. **Privacy-conscious:** collect only information that materially improves the decision.
10. **Evidence-led:** do not claim guaranteed savings, property-value uplift, or legal approval without supporting evidence.

## 2. The problem

A home's energy performance and retrofit value depend on more than the building fabric. Important factors include occupants, intended use, length of stay, local weather, tariffs, building configuration, permissions, budget, appliance changes, installation disruption, maintenance, and unexpected events.

A recommendation that looks optimal today may be unsuitable after a move, a change in tenants, a new appliance, an energy-price shock, or a change in property use. Green Home Score should expose this dependency rather than pretending there is one universally best package.

## 3. Primary users and modes

### Tenant mode
Prioritise lower bills over the tenancy period, reversible or portable measures, comfort, landlord permissions, repairs to raise with the landlord, and avoiding permanent investments whose benefits mostly accrue to the owner.

### Homeowner mode
Consider long-term savings, comfort, reliability, upfront cost, payback, planned sale or inheritance, measure sequencing, technical constraints, and future replacement costs.

### Landlord mode
Consider capital expenditure, compliance, tenant comfort and bills, maintenance, vacancy, tenant turnover, and the distribution of costs and benefits. Do not assume that upgrades automatically justify higher rent or sale value.

### Portfolio landlord mode
Compare multiple properties, prioritise investments, track data and model versions, and avoid misleading comparisons between properties with different data quality or construction.

### Housing-society/shared-building mode
Consider shared roofs, facades, heating, cooling, electrical and common-area systems; collective permissions; resident agreement; cost allocation; and disruption.

### Property/facilities manager mode
Consider equipment uptime, service contracts, maintenance, installation windows, common-area energy use, replacement planning, and post-installation verification.

### Mixed-use/commercial mode
Represent different occupancy hours and end uses, separate meters and costs where applicable, and avoid applying residential assumptions to shops, offices, clinics, workshops, or mixed-use buildings.

## 4. Property intent and lifecycle

A proposed **Property Intent & Ownership Horizon** component should ask why the decision is being made.

### Intended use
- Owner-occupied home.
- Renovating to sell.
- Living there for a few years, then moving.
- Long-term family home.
- Inheritance or transfer to future family members.
- Rental property.
- Commercial or mixed-use property.
- Second home or seasonal property.
- Possible future conversion to another use.
- Unknown or undecided.

### Horizon
- Under 2 years.
- 2–5 years.
- 5–10 years.
- 10+ years.
- Uncertain.

Ownership duration and actual occupancy duration should be separate when they differ. Horizon changes the relevance of payback, disruption, portability, maintenance, and long-term savings.

### Future occupants and lifecycle events
Scenarios may include the same household, a larger or smaller household, different tenants, frequent turnover, commercial use, part-time occupancy, or unknown future occupants. Other events include relocation, sale, inheritance, vacancy, renovation-related temporary relocation, appliance replacement, system failure, roof replacement, change of use, and tariff or regulatory changes.

These are scenarios, not certain predictions.

## 5. Location and climate intelligence

A proposed **Location & Climate Intelligence** component should use the most granular reliable location data available.

- **Cold/damp climates:** heating demand, insulation, draughts, condensation, mould risk, ventilation, moisture management.
- **Hot/humid climates:** cooling demand, solar heat gain, shading, roof insulation, humidity control, air-conditioning efficiency.
- **Hot/dry climates:** shading, roof reflectivity, thermal mass, ventilation timing, cooling efficiency.
- **Climate hazards:** extreme heat, flooding, storms, equipment durability, placement, resilience, and possible insurance implications.

These are context categories, not universal prescriptions. Construction details, orientation, shading, ventilation, and local weather can change the result.

Where reliable, location-sensitive inputs may include weather, tariffs and standing charges, energy-source/grid-carbon intensity, solar potential and export compensation, installation costs, grants and subsidies, local rules, hazards, and contractor lead times. The product must not pretend that a broad postcode reveals a property's exact microclimate.

## 6. Building context and physical feasibility

A proposed **Building Context & Physical Feasibility** component should consider:

### Building types
- Detached or standalone house.
- Semi-detached or attached house.
- Duplex.
- Apartment or flat.
- Housing-society or multi-unit building.
- Mixed-use property.
- Older or heritage property.
- Commercial building.
- Seasonal or intermittently occupied property.

### Relevant characteristics
- Floor and top-, ground-, middle-, corner-, or exposed-unit position.
- Roof access and roof ownership.
- Orientation and window exposure.
- External wall area and shared walls.
- Window type and condition.
- Insulation and construction.
- Heating, cooling, ventilation, and hot-water systems.
- Electrical capacity and existing equipment.
- Shared versus private infrastructure.
- Floor area, layout, and usage zones.
- Moisture, condensation, and ventilation concerns.

Floor position is a clue, not a fixed rule. Actual performance depends on fabric, adjacent spaces, orientation, and surrounding conditions.

Feasibility statuses may be: **physically feasible**, **feasible after enabling work**, **conditional on inspection/information**, **not feasible due to a known constraint**, or **unverified**. Missing information must not silently become confirmation.

## 7. Regulatory and permission feasibility

A proposed **Regulatory & Permission Feasibility** component should be a meaningful gate, not a disclaimer.

| Intervention | Potential constraint |
|---|---|
| Rooftop solar | Roof rights, landlord/society consent, grid connection, local installation rules |
| Heat pump | Outdoor-unit location, noise, electrical capacity, planning/building rules |
| Window replacement | Facade restrictions, conservation requirements, landlord consent |
| External wall insulation | Ownership, shared walls, planning, moisture and construction considerations |
| EV charger | Parking rights, electrical capacity, building approval |
| Smart controls | Compatibility and permission to modify existing systems |

Actual rules depend on jurisdiction, property, ownership arrangement, and installation.

Statuses:
1. **Confirmed feasible:** relevant requirements checked against reliable evidence.
2. **Conditional:** feasible if specified permissions or technical conditions are met.
3. **Unverified:** insufficient information to determine eligibility.
4. **Not feasible:** a known constraint rules it out.

Unverified does not mean prohibited; technically feasible does not mean legally approved. Legal, engineering, or installation confirmation may still be required. Rules and incentives should be dated, jurisdiction-specific, and linked to sources where possible.

## 8. Personal financial resilience and privacy

A proposed **Personal Financial Resilience** component can improve relevance without becoming a credit-scoring system.

Optional inputs:
- Upfront spending limit and comfortable monthly spending.
- Preference for upfront payment versus ongoing payments.
- Financial buffer the user wants to preserve.
- Expected time in the property.
- Willingness to accept uncertainty.
- Preference to avoid long payback periods or ongoing commitments.
- Anticipated changes in employment, household, or location, if the user chooses to disclose them.
- Access to grants/subsidies, where eligibility can be verified.

Employment stability should be represented through optional user-provided scenarios, not inferred from address, occupation, or indirect signals. Detailed salary, employer identity, bank balances, and employment records should not be necessary for ordinary recommendations.

Distinguish total project cost, upfront cash requirement, financing, operating and maintenance costs, expected bill savings, payback, duration of benefit, and liquidity constraints. Someone may be able to afford a project in total but not this year.

Privacy principles:
- Collect only inputs that materially affect the decision.
- Permit ranges and user-selected scenarios.
- Explain how missing information affects confidence.
- Protect household members' private inputs.
- Keep this separate from creditworthiness assessment.
- Do not automatically recommend borrowing because financing exists.

## 9. Occupancy, appliance use, and changing demand

A proposed **Occupancy & Usage Scenarios** component should separate:
- **Physical performance:** building/system efficiency under defined conditions.
- **Occupant-dependent consumption:** energy people and appliances use.
- **Environmental impact:** emissions associated with consumption and energy sources.
- **Financial outcome:** bills and savings under usage and tariff assumptions.

An efficient home can still have high bills if occupants use substantially more energy.

Scenarios may include current occupants, a larger family, different tenants, part-time occupancy, temporary vacancy, commercial use, or different heating/cooling/hot-water habits.

Appliance and load changes may include replacing a refrigerator, changing cooking equipment, adding air conditioning or EV charging, adding electronics, changing operating hours, or replacing heating/hot-water systems. Avoid double-counting: if a scenario already reduces an appliance's consumption, a second adjustment must not claim the same saving.

Vacancy does not mean zero energy use. Standing charges, background loads, security, moisture control, and climate-specific protection may remain. Temporary moves can change occupancy-related consumption, solar self-consumption, maintenance needs, and the user's ability to benefit from a permanent upgrade.

## 10. Robust retrofit planning

A proposed **Robust Retrofit Planning** component compares complete packages across plausible futures.

Three levels:
1. **User-selected scenarios:** the user changes assumptions and sees recalculated outcomes.
2. **Lifecycle planning:** expected changes have approximate timing, such as moving, appliance replacement, or tenant turnover.
3. **Robust decision-making:** options are compared across uncertain futures, fragile recommendations are identified, and trade-offs are quantified.

Scenarios may include expected occupancy, higher electricity demand, vacancy, early sale, different tenants, energy-price changes, grid-carbon changes, extreme weather, higher installation/maintenance costs, delayed installation, or unavailable equipment.

Questions:
- What is the expected outcome under the selected assumptions?
- What happens under favourable and plausible stress conditions?
- Which assumptions drive the result?
- Does package ranking change across scenarios?
- Which options remain feasible?
- What trade-off exists between expected benefit, cost, and robustness?

Do not always choose the most conservative option. Robustness may cost more; users may rationally accept uncertainty. The product cannot predict every black-swan event, but it can test plausible shocks and identify fragile decisions.

## 11. Original retrofit decision engine

The expanded concept retains a transparent, assumption-driven simulator.

Core capabilities:
- Establish a baseline.
- Distinguish measured inputs from modelled estimates and defaults.
- Check technical, legal, permission, and user constraints.
- Simulate individual measures and interactions.
- Compare complete retrofit packages.
- Show energy, carbon, cost, and other objectives separately.
- Explain assumptions, uncertainty, and trade-offs.
- Let users challenge assumptions and run scenarios.
- Preserve the basis of the decision for later comparison.

The original plan considered exhaustive combinations of a small measure catalogue, a Pareto frontier, and three featured packages:
- Lowest-cost package meeting a specified minimum emissions-saving threshold.
- Package with the largest estimated carbon saving.
- Best estimated carbon saving per pound subject to a minimum saving threshold.

The carbon-per-pound package must not be called “best overall.” The objective must be explicit, and zero-cost baseline cases need defined handling.

The original policy comparison included a fixed checklist, greedy marginal-carbon-saving approach, and exhaustive package search. Reports should separate carbon regret from carbon-per-pound regret, feasibility violations, sensitivity, and runtime. Results are relative to the simulator and test cases, not proof of real-world optimality.

Model and explanation integrity:
- Keep a model only if it beats a meaningful benchmark.
- Never call modelled consumption measured.
- Separate data uncertainty, model uncertainty, and sensitivity.
- LLM explanations must not invent numbers.
- Use structured claims, unit/sign checks, scenario identifiers, and template fallbacks where appropriate.
- Property-value uplift is not causal evidence without an appropriate research design.
- Missing data must remain visible rather than silently becoming confident predictions.


## 12. Detailed user personas (1–24)

These are illustrative design profiles, not statistical claims about prevalence.

### 1. The short-term renter
**Situation:** Expects to move within 12–24 months.  
**Needs:** Inexpensive, reversible improvements that pay back quickly.  
**Risks:** Permanent upgrades may mostly benefit the landlord; payback may exceed the tenancy.  
**Product implications:** Calculate benefits over expected occupancy; distinguish portable from attached measures; show permissions; compare low-cost actions with landlord-requested work.

### 2. The tenant with an unresponsive landlord
**Situation:** Faces inefficient windows, poor ventilation, or an unreliable heating system.  
**Needs:** Know what they can do independently and what requires landlord action.  
**Risks:** The system recommends unauthorised changes.  
**Product implications:** Provide a permission-aware action plan; distinguish tenant actions, landlord repairs, and shared decisions; identify facts needing confirmation.

### 3. The energy-burdened tenant
**Situation:** Bills consume a large share of household budget.  
**Needs:** Immediate bill relief, low-cost measures, and assistance information.  
**Risks:** A technically attractive upgrade is unaffordable upfront.  
**Product implications:** Prioritise cash required and near-term benefit; verify assistance eligibility; distinguish lifetime net savings from short-term affordability.

### 4. The student or shared-house renter
**Situation:** Several occupants share rooms, bills, and appliances.  
**Needs:** Simple actions and fair allocation of costs and savings.  
**Risks:** The payer and beneficiary differ; shared bills cause disputes.  
**Product implications:** Represent shared costs and occupants; support simple usage schedules; protect individual data.

### 5. The older tenant or person with limited mobility
**Situation:** Comfort, accessibility, and safe indoor conditions matter.  
**Needs:** Easy-to-use systems and manageable installation disruption.  
**Risks:** An energy-saving action makes the home uncomfortable or hard to operate.  
**Product implications:** Include comfort and usability; consider access and disruption; require qualified advice for health- or safety-critical issues.

### 6. The first-time homeowner
**Situation:** Wants to improve a property without expensive mistakes.  
**Needs:** Guidance despite incomplete building knowledge.  
**Risks:** Incorrect assumptions about insulation, boiler, wiring, or ownership.  
**Product implications:** Ask understandable questions; show inferred versus verified facts; allow unknowns; identify when inspection is needed.

### 7. The long-term family homeowner
**Situation:** Plans to stay 10–20 years and values comfort, bills, and reliability.  
**Needs:** Long-term planning and sensible sequencing.  
**Risks:** Installing everything at once duplicates work or wastes capital.  
**Product implications:** Compare staged pathways; model dependencies; include maintenance and replacement cycles.

### 8. The owner preparing to sell
**Situation:** Wants to know which upgrades are worth doing before listing.  
**Needs:** A short-horizon investment view.  
**Risks:** Long-term savings accrue to the buyer; resale uplift may be unproven.  
**Product implications:** Separate seller costs from buyer benefits; support market claims with evidence; show effect of sale timing.

### 9. The multigenerational household
**Situation:** Changing occupancy, varied comfort preferences, potentially high hot-water/cooling demand.  
**Needs:** Recommendations reflecting different schedules and room use.  
**Risks:** One average profile hides meaningful differences.  
**Product implications:** Support household-size and schedule scenarios; represent different comfort needs; avoid treating occupancy as a precise energy predictor.

### 10. The financially cautious homeowner
**Situation:** Has savings but wants to preserve an emergency fund and avoid long payback.  
**Needs:** Recommendations compatible with liquidity and timing.  
**Risks:** Total wealth is mistaken for cash available now.  
**Product implications:** Model upfront cost, timing, optional cash buffer, and payback preference; show trade-offs instead of a single affordability judgement.

### 11. The early adopter
**Situation:** Wants solar, batteries, heat pumps, smart controls, or EV charging.  
**Needs:** Compatibility and expansion planning.  
**Risks:** Electrical capacity, warranties, replacement cycles, and interactions are overlooked.  
**Product implications:** Check enabling requirements; model interactions; include warranties and maintenance where supported.

### 12. The owner of an older or heritage property
**Situation:** Unusual construction, moisture risks, conservation rules, or expensive repairs.  
**Needs:** Property-specific recommendations.  
**Risks:** Standard assumptions are inappropriate or unsafe.  
**Product implications:** Flag uncertainty; avoid unsupported insulation claims; require qualified assessment when needed.

### 13. The small private landlord
**Situation:** Manages capital expenditure, compliance, and rental attractiveness.  
**Needs:** Investment and maintenance view.  
**Risks:** Tenant benefits, landlord costs, and possible rent effects are conflated.  
**Product implications:** Show landlord and tenant outcomes separately; verify rules; do not assume upgrades permit higher rent.

### 14. The portfolio landlord
**Situation:** Owns properties with different types, locations, and performance.  
**Needs:** Consistent comparisons and portfolio prioritisation.  
**Risks:** Different data quality makes naive rankings misleading.  
**Product implications:** Track model/data versions; normalise comparisons where appropriate; prioritise urgency, feasibility, and benefit.

### 15. The housing-society committee
**Situation:** Coordinates residents, shared budgets, permissions, and contractors.  
**Needs:** Shared-building assessment and cost allocation.  
**Risks:** Disagreement over payment, benefits, and roof/facade control.  
**Product implications:** Separate unit and building outcomes; model shared infrastructure and approvals; explain allocation assumptions.

### 16. The building or facilities manager
**Situation:** Responsible for uptime, common-area energy, and maintenance.  
**Needs:** Operationally feasible upgrades.  
**Risks:** Downtime and maintenance outweigh theoretical savings.  
**Product implications:** Include maintenance and uptime; account for installation windows; support post-installation verification.

### 17. The mixed-use property owner
**Situation:** Residential and commercial areas have different schedules and demand.  
**Needs:** Separate use profiles and cost allocation.  
**Risks:** Residential assumptions are applied to commercial space.  
**Product implications:** Support different schedules/end uses; distinguish meters and loads; check use-specific rules.

### 18. The person expecting relocation
**Situation:** May change jobs, move cities, or leave temporarily.  
**Needs:** Recommendations accounting for changing occupancy and ownership.  
**Risks:** The user is assumed to remain for the upgrade's technical lifetime.  
**Product implications:** Separate ownership and occupancy duration; test early departure; identify portable equipment.

### 19. The owner with intermittent occupancy
**Situation:** Uses a second home seasonally or leaves it vacant.  
**Needs:** Efficient operation and property protection.  
**Risks:** Vacancy is treated as zero energy use.  
**Product implications:** Model background loads and standing charges; consider moisture/security/protection; reassess solar self-consumption.

### 20. The homeowner facing urgent repairs
**Situation:** Failed boiler, damaged roof, electrical fault, or water ingress.  
**Needs:** Safe, timely repair or replacement.  
**Risks:** Long-term optimisation delays essential work.  
**Product implications:** Separate urgent repair from elective retrofit; respect safety and timing; compare viable replacements.

### 21. The climate-vulnerable household
**Situation:** Faces extreme heat, flooding, storms, or unreliable energy.  
**Needs:** Comfort, safety, resilience.  
**Risks:** Average-cost solution performs poorly during extremes.  
**Product implications:** Stress-test local hazards; consider safe indoor conditions and continuity of essential services; distinguish hazard data from engineering conclusions.

### 22. The homeowner comparing contractor quotes
**Situation:** Has estimates with different specifications, warranties, and exclusions.  
**Needs:** Fair like-for-like comparison.  
**Risks:** Cheap quote omits necessary work or uses different equipment.  
**Product implications:** Compare scope, equipment, installation, exclusions, warranties, and ongoing costs; flag missing information.

### 23. The smart-home and appliance upgrader
**Situation:** Frequently adds devices, replaces appliances, or changes usage.  
**Needs:** Updated estimates and compatibility checks.  
**Risks:** Baseline becomes stale; savings are double-counted.  
**Product implications:** Allow load updates; track assumptions; prevent overlapping savings claims.

### 24. The family planning inheritance or ownership change
**Situation:** Maintains a property for future occupants with different needs.  
**Needs:** Maintainable systems, clear records, future compatibility.  
**Risks:** Next owner cannot understand or operate the installation.  
**Product implications:** Preserve decision/installation records; document maintenance and replacement; consider future use scenarios.


## 13. Cross-cutting patterns (25–39)

These patterns affect multiple personas and can make a recommendation fail even when the user profile is understood.

### 25. The bill does not match the model
**Scenario:** Estimated bill is £120/month but actual bill is £190.  
**Why it matters:** Tariffs, standing charges, billing periods, estimated readings, occupancy, and appliances can explain the gap.  
**Product implications:** Separate energy consumption from bill estimates; compare actual bills when provided; investigate discrepancies rather than silently recalibrating.

### 26. Comfort matters more than minimum consumption
**Scenario:** Better insulation leads occupants to keep the home warmer or cooler.  
**Why it matters:** Behaviour changes can reduce realised savings, a phenomenon often called the rebound effect.  
**Product implications:** Separate fixed-comfort and changed-comfort scenarios; do not present engineering savings as guaranteed bills savings.

### 27. Seasonal and daily usage patterns
**Scenario:** The home is empty during work hours, occupied on weekends, and uses substantial cooling in summer.  
**Why it matters:** Annual averages conceal peaks and time-of-use tariffs.  
**Product implications:** Support schedules; add hourly modelling only when justified.

### 28. Property data is wrong or outdated
**Scenario:** An EPC lists a boiler that was replaced two years ago.  
**Why it matters:** Correct calculations on incorrect inputs are still wrong.  
**Product implications:** Display source and age; allow corrections; distinguish verified, inferred, and user-provided data; recalculate after edits.

### 29. Retrofit measures depend on each other
**Scenario:** A heat pump is installed before the heating system and building fabric are assessed.  
**Why it matters:** Measures may require enabling work or a particular sequence.  
**Product implications:** Represent dependencies; compare pathways, not only independent measures; avoid double-counting.

### 30. The upgrade is installed but not maintained
**Scenario:** Filters are not replaced, controls are misconfigured, or performance declines.  
**Why it matters:** Real performance changes and maintenance costs money.  
**Product implications:** Include maintenance, replacement costs, and warranties where supported; model degradation only with evidence; allow verification.

### 31. Installer or equipment unavailable
**Scenario:** Installers are booked, equipment is unavailable, or electrical work must happen first.  
**Why it matters:** A theoretically optimal package may not be actionable.  
**Product implications:** Eventually account for lead times and alternatives; treat availability as time-sensitive sourced data; never invent current stock.

### 32. Installation disruption makes an option impractical
**Scenario:** Work requires temporary relocation, blocks access, or interrupts heating/hot water.  
**Why it matters:** Installation cost is not the only cost.  
**Product implications:** Show duration/disruption where known; consider temporary relocation and staged work.

### 33. Energy supply or electrical infrastructure is constrained
**Scenario:** Limited electrical capacity, unreliable power, shared heating, or export restrictions.  
**Why it matters:** Equipment ratings do not prove an installation can operate as intended.  
**Product implications:** Check capacity, connection requirements, compatibility, and outage behaviour where relevant; require inspection when needed.

### 34. Incentives or regulations change
**Scenario:** A grant expires, eligibility changes, or new requirements apply.  
**Why it matters:** Advice can become legally or financially outdated.  
**Product implications:** Date-stamp rules and incentives; identify jurisdiction and sources; distinguish current verified information from stale or unverified data.

### 35. Household members disagree
**Scenario:** One person wants comfort, another lower bills, another controls the budget.  
**Why it matters:** There may be no single shared objective.  
**Product implications:** Support multiple priorities where useful; make objectives explicit; distinguish committee decisions from individual preferences.

### 36. A green upgrade creates a safety/building problem
**Scenario:** Insulation is added without moisture management or equipment is installed unsafely.  
**Why it matters:** Carbon savings cannot compensate for unsafe conditions or building damage.  
**Product implications:** Safety and building-physics constraints are hard gates; require qualified assessment where needed.

### 37. The user can afford the upgrade but not the timing
**Scenario:** A £10,000 project is affordable in principle but the cash is needed for essential expenses this year.  
**Why it matters:** Total affordability, monthly affordability, and available cash today differ.  
**Product implications:** Model upfront cost, payment timing, ongoing costs, and optional financial buffer; explain financing assumptions without implying borrowing is always beneficial.

### 38. The user changes their mind
**Scenario:** A tenant decides to move, solar is postponed, or the budget changes after quotes arrive.  
**Why it matters:** The original recommendation may no longer fit.  
**Product implications:** Save scenarios; allow editable assumptions; version comparisons; explain what changed and why the ranking changed.

### 39. The user does not want to share sensitive information
**Scenario:** A user wants personalised advice without sharing salary, employer, exact bills, or occupancy schedules.  
**Why it matters:** Excessive collection creates privacy risk and friction.  
**Product implications:** Collect minimum necessary data; accept ranges and scenarios; explain how missing data affects confidence; protect private household inputs.


## 14. Further lifecycle and operational patterns

- **Changing energy prices:** compare tariffs and future price assumptions instead of treating today's prices as permanent.
- **Changing carbon intensity:** distinguish energy savings from emissions savings as the grid changes.
- **Extreme weather:** stress-test locally relevant hazards.
- **Equipment end-of-life:** coordinate upgrades with replacement cycles for boilers, appliances, windows, and roofs.
- **Existing financial commitments:** let users account for ongoing payments without demanding detailed records.
- **Insurance and warranties:** flag possible implications and the need to verify coverage with the provider.
- **Neighbour/shared-wall effects:** account for structures, noise, access, permissions, and cross-property benefits.
- **Actual versus promised performance:** compare measured outcomes with estimates while accounting for weather and occupancy.
- **Multiple occupants and privacy:** protect individual usage and financial inputs.
- **Accessibility and language:** provide understandable explanations and alternative input methods.
- **Local service ecosystem:** distinguish locally supportable work from work requiring unavailable expertise.
- **Moving equipment between homes:** identify portable equipment and whether moving it is economical or permitted.

## 15. The lifecycle of a recommendation

Each recommendation should answer six questions:

1. **Can I do it?** Physical, legal, technical, and permission feasibility.
2. **Can I afford it now?** Upfront cost, timing, financing, and alternatives.
3. **Will it work for my circumstances?** Climate, occupancy, building type, and usage.
4. **What happens if things change?** Relocation, occupants, appliances, tariffs, and unexpected events.
5. **How do I know the result is real?** Provenance, uncertainty, measured outcomes, and verification.
6. **What happens after installation?** Maintenance, replacement, future compatibility, and changing regulations.

## 16. Prioritisation

### Essential foundation
- Property and user-role context.
- Explicit assumptions and provenance.
- Tenant versus owner distinctions.
- Hard physical, legal, permission, and safety constraints.
- Transparent energy, carbon, and cost calculations.
- Missing-data handling.
- Clear uncertainty and sensitivity.
- A working vertical slice from property inputs to an explainable package comparison.

### Next layer
- Ownership and occupancy horizon.
- Upfront budget and timing constraints.
- Seasonal usage scenarios.
- Measure dependencies and staged upgrades.
- Maintenance and replacement assumptions.
- A small set of occupant, vacancy, appliance, and energy-price scenarios.
- User-editable assumptions and versioned comparisons.

### Later expansion
- Live contractor availability.
- Portfolio management.
- Automated bill reconciliation.
- Detailed hourly simulation.
- Ongoing performance monitoring.
- Financing integrations.
- Multi-party coordination.
- Broad international coverage.
- Advanced climate-risk and lifecycle optimisation.

### Lloyds / UK challenge scope
The current challenge direction is anchored to UK property data, geography, and rules. The architecture may support more regions later, but the first release should not pretend to validate UK EPC recommendations, Indian apartment-society rules, and several countries' incentives at once. A narrow, verifiable product is more credible than an enormous feature catalogue.

## 17. The decision record

A **versioned decision record** is a strong foundation. It preserves the basis of a recommendation so it can be revisited after a move, appliance change, tariff change, new quote, or failed installation.

Record, where applicable:
- Property reference, user role, intended use, and ownership/occupancy horizon.
- Property characteristics and sources.
- Current usage and appliance assumptions.
- Location and climate inputs.
- Legal and technical constraints.
- User objectives and budget constraints.
- Selected measures and their order.
- Estimated energy, carbon, cost, and other outcomes.
- Data sources and dates.
- Model, catalogue, emissions-factor, and assumption versions.
- Missing data and uncertainty.
- Scenario definitions and results.
- Reasons measures were excluded or marked conditional.
- User edits and changes between scenarios.
- Actual post-installation results when provided.

A stable scenario identifier should be based on canonicalised inputs affecting the calculation and the relevant model/catalogue/assumption versions. Store a timestamp separately unless it affects the calculation.

The record should answer: What was recommended? Which facts and assumptions produced it? What changed? Why did the ranking change? Which outcomes were estimated versus measured? Which permissions or technical checks remain unresolved?

## 18. Boundaries and non-goals

- Not a substitute for required engineering inspections, legal advice, or installation approvals.
- Do not imply measured energy data exists for every individual EPC property.
- Never label modelled consumption as measured.
- Do not claim causal property-value uplift without appropriate evidence.
- Do not assume tenants can modify the property.
- Do not treat missing data as confirmed positive or negative evidence.
- Do not claim to predict every black-swan event.
- Do not infer financial vulnerability or employment stability from indirect signals.
- Do not let carbon optimisation override safety, legal, or physical constraints.
- Do not assume one objective fits every occupant, owner, landlord, or building.
- More features are not proof of better recommendations.

## 19. Consolidated product definition

**Green Home Score is a transparent, property-aware and occupant-aware retrofit decision-support system. It evaluates a home's characteristics and energy performance, identifies feasible improvements, estimates energy, carbon, and financial consequences, compares complete retrofit packages, and tests how recommendations change with ownership goals, occupancy, location, climate, permissions, budgets, appliances, and plausible future events. It records the evidence and assumptions behind each decision so users can understand, challenge, and revisit the recommendation over the life of the property.**

The core differentiation is not the number of inputs or interface features. It is the ability to explain why a recommendation fits a particular decision-maker and property, what could invalidate it, which facts remain uncertain, and how the decision changes when circumstances change.

## 20. Open product questions

These are unresolved decisions, not silently settled in this document:

1. Should the first release optimise primarily for the occupant, property owner, or building?
2. Which user roles should be fully supported first?
3. Which climate/location variables can be sourced reliably within the challenge scope?
4. Which regulatory checks can be verified, and which must remain user-confirmed?
5. Which financial inputs improve recommendations without unnecessary privacy risk?
6. Which lifecycle scenarios provide the greatest decision value for the least modelling complexity?
7. What evidence is sufficient to report actual savings, performance improvement, or property-value effects?
8. When should the system request more data versus explicitly report uncertainty?
9. How should it compare conflicting objectives such as minimum carbon, minimum upfront cost, comfort, and robustness?
10. What is the smallest end-to-end vertical slice that demonstrates a defensible, useful recommendation?

---

*End of consolidated product concept.*
