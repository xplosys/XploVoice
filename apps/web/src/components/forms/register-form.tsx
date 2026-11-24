// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useActionState, useState } from "react";
import { registerAction } from "@/app/(auth)/actions";
import { Button, FormError, Input, Label, Select } from "@/components/ui";

type Country = { code: string; name: string; default_timezone: string; timezones: string[] };

export function RegisterForm({ countries }: { countries: Country[] }) {
  const [state, action, pending] = useActionState(registerAction, undefined);
  const [code, setCode] = useState(countries[0]?.code ?? "IN");
  const c = countries.find((x) => x.code === code);
  return (
    <form action={action} className="space-y-4">
      <div><Label htmlFor="display_name">Your name</Label><Input id="display_name" name="display_name" required maxLength={120} /></div>
      <div><Label htmlFor="organization_name">Organisation</Label><Input id="organization_name" name="organization_name" required maxLength={160} /></div>
      <div><Label htmlFor="email">Work email</Label><Input id="email" name="email" type="email" autoComplete="email" required /></div>
      <div>
        <Label htmlFor="password">Password</Label>
        <Input id="password" name="password" type="password" autoComplete="new-password" minLength={12} required />
        <p className="mt-1 text-xs text-slate-500">At least 12 characters, using three of: lowercase, uppercase, digits, symbols.</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><Label htmlFor="country_code">Country</Label>
          <Select id="country_code" name="country_code" value={code} onChange={(e) => setCode(e.target.value)}>
            {countries.map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
          </Select></div>
        <div><Label htmlFor="timezone">Time zone</Label>
          <Select id="timezone" name="timezone" key={code} defaultValue={c?.default_timezone}>
            {c?.timezones.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select></div>
      </div>
      <p className="text-xs text-slate-500">Country sets your currency, date format and default languages. It cannot be changed later.</p>
      <FormError message={state?.error} />
      <Button type="submit" className="w-full" disabled={pending}>{pending ? "Creating…" : "Create account"}</Button>
    </form>
  );
}
