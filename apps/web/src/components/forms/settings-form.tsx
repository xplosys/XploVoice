// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { updateTenantAction } from "@/app/app/actions";
import { Input, Label, Select } from "@/components/ui";
import type { Country, Tenant } from "@/lib/api";
import { ActionForm } from "./action-form";

export function SettingsForm({ t, country }: { t: Tenant; country: Country }) {
  return (
    <ActionForm action={updateTenantAction} submit="Save settings">
      <div><Label htmlFor="name">Organisation name</Label><Input id="name" name="name" defaultValue={t.name} required maxLength={160} /></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label htmlFor="timezone">Time zone</Label>
          <Select id="timezone" name="timezone" defaultValue={t.timezone}>
            {country.timezones.map((z) => <option key={z} value={z}>{z}</option>)}
          </Select></div>
        <div><Label htmlFor="default_language">Default language</Label>
          <Select id="default_language" name="default_language" defaultValue={t.default_language}>
            {country.languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
          </Select></div>
        <div><Label htmlFor="business_phone">Business phone</Label>
          <Input id="business_phone" name="business_phone" defaultValue={t.business_phone ?? ""} placeholder={country.code === "IN" ? "+919876543210" : "+14155550100"} /></div>
        <div><Label htmlFor="industry">Industry</Label><Input id="industry" name="industry" defaultValue={t.industry ?? ""} maxLength={80} /></div>
      </div>
      <div><Label htmlFor="website">Website</Label><Input id="website" name="website" type="url" defaultValue={t.website ?? ""} placeholder="https://" /></div>
    </ActionForm>
  );
}
