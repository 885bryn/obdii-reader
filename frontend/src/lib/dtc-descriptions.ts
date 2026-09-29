/**
 * Explicit descriptions only; no pattern-based or manufacturer-specific guesses.
 * P0420 uses the SAE J2012 generic wording:
 * https://law.resource.org/pub/us/cfr/ibr/005/sae.j2012.2002.pdf
 */
export const DTC_DESCRIPTIONS: Readonly<Record<string, string>> = Object.freeze({
  P0420: "Catalyst system efficiency below threshold (Bank 1)",
});

export function describeDtc(code: string): string {
  return DTC_DESCRIPTIONS[code] ?? "Description unavailable";
}
