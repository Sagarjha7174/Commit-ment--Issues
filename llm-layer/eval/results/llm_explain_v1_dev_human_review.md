# Human review sheet (LLM explanations)

For each sentence mark S (supported), U (unsupported) or C (contradicted) against the scenario JSON in eval/results/llm_cases.jsonl. Then compare with the judge's verdicts.

## missing_data-002 (missing_data, source: template)
Question: -

- [ ] 0. Your home's Green Home Score is 50/100, which is classed as Moderate.
- [ ] 1. Some information is missing, so the true score could be anywhere in the range 43–58; 6/7 parts of the score use known data.
- [ ] 2. The parts losing the most points are renewable energy and smart energy controls.
- [ ] 3. With the selected measures, the score is estimated to become 71/100 (Good).
- [ ] 4. Key issues: no renewable generation and basic heating controls.
- [ ] 5. The suggested measures, in the order they are applied, are: loft insulation, then cavity wall insulation, then solid wall insulation, then solar panels. Some of these need checking on site before they can be confirmed.
- [ ] 6. Why this order: solar panels are applied last because they only reduce the electricity bought from the grid.
- [ ] 7. Gas use is estimated to fall by 2,940 kWh/year.
- [ ] 8. Electricity bought from the grid is estimated to fall by 396 kWh/year.
- [ ] 9. In total, the energy the home buys is estimated to fall by 3,340 kWh/year, a cut of 24%.
- [ ] 10. With loft insulation, gas use is estimated to fall by 315 kWh/year.
- [ ] 11. With cavity wall insulation, gas use is estimated to fall by 1,210 kWh/year.
- [ ] 12. With solid wall insulation, gas use is estimated to fall by 1,420 kWh/year.
- [ ] 13. With solar panels, grid electricity is estimated to fall by 396 kWh/year.
- [ ] 14. These estimates account for how the measures interact: each one acts on the energy left after the previous one, so the savings are not simply added up.
- [ ] 15. Solar panels cut the electricity bought from the grid; they do not change how much energy the home itself needs.
- [ ] 16. Carbon emissions are estimated to fall by 594 kg CO2e/year, calculated separately for gas and electricity using DESNZ 2026 emissions factors.
- [ ] 17. The selected measures are estimated to cost about £21,500 in total.
- [ ] 18. The change in energy bills in pounds is not estimated for this home.
- [ ] 19. A change in property value is not estimated, because value is only estimated for the full recommended package.
- [ ] 20. Not suitable: double glazing, because the home already has double glazing.
- [ ] 21. Needs checking first: cavity wall insulation, because the wall construction is not recorded.
- [ ] 22. Needs checking first: solid wall insulation, because the wall construction is not recorded.
- [ ] 23. Note: Two months of meter data are missing; the annual figures are annualised from the ten available months.
- [ ] 24. Note: Wall construction is unknown, so the insulation part of the score uses a neutral value.
- [ ] 25. Details about the home that are missing: wall construction.
- [ ] 26. The starting energy use is not a meter reading from this home.
- [ ] 27. All savings, carbon and cost figures are estimates, not guarantees.
- [ ] 28. Main assumptions: 75/25 heating and hot water split of gas, boiler efficiency 85%, heat pump efficiency 3.0 (range 2.5 to 3.5) and 5% of gas used for cooking and other uses.

## missing_data-001 (missing_data, source: template)
Question: -

- [ ] 0. Your home's Green Home Score is 50/100, which is classed as Moderate.
- [ ] 1. Some information is missing, so the true score could be anywhere in the range 43–58; 6/7 parts of the score use known data.
- [ ] 2. The parts losing the most points are renewable energy and smart energy controls.
- [ ] 3. With the selected measures, the score is estimated to become 56/100 (Moderate).
- [ ] 4. Key issues: no renewable generation and basic heating controls.
- [ ] 5. The suggested measures, in the order they are applied, are: loft insulation, then a smart thermostat.
- [ ] 6. Gas use is estimated to fall by 852 kWh/year.
- [ ] 7. Electricity bought from the grid is not expected to change.
- [ ] 8. In total, the energy the home buys is estimated to fall by 852 kWh/year, a cut of 6.2%.
- [ ] 9. With loft insulation, gas use is estimated to fall by 315 kWh/year.
- [ ] 10. With a smart thermostat, gas use is estimated to fall by 538 kWh/year.
- [ ] 11. These estimates account for how the measures interact: each one acts on the energy left after the previous one, so the savings are not simply added up.
- [ ] 12. Carbon emissions are estimated to fall by 155 kg CO2e/year, calculated separately for gas and electricity using DESNZ 2026 emissions factors.
- [ ] 13. The selected measures are estimated to cost about £1,250 in total.
- [ ] 14. The change in energy bills in pounds is not estimated for this home.
- [ ] 15. A change in property value is not estimated, because value is only estimated for the full recommended package.
- [ ] 16. Not suitable: double glazing, because the home already has double glazing.
- [ ] 17. Needs checking first: cavity wall insulation, because the wall construction is not recorded.
- [ ] 18. Needs checking first: solid wall insulation, because the wall construction is not recorded.
- [ ] 19. Note: Two months of meter data are missing; the annual figures are annualised from the ten available months.
- [ ] 20. Note: Wall construction is unknown, so the insulation part of the score uses a neutral value.
- [ ] 21. Details about the home that are missing: wall construction.
- [ ] 22. The starting energy use is not a meter reading from this home.
- [ ] 23. All savings, carbon and cost figures are estimates, not guarantees.
- [ ] 24. Main assumptions: 75/25 heating and hot water split of gas, boiler efficiency 85%, heat pump efficiency 3.0 (range 2.5 to 3.5) and 5% of gas used for cooking and other uses.
