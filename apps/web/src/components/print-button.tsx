// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { Button } from "@/components/ui";

/** Opens the browser's print dialog, where the page can also be saved as a PDF. */
export function PrintButton({ label = "Print or save as PDF" }: { label?: string }) {
  return <Button type="button" variant="secondary" className="print:hidden" onClick={() => window.print()}>{label}</Button>;
}
