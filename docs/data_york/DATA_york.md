# York regional dataset (Lloyds PS2 Green Home Score)

Built by `pipelines/build_region.py` (seed 42). Access date for all sources: 2026-10-10.

## Sources and licences

| Source | URL | Licence / attribution |
|---|---|---|
| EPC domestic certificates and recommendations (bulk, 2008-2026), MHCLG | https://get-energy-performance-data.communities.gov.uk | Open Government Licence v3.0; address data subject to Royal Mail / OS copyright terms on the service |
| NEED anonymised dataset 2026 (4M sample), DESNZ | https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-anonymised-data-2026 | OGL v3.0 |
| HM Land Registry Price Paid Data 2025-2026 | https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads | OGL v3.0. Contains HM Land Registry data © Crown copyright and database right 2026. This data is licensed under the Open Government Licence v3.0. |
| DESNZ GHG conversion factors 2026 | https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026 | OGL v3.0 |
| postcodes / EPC code lists (epc_codes.json) | EPC API /api/codes | OGL v3.0 |

## Coverage

Local authority E06000014 (York); all EPC certificates lodged 2008-2026; Land Registry sales Jan 2025-Aug 2026 in district YORK; NEED benchmarks from need_4m, region E12000003 (Yorkshire and The Humber).

## Known limitations

- NEED is anonymised and cannot be linked to individual EPC homes: baseline energy is a **population benchmark** (median of similar homes in the region), not a measurement of that home.
- Benchmarks are keyed by NEED's coarse bands; within-cell variation (IQR in benchmarks.parquet) is large because of occupant behaviour.
- NEED gas benchmarks cover gas-heated homes only; homes with mains gas but non-gas main heating get no gas baseline.
- NEED electricity is metered import; homes with solar PV will import less than the benchmark suggests.
- Only 2025-26 sales are available, so repeat sales of the same home are rare: price changes after retrofits cannot be observed directly.
- homes.parquet holds the *latest* certificate; for any sale-related modelling use the at-sale fields in sales_matched.parquet (latest EPC lodged on/before the sale) to avoid future leakage.
- EPC data reflect the assessor's visit; many certificates are old (EPCs last 10 years) and features may have changed since.
- `epc_predicted_consumption_kwh_m2_primary` (deprecated name) is SAP-modelled energy per m2, not metered; the data dictionary does not say whether it is primary or delivered energy.
- 'smart' controls is a proxy: EPCs record 'Time and temperature zone control', not whether a thermostat is internet-connected.
- Recommendations are the assessor's software suggestions: context labels, not feasibility ground truth.

## Assumptions

- property_id = UPRN where present, else hash of normalised address + postcode.
- Secondary glazing is treated as `double`; partial = any multi-glazed share between 1 and 99%.
- Main heating system = first system listed in mainheat_description; community schemes, LPG and solid fuels -> `other`.
- EPC age bands straddling NEED band edges are assigned by their midpoint (e.g. 1967-1975 -> NEED band 2).
- Open-ended floor-area and age bands: '2007/2012 onwards' end at 2026; 'before 1900' starts at 1850.
- Benchmark cells need >= 30 homes; otherwise the next coarser level is used (recorded per home). Benchmarks also split by main heating fuel, because electricity use differs strongly for electrically heated homes.
- Sales matching: same postcode, then exact normalised address (EPC lines 1 / 1-2 / 1-3 vs sale SAON+PAON+street with and without locality), then fuzzy token_sort_ratio >= 90 restricted to candidates with identical house/flat numbers; matches whose runner-up is within 3 points are 'ambiguous' and not linked.

## Mapping tables

### improvement_to_measure

File: `mappings/improvement_to_measure.csv`

|   improvement_id | improvement_summary                                             | measure          |
|-----------------:|:----------------------------------------------------------------|:-----------------|
|                1 | Insulate hot water cylinder with 80 mm jacket                   | other            |
|                2 | Increase hot water cylinder insulation                          | other            |
|                3 | Add additional 80 mm jacket to hot water cylinder               | other            |
|                4 | Hot water cylinder thermostat                                   | other            |
|                5 | Increase loft insulation to 270 mm                              | loft_insulation  |
|                6 | Cavity wall insulation                                          | cavity_wall      |
|                7 | 50 mm internal or external wall insulation                      | solid_wall       |
|                8 | Replace single glazed windows with low-E double glazed windows  | double_glazing   |
|                9 | Secondary glazing to single glazed windows                      | double_glazing   |
|               10 | Draught proof single-glazed windows                             | other            |
|               11 | Upgrade heating controls                                        | smart_thermostat |
|               12 | Upgrade heating controls                                        | smart_thermostat |
|               13 | Upgrade heating controls                                        | smart_thermostat |
|               14 | Upgrade heating controls                                        | smart_thermostat |
|               15 | Upgrade heating controls                                        | smart_thermostat |
|               16 | Time and temperature zone control                               | smart_thermostat |
|               17 | Upgrade heating controls                                        | smart_thermostat |
|               18 | Upgrade heating controls                                        | smart_thermostat |
|               19 | Solar water heating                                             | other            |
|               20 | Replace boiler with new condensing boiler                       | other            |
|               21 | Replace boiler with new condensing boiler                       | other            |
|               22 | Replace boiler with biomass boiler                              | other            |
|               23 | Wood pellet stove with boiler and radiators                     | other            |
|               24 | Fan assisted storage heaters and dual immersion cylinder        | other            |
|               25 | Fan-assisted storage heaters                                    | other            |
|               26 | Replacement warm air unit                                       | other            |
|               27 | Change heating to gas condensing boiler                         | other            |
|               28 | Condensing oil boiler with radiators                            | other            |
|               29 | Change heating to gas condensing boiler                         | other            |
|               30 | Fan assisted storage heaters and dual immersion cylinder        | other            |
|               31 | Fan-assisted storage heaters                                    | other            |
|               32 | Change heating to gas condensing boiler                         | other            |
|               34 | Solar photovoltaic panels, 2.5 kWp                              | solar_pv         |
|               35 | Low energy lighting for all fixed outlets                       | other            |
|               36 | Replace heating unit with condensing unit                       | other            |
|               37 | Install condensing boiler                                       | other            |
|               38 | Install condensing boiler                                       | other            |
|               39 | Wood pellet stove with boiler and radiators                     | other            |
|               40 | Change room heaters to condensing boiler                        | other            |
|               41 | Change room heaters to condensing boiler                        | other            |
|               42 | Replace heating unit with mains gas condensing unit             | other            |
|               43 | Condensing oil boiler with radiators                            | other            |
|               44 | Wind turbine                                                    | other            |
|               45 | Flat roof or sloping ceiling insulation                         | loft_insulation  |
|               46 | Room-in-roof insulation                                         | loft_insulation  |
|               47 | Floor insulation                                                | other            |
|               48 | High performance external doors                                 | other            |
|               49 | Heat recovery system for mixer showers                          | other            |
|               50 | Flue gas heat recovery in conjunction with boiler               | other            |
|               51 | Air or ground source heat pump                                  | heat_pump        |
|               52 | Air or ground source heat pump with underfloor heating          | heat_pump        |
|               53 | Micro CHP                                                       | other            |
|               54 | Biomass boiler (Exempted Appliance if in Smoke Control Area)    | other            |
|               55 | External insulation with cavity wall insulation                 | solid_wall       |
|               56 | Replacement glazing units                                       | double_glazing   |
|               57 | Floor insulation (suspended floor)                              | other            |
|               58 | Floor insulation (solid floor)                                  | other            |
|               59 | High heat retention storage heaters and dual immersion cylinder | other            |
|               60 | High heat retention storage heaters                             | other            |
|               61 | High heat retention storage heaters and dual immersion cylinder | other            |
|               62 | High heat retention storage heaters                             | other            |
|               63 | Party wall insulation                                           | other            |
|               65 | External wall insulation                                        | solid_wall       |
|               66 | Internal insulation with cavity wall insulation                 | solid_wall       |
|               70 | Water heating controls                                          | other            |
|               72 | Add PV battery                                                  | other            |
|               73 | Add PV diverter                                                 | other            |
|               75 | Air or ground source heat pump                                  | heat_pump        |
|               76 | Air or ground source heat pump with underfloor heating          | heat_pump        |

### glazing

File: `mappings/glazing.csv`

| glazing   | glazed_type                                   | windows_description                                  |     n |
|:----------|:----------------------------------------------|:-----------------------------------------------------|------:|
| double    | double glazing, unknown install date          | Fully double glazed                                  | 24548 |
| double    | double glazing installed during or after 2002 | Fully double glazed                                  | 23689 |
| double    | double glazing installed before 2002          | Fully double glazed                                  | 19339 |
| double    | <missing>                                     | High performance glazing                             |  7631 |
| double    | <missing>                                     | Fully double glazed                                  |  6105 |
| single    | not defined                                   | Single glazed                                        |  3708 |
| partial   | double glazing, unknown install date          | Partial double glazing                               |  1242 |
| partial   | double glazing installed before 2002          | Partial double glazing                               |  1064 |
| partial   | double glazing, unknown install date          | Mostly double glazing                                |   988 |
| partial   | double glazing installed during or after 2002 | Partial double glazing                               |   924 |
| single    | single glazing                                | Single glazed                                        |   781 |
| partial   | double glazing installed during or after 2002 | Mostly double glazing                                |   738 |
| partial   | double glazing installed before 2002          | Mostly double glazing                                |   609 |
| double    | not defined                                   | Fully double glazed                                  |   571 |
| partial   | double glazing, unknown install date          | Some double glazing                                  |   510 |
| double    | secondary glazing                             | Full secondary glazing                               |   461 |
| partial   | double glazing installed before 2002          | Some double glazing                                  |   318 |
| partial   | double glazing installed during or after 2002 | Some double glazing                                  |   315 |
| partial   | secondary glazing                             | Partial secondary glazing                            |   280 |
| partial   | <missing>                                     | Mostly double glazing                                |   195 |
| <missing> | <missing>                                     | SAP05:Windows                                        |   149 |
| partial   | <missing>                                     | Partial double glazing                               |   146 |
| single    | <missing>                                     | Single glazed                                        |   118 |
| double    | <missing>                                     | Multiple glazing throughout                          |   106 |
| double    | <missing>                                     | Full secondary glazing                               |    95 |
| triple    | triple glazing                                | Fully triple glazed                                  |    91 |
| double    | <missing>                                     | Single glazed                                        |    69 |
| partial   | secondary glazing                             | Some secondary glazing                               |    68 |
| partial   | secondary glazing                             | Mostly secondary glazing                             |    64 |
| partial   | <missing>                                     | Some double glazing                                  |    64 |
| partial   | not defined                                   | Mostly double glazing                                |    62 |
| partial   | not defined                                   | Partial double glazing                               |    49 |
| double    | not defined                                   | Multiple glazing throughout                          |    32 |
| partial   | not defined                                   | Mostly multiple glazing                              |    21 |
| triple    | <missing>                                     | Fully triple glazed                                  |    17 |
| partial   | not defined                                   | Some double glazing                                  |    17 |
| partial   | <missing>                                     | Partial multiple glazing                             |    17 |
| partial   | not defined                                   | Partial multiple glazing                             |    15 |
| partial   | <missing>                                     | Mostly multiple glazing                              |    15 |
| double    | secondary glazing                             | Fully secondary glazing                              |    12 |
| double    | double, known data                            | High performance glazing                             |    11 |
| double    | double glazing installed before 2002          | Single glazed                                        |    10 |
| double    | double glazing installed before 2002          | Single glazeddouble glazing                          |    10 |
| partial   | <missing>                                     | Partial secondary glazing                            |     9 |
| double    | double, known data                            | Fully double glazed                                  |     6 |
| double    | double glazing installed during or after 2002 | High performance glazing                             |     6 |
| partial   | <missing>                                     | Some secondary glazing                               |     6 |
| double    | secondary glazing                             | Secondary glazing                                    |     5 |
| partial   | triple glazing                                | Partial triple glazing                               |     4 |
| partial   | not defined                                   | Partial secondary glazing                            |     4 |
| triple    | not defined                                   | Fully triple glazed                                  |     3 |
| partial   | double, known data                            | Mostly double glazing                                |     2 |
| partial   | not defined                                   | Single glazed                                        |     2 |
| partial   | triple glazing                                | Mostly triple glazing                                |     2 |
| double    | single glazing                                | Multiple glazing throughout                          |     2 |
| partial   | double glazing installed during or after 2002 | Fully double glazed                                  |     1 |
| partial   | single glazing                                | Partial double glazing                               |     1 |
| partial   | double glazing installed during or after 2002 | Multiple glazing throughout                          |     1 |
| double    | double glazing installed during or after 2002 | Single glazed                                        |     1 |
| double    | double glazing, unknown install date          | Single glazed                                        |     1 |
| double    | <missing>                                     | High performance glazing|Ffenestri perfformiad uchel |     1 |
| single    | single glazing                                | Single glazedSingle glazing                          |     1 |
| double    | single glazing                                | Single glazed                                        |     1 |
| double    | double glazing, unknown install date          | double glazing                                       |     1 |
| partial   | single glazing                                | Single glazed                                        |     1 |
| double    | not defined                                   | Single glazed                                        |     1 |
| double    | double glazing, unknown install date          | Single glazeddouble glazing                          |     1 |
| double    | secondary glazing                             | Single glazedsecondary glazing                       |     1 |
| partial   | double glazing installed before 2002          | Mostly multiple glazing                              |     1 |
| partial   | triple glazing                                | Some triple glazing                                  |     1 |
| partial   | not defined                                   | Some multiple glazing                                |     1 |
| double    | double glazing installed before 2002          | High performance glazing                             |     1 |
| triple    | triple, known data                            | Fully triple glazed                                  |     1 |
| partial   | not defined                                   | Mostly secondary glazing                             |     1 |
| double    | double glazing, unknown install date          | High performance glazing                             |     1 |
| single    | not defined                                   | <missing>                                            |     1 |
| partial   | <missing>                                     | Some triple glazing                                  |     1 |
| partial   | <missing>                                     | Mostly secondary glazing                             |     1 |

### heating_type

File: `mappings/heating_type.csv`

| heating_type   | mainheat_description                                                       | main_fuel                                                                                     |     n |
|:---------------|:---------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------|------:|
| gas_boiler     | Boiler and radiators, mains gas                                            | mains gas (not community)                                                                     | 56523 |
| gas_boiler     | Boiler and radiators, mains gas                                            | mains gas                                                                                     | 13905 |
| electric       | Electric storage heaters                                                   | electricity (not community)                                                                   |  4198 |
| gas_boiler     | Boiler and radiators, mains gas                                            | Gas: mains gas                                                                                |  3778 |
| electric       | Room heaters, electric                                                     | electricity (not community)                                                                   |  3518 |
| electric       | Electric storage heaters                                                   | electricity                                                                                   |  2108 |
| electric       | Room heaters, electric                                                     | Electricity: electricity, unspecified tariff                                                  |  2063 |
| other          | Community scheme                                                           | <missing>                                                                                     |  1219 |
| oil            | Boiler and radiators, oil                                                  | oil (not community)                                                                           |   872 |
| electric       | Room heaters, electric                                                     | electricity                                                                                   |   691 |
| other          | Community scheme                                                           | mains gas (community)                                                                         |   682 |
| gas_boiler     | Boiler and underfloor heating, mains gas                                   | Gas: mains gas                                                                                |   542 |
| gas_boiler     | Room heaters, mains gas                                                    | mains gas (not community)                                                                     |   479 |
| heat_pump      | Air source heat pump, radiators, electric                                  | electricity (not community)                                                                   |   278 |
| heat_pump      | Air source heat pump, radiators, electric                                  | Electricity: electricity, unspecified tariff                                                  |   263 |
| gas_boiler     | Warm air, mains gas                                                        | mains gas (not community)                                                                     |   235 |
| gas_boiler     | Room heaters, mains gas                                                    | mains gas                                                                                     |   231 |
| other          | Boiler and radiators, LPG                                                  | LPG (not community)                                                                           |   213 |
| gas_boiler     | Boiler and underfloor heating, mains gas                                   | mains gas (not community)                                                                     |   194 |
| electric       | Boiler and radiators, electric                                             | electricity (not community)                                                                   |   192 |
| oil            | Boiler and radiators, oil                                                  | oil                                                                                           |   167 |
| gas_boiler     | Boiler and radiators, mains gas, Boiler and radiators, mains gas           | mains gas (not community)                                                                     |   124 |
| gas_boiler     | Boiler and radiators, mains gas, Boiler and underfloor heating, mains gas  | mains gas (not community)                                                                     |   116 |
| electric       | Room heaters, radiators, electric                                          | Electricity: electricity, unspecified tariff                                                  |   101 |
| other          | Community scheme                                                           | biomass (community)                                                                           |    99 |
| <missing>      | SAP05:Main-Heating                                                         | Gas: mains gas                                                                                |    93 |
| <missing>      | SAP05:Main-Heating                                                         | Electricity: electricity, unspecified tariff                                                  |    92 |
| electric       | Portable electric heaters assumed for most rooms                           | mains gas (not community)                                                                     |    90 |
| other          | Community scheme                                                           | mains gas                                                                                     |    86 |
| electric       | Boiler and radiators, electric                                             | Electricity: electricity, unspecified tariff                                                  |    85 |
| electric       | Electric underfloor heating                                                | electricity (not community)                                                                   |    83 |
| electric       | Boiler and radiators, electric                                             | electricity                                                                                   |    82 |
| other          | No system present: electric heaters assumed                                | To be used only when there is no heating/hot-water system or data is from a community network |    79 |
| heat_pump      | Air source heat pump, underfloor, electric                                 | Electricity: electricity, unspecified tariff                                                  |    78 |
| electric       | Electric storage heaters, Electric storage heaters                         | electricity (not community)                                                                   |    78 |
| electric       | Electric underfloor heating, Room heaters, electric                        | Electricity: electricity, unspecified tariff                                                  |    78 |
| electric       | Electric storage heaters, Room heaters, electric                           | electricity (not community)                                                                   |    71 |
| gas_boiler     | Warm air, mains gas                                                        | mains gas                                                                                     |    70 |
| gas_boiler     | Boiler& underfloor, mains gas                                              | Gas: mains gas                                                                                |    65 |
| heat_pump      | Air source heat pump, underfloor, electric                                 | electricity (not community)                                                                   |    58 |
| gas_boiler     | Boiler and underfloor heating, mains gas, Boiler and radiators, mains gas  | mains gas (not community)                                                                     |    52 |
| electric       | Electric storage heaters                                                   | Electricity: electricity, unspecified tariff                                                  |    51 |
| electric       | No system present: electric heaters assumed                                | To be used only when there is no heating/hot-water system                                     |    47 |
| other          | Boiler and radiators, dual fuel (mineral and wood)                         | dual fuel - mineral + wood                                                                    |    45 |
| heat_pump      | Air source heat pump, radiators, electric, Boiler and radiators, mains gas | electricity (not community)                                                                   |    44 |
| gas_boiler     | Boiler and underfloor heating, mains gas                                   | mains gas                                                                                     |    42 |
| other          | Community scheme, mains gas                                                | Gas: mains gas                                                                                |    40 |
| electric       | Electric underfloor heating                                                | electricity                                                                                   |    39 |
| other          | Boiler and radiators, LPG                                                  | LPG                                                                                           |    36 |
| gas_boiler     | Boiler and radiators, mains gas, Electric underfloor heating               | mains gas (not community)                                                                     |    35 |
| gas_boiler     | Boiler & underfloor, mains gas                                             | Gas: mains gas                                                                                |    35 |
| heat_pump      | Air source heat pump, radiators and underfloor, electric                   | Electricity: electricity, unspecified tariff                                                  |    33 |
| other          | Boiler and radiators, wood pellets                                         | bulk wood pellets                                                                             |    32 |
| other          | Room heaters, dual fuel (mineral and wood)                                 | dual fuel - mineral + wood                                                                    |    31 |
| gas_boiler     | Room heaters, mains gas, Room heaters, mains gas                           | mains gas (not community)                                                                     |    29 |
| other          | Boiler and radiators, LPG                                                  | Gas: bulk LPG                                                                                 |    26 |
| electric       | Boiler and underfloor heating, electric                                    | electricity (not community)                                                                   |    21 |
| gas_boiler     | Boiler and radiators, mains gas, Room heaters, electric                    | mains gas (not community)                                                                     |    21 |
| other          | Boiler and radiators, LPG                                                  | bottled LPG                                                                                   |    21 |
| gas_boiler     | Boiler with radiators and underfloor heating, mains gas                    | mains gas (not community)                                                                     |    21 |
| heat_pump      | Ground source heat pump, underfloor, electric                              | electricity (not community)                                                                   |    20 |
| heat_pump      | Ground source heat pump, radiators, electric                               | electricity (not community)                                                                   |    20 |
| gas_boiler     | Boiler and radiators, mains gas, Electric storage heaters                  | mains gas (not community)                                                                     |    19 |
| electric       | Electric storage heaters, radiators                                        | Electricity: electricity, unspecified tariff                                                  |    18 |
| oil            | Boiler and underfloor heating, oil                                         | oil (not community)                                                                           |    17 |
| other          | Portable electric heaters assumed for most rooms                           | dual fuel - mineral + wood                                                                    |    16 |
| electric       | Warm air, Electricaire                                                     | electricity (not community)                                                                   |    16 |
| other          | Room heaters, coal                                                         | house coal (not community)                                                                    |    16 |
| electric       | No system present: electric heaters assumed                                | electricity                                                                                   |    15 |
| heat_pump      | Air source heat pump, electric                                             | Electricity: electricity, unspecified tariff                                                  |    15 |
| other          | Boiler and radiators, smokeless fuel                                       | smokeless coal                                                                                |    13 |
| other          | Room heaters, wood logs                                                    | wood logs                                                                                     |    13 |
| other          | Boiler and radiators, coal                                                 | house coal (not community)                                                                    |    13 |
| electric       | Warm air, Electricaire                                                     | Electricity: electricity, unspecified tariff                                                  |    13 |
| heat_pump      | Ground source heat pump, underfloor, electric                              | Electricity: electricity, unspecified tariff                                                  |    12 |
| electric       | Room heaters, electric, Electric storage heaters                           | electricity (not community)                                                                   |    12 |
| heat_pump      | Air source heat pump, warm air, electric                                   | electricity (not community)                                                                   |    12 |
| other          | Room heaters, smokeless fuel                                               | smokeless coal                                                                                |    11 |
| oil            | Boiler and radiators, oil, Boiler and radiators, oil                       | oil (not community)                                                                           |    11 |
| oil            | Boiler and radiators, oil                                                  | Oil: heating oil                                                                              |    11 |

...(200 rows, see CSV)

### controls

File: `mappings/controls.csv`

| controls   | mainheatcont_description                                                                         |     n |
|:-----------|:-------------------------------------------------------------------------------------------------|------:|
| full       | Programmer, room thermostat and TRVs                                                             | 53523 |
| full       | Programmer and room thermostat                                                                   | 13016 |
| none       | Manual charge control                                                                            |  5023 |
| full       | Programmer, TRVs and bypass                                                                      |  4798 |
| smart      | Time and temperature zone control                                                                |  4744 |
| timer      | Programmer and appliance thermostats                                                             |  4437 |
| full       | Programmer, no room thermostat                                                                   |  1488 |
| full       | Automatic charge control                                                                         |  1260 |
| timer      | Appliance thermostats                                                                            |  1229 |
| none       | No thermostatic control of room temperature                                                      |   979 |
| full       | Charging system linked to use of community heating, programmer and TRVs                          |   943 |
| timer      | Room thermostat only                                                                             |   633 |
| full       | Programmer and at least two room thermostats                                                     |   290 |
| timer      | Flat rate charging, TRVs                                                                         |   283 |
| full       | Programmer and room thermostats                                                                  |   281 |
| timer      | TRVs and bypass                                                                                  |   276 |
| full       | Flat rate charging, programmer and TRVs                                                          |   225 |
| full       | Controls for high heat retention storage heaters                                                 |   224 |
| none       | No time or thermostatic control of room temperature                                              |   217 |
| <missing>  | SAP05:Main-Heating-Controls                                                                      |   185 |
| full       | Programmer, TRVs and boiler energy manager                                                       |   174 |
| full       | Charging system linked to use of community heating, programmer and at least two room thermostats |   159 |
| none       | None                                                                                             |   153 |
| full       | Charging system linked to use of community heating, programmer and at least two room stats       |   152 |
| full       | Room thermostat and TRVs                                                                         |   108 |
| full       | Flat rate charging, programmer and room thermostat                                               |   100 |
| full       | Charging system linked to use of community heating, programmer and room thermostat               |    79 |
| full       | Charging system linked to use of community heating, TRVs                                         |    73 |
| timer      | Room thermostats only                                                                            |    58 |
| full       | Flat rate charging, room thermostat and TRVs                                                     |    40 |
| smart      | Temperature zone control                                                                         |    37 |
| none       | Flat rate charging, no thermostatic control of room temperature                                  |    34 |
| full       | Celect control                                                                                   |    23 |
| full       | Flat rate charging, programmer and at least two room thermostats                                 |    19 |
| full       | Charging system linked to use of community heating, room thermostat only                         |    13 |
| full       | Programmer and at least 2 room thermostats                                                       |    12 |
| none       | Flat rate charging, no stat control of room temperature                                          |    12 |
| timer      | Flat rate charging, room thermostat only                                                         |    11 |
| full       | Celect controls                                                                                  |     8 |
| full       | Unit charging, programmer and TRVs                                                               |     6 |
| full       | Flat rate charging, programmer no room thermostat                                                |     4 |
| full       | Flat rate charging, programmer, no room thermostat                                               |     4 |
| none       | No time or thermostatic control of room temp                                                     |     3 |
| full       | Charging system linked to use of community heating, room thermostat and TRVs                     |     3 |
| <missing>  | <missing>                                                                                        |     2 |
| full       | Charging system linked to use of heating, room thermostat and TRVs                               |     2 |
| full       | Charging system linked to the use of community heating, prog and TRVs                            |     1 |
| full       | Flat rate charging, programmer and room stat                                                     |     1 |
| full       | Charging system linked to use of communit heating, programmer and TRVs                           |     1 |
| full       | Charging system linked to the use of community heating, programmer and TRVs                      |     1 |
| full       | Charging system linked to use of heating room thermostat and TRVs                                |     1 |

### age_band

File: `mappings/age_band.csv`

| age_band     | age_start   | age_end   | need_age_band   | raw                             |     n |
|:-------------|:------------|:----------|:----------------|:--------------------------------|------:|
| 1950-1966    | 1950.0      | 1966.0    | 2               | England and Wales: 1950-1966    | 13290 |
| 1930-1949    | 1930.0      | 1949.0    | 2               | England and Wales: 1930-1949    | 11858 |
| before 1900  | 1850.0      | 1899.0    | 1               | England and Wales: before 1900  | 11493 |
| 1967-1975    | 1967.0      | 1975.0    | 2               | England and Wales: 1967-1975    |  8326 |
| 1900-1929    | 1900.0      | 1929.0    | 1               | England and Wales: 1900-1929    |  7976 |
| 1996-2002    | 1996.0      | 2002.0    | 3               | England and Wales: 1996-2002    |  6294 |
| 1983-1990    | 1983.0      | 1990.0    | 3               | England and Wales: 1983-1990    |  5641 |
| 1976-1982    | 1976.0      | 1982.0    | 3               | England and Wales: 1976-1982    |  5138 |
| 2003-2006    | 2003.0      | 2006.0    | 4               | England and Wales: 2003-2006    |  3997 |
| 1991-1995    | 1991.0      | 1995.0    | 3               | England and Wales: 1991-1995    |  3681 |
| 2007-2011    | 2007.0      | 2011.0    | 4               | England and Wales: 2007-2011    |  1274 |
| 1930-1949    | 1930.0      | 1949.0    | 2               | 1930-1949                       |  1013 |
| before 1900  | 1850.0      | 1899.0    | 1               | Pre-1900                        |   974 |
| 1950-1966    | 1950.0      | 1966.0    | 2               | 1950-1966                       |   927 |
| 2016         | 2016.0      | 2016.0    | 4               | 2016                            |   926 |
| 1900-1929    | 1900.0      | 1929.0    | 1               | 1900-1929                       |   907 |
| 2007 onwards | 2007.0      | 2026.0    | 4               | England and Wales: 2007 onwards |   695 |
| 2017         | 2017.0      | 2017.0    | 4               | 2017                            |   583 |
| 2013         | 2013.0      | 2013.0    | 4               | 2013                            |   577 |
| 2019         | 2019.0      | 2019.0    | 4               | 2019                            |   577 |
| 2018         | 2018.0      | 2018.0    | 4               | 2018                            |   549 |
| 2021         | 2021.0      | 2021.0    | 4               | 2021                            |   545 |
| 1996-2002    | 1996.0      | 2002.0    | 3               | 1996-2002                       |   502 |
| 2009         | 2009.0      | 2009.0    | 4               | 2009                            |   500 |
| 2012 onwards | 2012.0      | 2026.0    | 4               | England and Wales: 2012 onwards |   463 |
| 2015         | 2015.0      | 2015.0    | 4               | 2015                            |   447 |
| 2023         | 2023.0      | 2023.0    | 4               | 2023                            |   446 |
| 2003-2006    | 2003.0      | 2006.0    | 4               | 2003-2006                       |   438 |
| 2014         | 2014.0      | 2014.0    | 4               | 2014                            |   434 |
| 1983-1990    | 1983.0      | 1990.0    | 3               | 1983-1990                       |   432 |
| 2024         | 2024.0      | 2024.0    | 4               | 2024                            |   430 |
| 2022         | 2022.0      | 2022.0    | 4               | 2022                            |   410 |
| 1967-1975    | 1967.0      | 1975.0    | 2               | 1967-1975                       |   407 |
| 2020         | 2020.0      | 2020.0    | 4               | 2020                            |   403 |
| 2025         | 2025.0      | 2025.0    | 4               | 2025                            |   374 |
| 2008         | 2008.0      | 2008.0    | 4               | 2008                            |   264 |
| 1976-1982    | 1976.0      | 1982.0    | 3               | 1976-1982                       |   260 |
| 2012-2021    | 2012.0      | 2021.0    | 4               | England and Wales: 2012-2021    |   250 |
| 2010         | 2010.0      | 2010.0    | 4               | 2010                            |   245 |
| 2011         | 2011.0      | 2011.0    | 4               | 2011                            |   242 |
| 1991-1995    | 1991.0      | 1995.0    | 3               | 1991-1995                       |   221 |
| 2012         | 2012.0      | 2012.0    | 4               | 2012                            |   218 |
| 2007         | 2007.0      | 2007.0    | 4               | 2007                            |   205 |
| <missing>    | <missing>   | <missing> | <missing>       | Post-2006                       |   156 |
| 2026         | 2026.0      | 2026.0    | 4               | 2026                            |   130 |
| 2006         | 2006.0      | 2006.0    | 4               | 2006                            |    81 |
| 2000         | 2000.0      | 2000.0    | 4               | 2000                            |    71 |
| <missing>    | <missing>   | <missing> | <missing>       | 0                               |    24 |
| 2005         | 2005.0      | 2005.0    | 4               | 2005                            |    12 |
| 2004         | 2004.0      | 2004.0    | 4               | 2004                            |    12 |
| 1900         | 1900.0      | 1900.0    | 1               | 1900                            |    11 |
| 2022 onwards | 2022.0      | 2026.0    | 4               | England and Wales: 2022 onwards |     5 |
| 1960         | 1960.0      | 1960.0    | 2               | 1960                            |     4 |
| 2103         | 2103.0      | 2103.0    | 4               | 2103                            |     2 |
| 1920         | 1920.0      | 1920.0    | 1               | 1920                            |     2 |
| 1901         | 1901.0      | 1901.0    | 1               | 1901                            |     1 |
| 1970         | 1970.0      | 1970.0    | 2               | 1970                            |     1 |
| 1967         | 1967.0      | 1967.0    | 2               | 1967                            |     1 |
| <missing>    | <missing>   | <missing> | <missing>       | 214                             |     1 |
| 1783         | 1783.0      | 1783.0    | 1               | 1783                            |     1 |
| 1930         | 1930.0      | 1930.0    | 2               | 1930                            |     1 |

### need_property_type

File: `mappings/need_property_type.csv`

| property_type   | built_form           | need_property_type   |     n |
|:----------------|:---------------------|:---------------------|------:|
| House           | Semi-Detached        | Semi detached        | 15160 |
| House           | Mid-Terrace          | Mid terrace          | 12972 |
| House           | Detached             | Detached             |  8829 |
| House           | End-Terrace          | End terrace          |  5409 |
| Flat            | Mid-Terrace          | Flat                 |  4505 |
| Bungalow        | Semi-Detached        | Bungalow             |  3578 |
| Bungalow        | Detached             | Bungalow             |  3338 |
| Flat            | Semi-Detached        | Flat                 |  3288 |
| Flat            | End-Terrace          | Flat                 |  2454 |
| Flat            | Detached             | Flat                 |  2046 |
| Flat            | <missing>            | Flat                 |  1507 |
| Flat            | Enclosed Mid-Terrace | Flat                 |   576 |
| Flat            | Enclosed End-Terrace | Flat                 |   566 |
| Maisonette      | Mid-Terrace          | Flat                 |   329 |
| Bungalow        | Mid-Terrace          | Bungalow             |   308 |
| Bungalow        | End-Terrace          | Bungalow             |   251 |
| Maisonette      | End-Terrace          | Flat                 |   178 |
| Maisonette      | Semi-Detached        | Flat                 |   119 |
| House           | Enclosed End-Terrace | End terrace          |   107 |
| Maisonette      | <missing>            | Flat                 |    95 |
| House           | <missing>            | <missing>            |    71 |
| Maisonette      | Detached             | Flat                 |    65 |
| House           | Enclosed Mid-Terrace | Mid terrace          |    61 |
| Park home       | Detached             | <missing>            |    17 |
| Maisonette      | Enclosed Mid-Terrace | Flat                 |    16 |
| Maisonette      | Enclosed End-Terrace | Flat                 |    13 |
| Bungalow        | Enclosed End-Terrace | Bungalow             |     7 |
| Bungalow        | <missing>            | Bungalow             |     4 |
| Bungalow        | Enclosed Mid-Terrace | Bungalow             |     3 |

### need_floor_area_band

File: `mappings/need_floor_area_band.csv`

|   need_floor_area_band | floor_area_m2   |
|-----------------------:|:----------------|
|                      1 | <=50            |
|                      2 | 50-100          |
|                      3 | 100-150         |
|                      4 | 150-200         |
|                      5 | >200            |

### need_epc_band

File: `mappings/need_epc_band.csv`

| rating   | need_epc_band   |
|:---------|:----------------|
| A        | A/B             |
| B        | A/B             |
| C        | C               |
| D        | D               |
| E        | E               |
| F        | F/G             |
| G        | F/G             |

### need_main_fuel

File: `mappings/need_main_fuel.csv`

| heating_type   | need_main_fuel   |
|:---------------|:-----------------|
| gas_boiler     | 1                |
| oil            | 2                |
| electric       | 2                |
| heat_pump      | 2                |
| other          | 2                |
| <missing>      | missing          |

### controls_rules

File: `mappings/controls_rules.csv`

| regex                                                                                                                                                                                           | level   |
|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------|
| temperature zone control|smart                                                                                                                                                                  | smart   |
| ^none$|no time or thermostatic|no thermostatic control|^manual charge|flat rate charging, no                                                                                                    | none    |
| (?:programmer|charging system linked).*(?:room thermostat|room stat|trvs)|room thermostat and trvs|automatic charge control|celect|high heat retention|boiler energy manager|programmer.*bypass | full    |
| programmer|room thermostat|trvs|appliance thermostat|flat rate charging                                                                                                                         | timer   |

## Column dictionary: homes.parquet

| Column | Unit | Provenance | Notes |
|---|---|---|---|
| property_id | - | observed | UPRN (prefix U) or sha256 of normalised address+postcode (prefix A) |
| certificate_number | - | observed | latest certificate |
| uprn | - | observed |  |
| address | - | observed | EPC address |
| postcode | - | observed |  |
| rating | A-G | observed | current_energy_rating |
| sap_score | SAP points 1-100+ | observed | current_energy_efficiency |
| potential_rating | A-G | modelled | assessor software potential rating |
| potential_sap | SAP points | modelled | potential_energy_efficiency |
| floor_area_m2 | m2 | observed | total_floor_area; values <=0 set missing |
| property_type | category | observed |  |
| built_form | category | observed | 'Not Recorded' -> missing |
| age_band | text | observed | construction_age_band with 'England and Wales:' prefix removed |
| age_start | year | observed | parsed from age band |
| age_end | year | assumption | 'onwards' bands end at 2026; pre-1900 starts 1850 |
| need_age_band | NEED code 1-4 | assumption | EPC band midpoint mapped to NEED edges |
| walls_rating | Very Poor..Very Good | observed |  |
| walls_rating_status | category | - | status/provenance of the related field |
| roof_rating | Very Poor..Very Good | observed | N/A = another dwelling above |
| roof_rating_status | category | - | status/provenance of the related field |
| floor_rating | Very Poor..Very Good | observed | mostly N/A in EPC (not rated in RdSAP) |
| floor_rating_status | category | - | status/provenance of the related field |
| windows_rating | Very Poor..Very Good | observed |  |
| windows_rating_status | category | - | status/provenance of the related field |
| glazing | single/partial/double/triple | observed | rules in mappings/glazing.csv; secondary glazing counted as double (assumption) |
| multi_glaze_pct | % | observed |  |
| heating_type | category | observed | rules in mappings/heating_type.csv |
| heating_rating | Very Poor..Very Good | observed | mainheat_energy_eff |
| controls | none/timer/full/smart | observed | rules in mappings/controls.csv; 'smart' = time & temperature zone control (proxy) |
| solar_pv | bool | observed | photo_supply > 0 |
| solar_pv_roof_pct | % of roof | observed | photo_supply |
| mains_gas | bool | observed | mains_gas_flag |
| epc_predicted_consumption_kwh_m2_primary | kWh/m2/yr (DEPRECATED: 'primary' unverified; use epc_modelled_energy_kwh_m2 in homes_tagged) | modelled | EPC energy_consumption_current (SAP model, not metered) |
| epc_predicted_consumption_status | category | - | status/provenance of the related field |
| lodgement_date | date | observed | latest certificate lodgement |
| raw_uprn_source | text | observed | raw EPC field, unchanged |
| raw_address1 | text | observed | raw EPC field, unchanged |
| raw_address2 | text | observed | raw EPC field, unchanged |
| raw_address3 | text | observed | raw EPC field, unchanged |
| raw_posttown | text | observed | raw EPC field, unchanged |
| raw_local_authority | text | observed | raw EPC field, unchanged |
| raw_local_authority_label | text | observed | raw EPC field, unchanged |
| raw_region | text | observed | raw EPC field, unchanged |
| raw_inspection_date | text | observed | raw EPC field, unchanged |
| raw_transaction_type | text | observed | raw EPC field, unchanged |
| raw_tenure | text | observed | raw EPC field, unchanged |
| raw_property_type | text | observed | raw EPC field, unchanged |
| raw_built_form | text | observed | raw EPC field, unchanged |
| raw_construction_age_band | text | observed | raw EPC field, unchanged |
| raw_total_floor_area | text | observed | raw EPC field, unchanged |
| raw_number_habitable_rooms | text | observed | raw EPC field, unchanged |
| raw_current_energy_rating | text | observed | raw EPC field, unchanged |
| raw_current_energy_efficiency | text | observed | raw EPC field, unchanged |
| raw_potential_energy_rating | text | observed | raw EPC field, unchanged |
| raw_potential_energy_efficiency | text | observed | raw EPC field, unchanged |
| raw_energy_consumption_current | text | observed | raw EPC field, unchanged |
| raw_co2_emissions_current | text | observed | raw EPC field, unchanged |
| raw_walls_description | text | observed | raw EPC field, unchanged |
| raw_walls_energy_eff | text | observed | raw EPC field, unchanged |
| raw_roof_description | text | observed | raw EPC field, unchanged |
| raw_roof_energy_eff | text | observed | raw EPC field, unchanged |
| raw_floor_description | text | observed | raw EPC field, unchanged |
| raw_floor_energy_eff | text | observed | raw EPC field, unchanged |
| raw_windows_description | text | observed | raw EPC field, unchanged |
| raw_windows_energy_eff | text | observed | raw EPC field, unchanged |
| raw_glazed_type | text | observed | raw EPC field, unchanged |
| raw_multi_glaze_proportion | text | observed | raw EPC field, unchanged |
| raw_main_fuel | text | observed | raw EPC field, unchanged |
| raw_mainheat_description | text | observed | raw EPC field, unchanged |
| raw_mainheat_energy_eff | text | observed | raw EPC field, unchanged |
| raw_mainheatcont_description | text | observed | raw EPC field, unchanged |
| raw_mainheatc_energy_eff | text | observed | raw EPC field, unchanged |
| raw_mains_gas_flag | text | observed | raw EPC field, unchanged |
| raw_photo_supply | text | observed | raw EPC field, unchanged |
| raw_solar_water_heating_flag | text | observed | raw EPC field, unchanged |
| raw_wind_turbine_count | text | observed | raw EPC field, unchanged |
| n_certificates | count | observed |  |
| need_property_type | NEED category | observed | mappings/need_property_type.csv |
| need_floor_area_band | NEED code 1-5 | observed | NEED edges 50/100/150/200 m2 |
| need_region | ONS code | observed | EPC region column |
| need_epc_band | A/B,C,D,E,F/G | observed |  |
| need_main_fuel | 1 gas / 2 not gas | observed | heating_type == gas_boiler |
| flag_floor_area_implausible | bool | observed | outside 15-1000 m2 |
| flag_missing_rating | bool | observed |  |
| flag_missing_heating | bool | observed |  |
| baseline_gas_kwh | kWh/yr | population_benchmark | NEED median for similar homes in region; 0 only when no mains gas |
| gas_benchmark_level | level / count | population_benchmark | benchmark cell used and its size |
| gas_benchmark_n | level / count | population_benchmark | benchmark cell used and its size |
| baseline_elec_kwh | kWh/yr | population_benchmark | NEED median for similar homes in region |
| elec_benchmark_level | level / count | population_benchmark | benchmark cell used and its size |
| elec_benchmark_n | level / count | population_benchmark | benchmark cell used and its size |
| flag_conflict_gas_heating_no_mains_gas | bool | observed | gas boiler recorded but mains_gas_flag = N; gas set 0 per rule |
| gas_status | category | - | how baseline_gas_kwh was set |
| elec_status | category | - |  |
| baseline_source | category | population_benchmark | provenance of baseline_*_kwh |
| modelled_gas_kwh | kWh/yr | unavailable | reserved for energy model |
| modelled_elec_kwh | kWh/yr | unavailable | reserved |
| rec_loft_insulation | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| rec_cavity_wall | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| rec_solid_wall | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| rec_double_glazing | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| rec_smart_thermostat | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| rec_heat_pump | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| rec_solar_pv | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| rec_other | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| n_recommendations | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| has_recommendations | 0/1 | observed | assessor recommendation on latest certificate (context label) |
| split | train/val/test | assumption | hash of property_id with seed 42, 70/15/15 |