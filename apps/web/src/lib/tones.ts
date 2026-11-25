// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Badge colours for the Phase 5 record statuses, shared by list and detail pages.
type Tone = "slate" | "green" | "amber" | "red" | "brand";

export const LEAD_TONE: Record<string, Tone> = { new: "brand", contacted: "amber", qualified: "green", won: "green", lost: "red" };
export const TICKET_TONE: Record<string, Tone> = { open: "brand", pending: "amber", resolved: "green", closed: "slate" };
export const PRIORITY_TONE: Record<string, Tone> = { low: "slate", normal: "slate", high: "amber", urgent: "red" };
export const EXEC_TONE: Record<string, Tone> = {
  succeeded: "green", pending_approval: "amber", approved: "amber", failed: "red", denied: "red", rejected: "red", timeout: "red",
};
export const DELIVERY_TONE: Record<string, Tone> = { succeeded: "green", pending: "slate", retrying: "amber", dead: "red" };

export const label = (s: string) => s.replaceAll("_", " ");
