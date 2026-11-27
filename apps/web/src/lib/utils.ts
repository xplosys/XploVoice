import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Formats a metered quantity in its provider unit, e.g. "1 input token", "36 characters", "2.0 s". */
export function fmtQty(q: string | number, unit: string): string {
  const n = Number(q);
  if (unit === "audio_second") return `${n.toFixed(1)} s`;
  const name = unit.replace("_", " ");
  return `${n.toLocaleString()} ${name}${n === 1 ? "" : "s"}`;
}

/** Money in the organisation's currency: INR in the Indian format (1,23,456.00), USD in the US format. */
export function fmtMoney(amount: string | number | null | undefined, currency: string, digits = 2): string {
  const n = Number(amount ?? 0);
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency", currency, minimumFractionDigits: digits, maximumFractionDigits: Math.max(digits, 2),
  }).format(n);
}

/** A unit price, which can be a fraction of a cent (per 1,000 tokens, for example). */
export function fmtPrice(amount: string | number | null | undefined, currency: string): string {
  const n = Number(amount ?? 0);
  return fmtMoney(n, currency, n !== 0 && Math.abs(n) < 1 ? 4 : 2);
}

/** Badge colour for a call status. */
export const callTone = (s: string) =>
  s === "completed" ? "green" : s === "failed" ? "red" : s === "abandoned" ? "slate" : "brand";
