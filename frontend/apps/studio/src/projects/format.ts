/** How Analytics numbers read: dollars and durations. */

const cents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fractionOfACent = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumSignificantDigits: 2 });

/** Dollars as a person reads them: to the cent, or to two significant digits below a cent. */
export function dollars(amount: string): string {
  const value = Number(amount);
  return value !== 0 && value < 0.01 ? fractionOfACent.format(value) : cents.format(value);
}

/** Milliseconds, or seconds from one second up. */
export function duration(ms: number): string {
  return ms < 1000 ? `${String(Math.round(ms))} ms` : `${(ms / 1000).toFixed(1)} s`;
}
