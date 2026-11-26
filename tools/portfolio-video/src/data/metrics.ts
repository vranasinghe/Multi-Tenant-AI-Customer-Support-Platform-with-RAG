// Every figure shown on screen. Source: docs/portfolio-video/00_PROJECT_FACT_CHECK.md §4–5.
// Change a value only when the cited artifact changes.

export const SUITES = [
  { name: "Backend", passed: 1209 }, // F-60
  { name: "Runtime proxy", passed: 17 }, // F-61
  { name: "Web unit", passed: 243 }, // F-62
  { name: "Widget unit", passed: 19 }, // F-62
  { name: "Browser", passed: 17 }, // F-63
];

/** F-64: 1,505. The 753-test Linux unit run is a subset and is not added. */
export const TOTAL_PASSED = SUITES.reduce((sum, suite) => sum + suite.passed, 0);

export const FINDINGS_CLOSED = 7; // F-69
export const FINDINGS_TOTAL = 7;

/** F-70: backend tests at the first audit, when added audit checks still failed. */
export const ORIGINAL_BACKEND = 582;

/** F-68: self-assessment by the engineer who did the work; not independent. */
export const SCORE = { original: "80.5", current: "85.75" };
