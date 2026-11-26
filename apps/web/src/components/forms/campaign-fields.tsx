// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import type { Agent, Campaign, PhoneNumber } from "@/lib/api";
import { Input, Label, Select } from "@/components/ui";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/** Campaign settings, shared by the create and edit forms. */
export function CampaignFields({ agents, numbers, c }: { agents: Agent[]; numbers: PhoneNumber[]; c?: Campaign }) {
  const hm = (v?: string) => (v ?? "").slice(0, 5);
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label htmlFor="cname">Name</Label><Input id="cname" name="name" required maxLength={120} defaultValue={c?.name} /></div>
        <div><Label htmlFor="cpurpose">Purpose</Label><Input id="cpurpose" name="purpose" maxLength={500} defaultValue={c?.purpose} placeholder="Appointment reminders" /></div>
        <div><Label htmlFor="cagent">Agent</Label><Select id="cagent" name="agent_id" defaultValue={c?.agent_id}>
          {agents.filter((a) => a.status !== "archived").map((a) => <option key={a.id} value={a.id}>{a.name}{a.status !== "published" ? ` (${a.status})` : ""}</option>)}</Select></div>
        <div><Label htmlFor="cfrom">Call from</Label><Select id="cfrom" name="from_number_id" defaultValue={c?.from_number_id}>
          {numbers.filter((n) => n.status === "active" && n.outbound).map((n) => <option key={n.id} value={n.id}>{n.e164}{n.label ? ` · ${n.label}` : ""}</option>)}</Select></div>
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-slate-700">Calling window</legend>
        <p className="text-xs text-slate-500">In each person&apos;s local time. It is never wider than the country default (India 09:00–21:00, US 08:00–21:00), which is a starting point from common guidance, not legal advice.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div><Label htmlFor="ctz">Campaign time zone</Label><Input id="ctz" name="timezone" required defaultValue={c?.timezone ?? "Asia/Kolkata"} /></div>
          <div><Label htmlFor="cws">From</Label><Input id="cws" name="window_start" type="time" defaultValue={hm(c?.window_start) || "10:00"} /></div>
          <div><Label htmlFor="cwe">Until</Label><Input id="cwe" name="window_end" type="time" defaultValue={hm(c?.window_end) || "18:00"} /></div>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">{DAYS.map((d) => (
          <label key={d} className="flex items-center gap-1"><input type="checkbox" name="days" value={d} defaultChecked={c ? c.days.includes(d) : !["sat", "sun"].includes(d)} />{d}</label>))}</div>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-4">
        <div><Label htmlFor="cma">Attempts per person</Label><Input id="cma" name="max_attempts" type="number" min={1} max={5} defaultValue={c?.max_attempts ?? 2} /></div>
        <div><Label htmlFor="crm">Retry after (minutes)</Label><Input id="crm" name="retry_minutes" type="number" min={15} max={10080} defaultValue={c?.retry_minutes ?? 120} /></div>
        <div><Label htmlFor="cmc">Calls at once</Label><Input id="cmc" name="max_concurrent" type="number" min={1} max={10} defaultValue={c?.max_concurrent ?? 1} /></div>
        <div><Label htmlFor="cpm">Calls per minute</Label><Input id="cpm" name="calls_per_minute" type="number" min={1} max={30} defaultValue={c?.calls_per_minute ?? 2} /></div>
      </div>
    </>
  );
}
