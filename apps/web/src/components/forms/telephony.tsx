// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
// Interactive pieces of the Phase 6 screens.
import Link from "next/link";
import { simulateInboundAction } from "@/app/app/telephony-actions";
import { Input, Label, Select } from "@/components/ui";
import { ActionForm } from "./action-form";

/** Development only: rings one of the organisation's numbers on the simulated carrier. */
export function SimulateInbound({ numbers }: { numbers: string[] }) {
  return (
    <ActionForm action={simulateInboundAction} submit="Ring the number" className="mt-3 space-y-3"
      render={(s) => s?.data?.call_id ? <Link className="text-sm text-brand-700 underline" href={`/app/calls/${s.data.call_id}`}>Open the call</Link> : null}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label htmlFor="sto">Number</Label><Select id="sto" name="to">{numbers.map((n) => <option key={n} value={n}>{n}</option>)}</Select></div>
        <div><Label htmlFor="sfrom">Caller</Label><Input id="sfrom" name="caller" defaultValue="+919800000001" /></div>
      </div>
    </ActionForm>
  );
}
