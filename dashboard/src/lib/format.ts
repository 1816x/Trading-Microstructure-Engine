/** Number formatting shared by tiles, axes, tooltips and the journal table. */

const INT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const PRICE = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Integer with thousands separators (volumes, sizes). */
export function fmtInt(value: number): string {
  return INT.format(value);
}

/** Two-decimal price (VWAP, entry/exit). */
export function fmtPrice(value: number): string {
  return PRICE.format(value);
}

/** Signed, for values around a zero baseline (OFI, PnL). */
export function fmtSigned(value: number, digits = 2): string {
  const s = value.toFixed(digits);
  return value > 0 ? `+${s}` : s;
}

/** Compact significant-digits form for small magnitudes (realized vol). */
export function fmtSig(value: number, digits = 3): string {
  if (value === 0) return "0";
  return Number(value.toPrecision(digits)).toString();
}
