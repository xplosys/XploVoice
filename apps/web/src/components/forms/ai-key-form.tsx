// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { addKeyAction } from "@/app/app/ai/actions";
import { Input, Label, Select } from "@/components/ui";
import { ActionForm } from "./action-form";

export function AiKeyForm({ providers }: { providers: { key: string; name: string }[] }) {
  return (
    <ActionForm action={addKeyAction} submit="Save key">
      <div className="grid gap-3 sm:grid-cols-3">
        <div><Label htmlFor="provider_key">Provider</Label>
          <Select id="provider_key" name="provider_key">
            {providers.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
          </Select></div>
        <div><Label htmlFor="label">Name</Label><Input id="label" name="label" required maxLength={80} placeholder="e.g. Production key" /></div>
        <div><Label htmlFor="secret">API key</Label>
          <Input id="secret" name="secret" type="password" autoComplete="off" required minLength={8} maxLength={512} /></div>
      </div>
      <p className="text-xs text-slate-500">Keys are encrypted at rest, used only by the XploVoice servers, and never shown again. Usage on your own key is billed to you by the provider.</p>
    </ActionForm>
  );
}
