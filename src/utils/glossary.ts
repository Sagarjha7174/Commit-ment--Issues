/** Plain-language definitions for words a non-expert may not know. */
export const GLOSSARY: Record<string, string> = {
  'Green Home Score': 'A 0–100 rating of how energy-efficient and low-carbon this home is. Higher is better.',
  EPC: 'Energy Performance Certificate: the official A–G energy rating recorded when a home is sold or let.',
  kWh: 'Kilowatt-hour: the unit your energy bills are measured in. A kettle boil uses about 0.1 kWh.',
  'CO₂e': 'Carbon dioxide equivalent: a single measure of the greenhouse gases caused by the energy you use.',
  'heat pump': 'An electric heater that moves heat from the outside air into the home. It replaces a gas boiler, so gas use falls and electricity use rises.',
  SCOP: 'How efficient a heat pump is over a year. A SCOP of 3 means 3 units of heat for every unit of electricity.',
  benchmark: 'The typical energy use of similar homes nearby (national NEED data), used when we don’t have your meter readings.',
  scenario: 'One set of choices (which improvements, which assumptions) and the engine’s results for it. Each has its own ID.',
  feasible: 'Physically possible for this home, based on its recorded features.',
  'needs verification': 'We can’t tell from the records whether this would work. A survey would confirm it.',
  sensitivity: 'We re-run the plan with different assumptions (energy use ±15%, heat-pump efficiency, savings high/low) to see if the choice still holds.',
};
