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

/** Badge colour for a call status. */
export const callTone = (s: string) =>
  s === "completed" ? "green" : s === "failed" ? "red" : s === "abandoned" ? "slate" : "brand";
