Yes. And this changes Green Home Score from a retrofit calculator into a much more complete housing decision-support system. It could work for homeowners, tenants, landlords, and property managers, while accounting for the fact that a technically excellent retrofit can be financially impractical, legally prohibited, physically unsuitable, or simply irrelevant to the person living there.

The key is to stop treating the property as just a building. We need to understand four things together:

- The building: What can physically be improved?
- The location: What does the climate demand, and what local rules apply?
- The person: Who pays, who benefits, how long will they stay, and what can they afford?
- The decision: Which improvements are feasible, worthwhile, and resilient to changes in circumstances?

Let's map out what that would mean.

## 1. Support tenants as first-class users

A tenant and a homeowner can occupy the exact same property but have completely different retrofit options.

[No heat in your rental? Here's who to contact](https://images.openai.com/static-rsc-4/aLj-c_KnTyRyiLtWp3dyz5Kiz0TarcnAqJoZUl1JZbIGBqwDimJZzzRIPawAtUOwYMkONhsunp35njoGhP3kIYGq4mL_4ZdjKAD6wchSNxBaPGiY45Gm1I3eFbccVouxGSIwhv7x10fWItToI6m4KpIxMByp1ui2eWPzRIHteec?purpose=inline)

Tenant mode

The system prioritises lower bills, comfort, reversible improvements, landlord permissions, portability, and the expected length of the tenancy.

Examples: draught-proofing where permitted, efficient lighting, smart heating controls, and identifying inefficient appliances.

[Property inspections | MCM Housing](https://images.openai.com/static-rsc-4/e5_nsSrOGgty1334XIVJuf9Ld8GW-1ffEoHEOmEPowNCQ1fJSrBLPXac8cIQOhvuf7UP3As90o7UarK8oiT1xTtS1WJ_0AzEU0JGzFMVBXkj1Jzovb5UJrCaCcbla1waiCDS--72Zrl1sjpFTFjbDngVbUoxwrMAqpeehMG9TdQ?purpose=inline)

Owner or landlord mode

The system can consider insulation, heating-system replacement, solar panels, long-term maintenance, property value, rental attractiveness, and regulatory obligations.

[Čime se bavi profesionalni upravnik zgrade? | SrbijaSpace](https://images.openai.com/static-rsc-4/V8_pchwVrOPS-0o5J5ZwA7MjYN3Do_6OQ7LccWeL35rvqPjeTeOLmZWq3b4EJvZpCtVRhu-8a9Jelfo395xLubb0v28sLOP-dHrwUqmglbIdnPkeEmWEqQqvRYWMs2R7VuUi3RE28R4qC3sMH0PsxtpnlOVk85BJ4Ax28t1Bm7k?purpose=inline)

Property manager or housing society mode

The system evaluates shared infrastructure, common-area energy use, roof access, collective installations, permissions, and costs distributed across multiple households.

The most interesting tenant-specific problem is the split incentive: the landlord pays for a permanent improvement, but the tenant receives much of the energy-bill benefit. A tenant might also pay for an improvement they cannot take with them when they move.

We should therefore calculate outcomes separately for the tenant, landlord, and property where relevant. A package that benefits the building overall may still be a bad financial decision for the person paying for it.

## 2. Climate and geography should change the recommendation

A retrofit that makes sense in a cold, damp climate may be a poor investment in a hot, humid one. The system needs a Location & Climate Intelligence component.

[Deposit Protection UK 2026: DPS, TDS, mydeposits | LetCompliance](https://images.openai.com/static-rsc-4/M6Qg7MQztd_BF1LYvL-0rp5OcogMttWbQZgMbI0UfH0wHUjtl9g1MQS9rMRfGnFsx5Wek2kzLoNk-sP6BJPsJwClPIQuh0bcabh4iaMfcLELa0_sWMeF2P166yOEX_k3nCMidUHW9A5ASifRiiBvQwVgue5EzKDGN9TKoAG_OKA?purpose=inline)

Cold and damp climates

Heating demand, insulation, draughts, condensation, ventilation, and mould risk. Insulation recommendations must account for moisture management.

[Flats for Sale in Anantha Vayun Meadows, Sainikpuri Hyderabad : Resale Flats in Anantha Vayun Meadows Hyderabad](https://images.openai.com/static-rsc-4/h2hncSoXboeeSEKpa4F0kO2W0gWmM3XpOkJ449h7zDGE8sBuNzF5Y1_ZL7Vcd-Ky-O6rQDt2keuGfor7efvCDJ3ekjMwAIx-wjaJoZPbMfuFKI0IxEaXb96LAnmQtyNLG4_05g9MtqoP9aXwYrEeMrmU2kS2fnRqCSVJ3nARSZQ?purpose=inline)

Hot and humid climates

Cooling loads, solar heat gain, shading, roof insulation, humidity control, and air-conditioning efficiency.

[How Much Do Solar Panels Cost in Arizona? (2026)](https://images.openai.com/static-rsc-4/jkRe1MJYtRAkUQK2vBxYUBUoQqSjafm8r92InEf9LDch-QzsHLGQLiPGFxk-Q6lQwzgYjB_xiE7Svg3xDuA-QR3Y4vN-Q8CfNToWwG4kgSL_iARbgZtOkI2Yr-hDyhONCZm0WzbMhsHw3giLQyhm96Tdc5BNY9ns0Nr-WATslTU?purpose=inline)

Hot and dry climates

Shading, roof reflectivity, thermal mass, ventilation timing, and cooling-system efficiency.

[Govt launches two apps to give real-time info on rainfall, urban flooding in Bengaluru](https://images.openai.com/static-rsc-4/dcc71HNtCKDJ80htep5qrUJcah-lKfRaYua53mGaeAHxKsSibjpwbs7a1EyzHHU-8hmLbB6IqzpThTecfJIMgPowE9jvC7meO8dl7XThWXGQEFIggXAZUN7zK8guMS5Sz4qcY4pwjcCHczUkcVDydSzWTz-1C0wP0zpha7Yb20Q?purpose=inline)

Climate hazards

Flooding, extreme heat, storms, and other locally relevant hazards can affect equipment placement, durability, insurance, and the suitability of an upgrade.

Location could also determine electricity tariffs, available energy sources, solar potential, contractor costs, subsidies, and local building requirements.

One important limitation: the system should use the most granular reliable location data available, not pretend it knows the exact microclimate of a property from its postcode alone.

## 3. Home type, floor, and building configuration

This deserves its own Building Context & Physical Feasibility component.

[The square by ira 4 BHK Villas Adibatla 3705.00 sqft properties | JLL Homes](https://images.openai.com/static-rsc-4/bRbQqhmilV4H6R0wWTI11ksP53my4euOW1RF77F4Q4ivVSc7utm0mm5CRBsN6iaji5uqEKAqBcTJgoBZmwjW6QJBi1lXiLrH4syyeArXipA0G7f_4EDgMFfv6kiAcbKRoT8kBGCPOM-XkwQ7xn7G89DpUT9pREMZLF1TO9IFHR8?purpose=inline)

Standalone or detached house

Potentially greater control over the roof, exterior walls, equipment placement, and property-level installations, subject to local rules.

[200A North East Road, Vale Park, SA 5081 - realestate.com.au](https://images.openai.com/static-rsc-4/8t4j2T7y4FRMM-jwyTUT62gt9yYIVROVRI9aEfsOhzTj_VAt9pJN50hUNKmtil8SvHTsAnWSOP2Fo6NgjQk_RcTGY27nZqFYB4WJ3oF56mq86xVaBpLPImZTxj24NPCyCExh8Q8qC8dMGneDVeoUR_xkxdUggJ1AYzyLqiYz38U?purpose=inline)

Semi-detached, duplex, or attached house

Shared walls, roof ownership, neighbour impact, and the distinction between private and shared structures matter.

[Victoria Vistas Bhawanipur – Luxury 3 & 4 BHK Apartments with Victoria Memorial Views](https://images.openai.com/static-rsc-4/m7YRDJg7HU7vMYwtwzXQpIW7UAXYXCsTX5Bd6y3HneAjyMQHIyMf4cSfWYbBzfDRJ9WizEDQ1-jRB3ptGUylQgKzyhgUIwRzTM11cM_cFGwp8a6-pCOxQ3eI6R1SD9kCKN9Oa2O_E2HTv2sAzlBRvU5CBsppRhcZsYqpdGmKGZE?purpose=inline)

Apartment or housing society

Roof access, facade restrictions, shared heating or cooling, electrical capacity, common-area systems, and society approvals may determine feasibility.

For apartments, the floor and position within the building can materially change the analysis:

- Top floor: potentially greater roof-related heat gain or heat loss.
- Ground floor: potentially different exposure to ground moisture, outdoor temperatures, and flooding.
- Middle floor: heat transfer from neighbouring units may reduce or increase heating and cooling needs.
- Corner or exposed unit: more external wall area can change thermal performance.
- Orientation and window exposure: affect daylight and solar heat gain.

These are not universal rules. Construction quality, surrounding buildings, shading, ventilation, and the actual roof and wall assemblies can reverse the expected result.

The product should also distinguish between an improvement that is technically possible and one that is feasible for a particular unit. A tenant in a high-rise apartment cannot independently install rooftop solar simply because the building receives plenty of sunlight. The roof belongs to somebody, or is shared, and apparently property rights insist on existing.

## 4. Legalities, permissions, and installation restrictions

This should be a Regulatory & Permission Feasibility component, not a disclaimer buried at the bottom of the page.

Before recommending an intervention, the system should determine the relevant constraints.

| Intervention             | Potential constraint                                                                |
| ------------------------ | ----------------------------------------------------------------------------------- |
| Rooftop solar            | Roof rights, society or landlord consent, grid connection, local installation rules |
| Heat pump                | Outdoor-unit placement, noise, electrical capacity, planning or building rules      |
| Window replacement       | Facade restrictions, conservation requirements, landlord consent                    |
| External wall insulation | Ownership, shared walls, planning permission, moisture considerations               |
| EV charger               | Parking rights, electrical capacity, building approvals                             |
| Smart controls           | Compatibility with existing systems and permission to modify them                   |

The actual rules depend on the jurisdiction, building, ownership arrangement, and specific installation.

Ideally, each proposed measure receives one of four statuses:

- Confirmed feasible: the necessary requirements have been checked against reliable information.
- Conditional: feasible if specified permission or technical conditions are met.
- Unverified: insufficient information to determine eligibility.
- Not feasible: a known constraint rules it out.

Crucially, unverified does not mean prohibited, and technically feasible does not mean legally approved. The system should identify the relevant authority, building management, landlord, or qualified professional when a decision requires confirmation.

## 5. Employment stability, spending capacity, and financial risk

Yes, these factors can improve recommendations. But I would not build a system that tries to infer someone's job security or financial health from their address, occupation, or other indirect clues.

Instead, make this an optional Personal Financial Resilience component based on information the user chooses to provide.

It could ask for:

- A comfortable upfront spending limit.
- Whether the user prefers upfront spending or monthly payments.
- Whether they have a financial buffer for unexpected expenses.
- How long they expect to remain in the property.
- How much uncertainty they are willing to accept.
- Whether they want to avoid long payback periods or ongoing contractual commitments.
- Whether they expect a major life change, such as moving, changing jobs, or a household-size change.

Exact salary, employer identity, bank balances, or detailed employment records should not be necessary for ordinary recommendations.

### Why this changes the result

Consider two households looking at the same insulation upgrade.

Household A

Low financial flexibility

Needs to preserve cash for near-term expenses and may move within two years.

Prioritise low-cost measures, reversible improvements, and upgrades with benefits within the expected occupancy period.

Household B

Longer-term capacity

Can comfortably fund improvements and expects to remain for a decade.

Consider larger investments with longer payback periods, while stress-testing costs and future energy prices.

These are illustrative profiles, not assumptions about real people.

A financially constrained household should not automatically receive worse energy-efficiency advice. It should receive recommendations that fit its constraints, including grants, subsidies, low-cost actions, and financing options where verified.

We should also keep this separate from credit scoring. The goal is to help users make housing decisions, not to judge their creditworthiness or employment prospects.

## 6. Combine the dimensions into one decision

The opportunity is to evaluate a retrofit across several simultaneous questions:

Physical feasibility

Can this property accommodate the upgrade?

Environmental suitability

Does it make sense for the local climate, energy supply, and hazards?

Legal and permission feasibility

Is it permitted, and which approvals remain outstanding?

Personal affordability

Can the person fund it without taking on an unacceptable financial burden?

Lifecycle suitability

Will the user stay long enough to benefit, and what happens if the occupants or intended use change?

Robustness

Does the recommendation remain reasonable under plausible changes in occupancy, appliance use, energy prices, and finances?

A recommendation should pass the hard constraints first. A legally prohibited or physically impossible installation should not rank first merely because a mathematical model predicts excellent savings.

After that, the system can compare feasible alternatives using the user's priorities.

## 7. What I think the product is becoming

The original Green Home Score was about evaluating a home's efficiency and comparing retrofit packages.

With these additions, it becomes a broader property-aware, occupant-aware retrofit decision engine:

- For tenants, it finds improvements they can actually make and benefit from.
- For homeowners, it balances long-term savings, comfort, cost, and property plans.
- For landlords, it considers investment returns, tenant benefits, compliance, and turnover.
- For housing societies, it evaluates shared upgrades and collective constraints.
- For future occupants, it tests whether recommendations remain useful as usage changes.
- For everyone, it distinguishes what is known, what is assumed, what is legally verified, and what remains uncertain.

One boundary matters: we should not try to collect every possible detail about a person and every possible detail about a building. That would produce an exhausting intake form and a false sense of precision. The system should ask for information when it can materially change the decision, allow unknown answers, and explain when missing information prevents a reliable recommendation.

The central product question is now bigger than “Which retrofit saves the most energy?” It is: “Given this building, location, ownership situation, intended use, financial constraints, and plausible future changes, which improvements are feasible and worthwhile for this particular decision-maker?”

That is a coherent product direction. The next conceptual challenge is deciding whether the product should primarily optimise for the individual occupant, the property owner, or the building itself, because those objectives can conflict even when everyone wants a greener home.