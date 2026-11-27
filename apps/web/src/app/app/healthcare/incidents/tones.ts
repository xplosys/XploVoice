// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
export const SEVERITY_TONE = { low: "slate", medium: "amber", high: "red", critical: "red" } as const;
export const STATUS_TONE = { open: "amber", assessing: "brand", notifying: "red", closed: "green" } as const;
export const tone = <T extends Record<string, string>>(m: T, k: string) => (m[k as keyof T] ?? "slate") as T[keyof T] | "slate";
