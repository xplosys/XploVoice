// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Agent, type Campaign, type PhoneNumber } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { CAMPAIGN_TONE } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { CampaignFields } from "@/components/forms/campaign-fields";
import { Badge, Card, Notice } from "@/components/ui";
import { When } from "@/components/when";
import { createCampaignAction } from "../telephony-actions";

export const metadata = { title: "Campaigns · XploVoice" };

export default async function CampaignsPage() {
  const me = await getMe();
  if (!can(me, "campaigns:read")) redirect("/app");
  const manage = can(me, "campaigns:manage");
  const [campaigns, agents, numbers] = await Promise.all([
    api<Campaign[]>("/v1/campaigns"),
    manage ? api<Agent[]>("/v1/agents").catch(() => [] as Agent[]) : Promise.resolve([] as Agent[]),
    manage && can(me, "telephony:read") ? api<PhoneNumber[]>("/v1/phone-numbers").catch(() => [] as PhoneNumber[]) : Promise.resolve([] as PhoneNumber[]),
  ]);
  const canCall = numbers.some((n) => n.status === "active" && n.outbound);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Outbound campaigns</h1>
        <p className="text-sm text-slate-600">An agent calls a list of people who agreed to be called. Every campaign needs approval, and every call is checked first: consent, your do-not-call list, the person&apos;s local calling hours and your limits.</p>
      </div>
      <Card className="p-0">
        {campaigns.length === 0 ? <p className="p-6 text-sm text-slate-600">No campaigns yet.</p> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {campaigns.map((c) => {
              const total = Object.values(c.counts).reduce((a, b) => a + b, 0);
              return (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
                  <div>
                    <Link className="font-medium text-brand-700 underline" href={`/app/campaigns/${c.id}`}>{c.name}</Link>
                    <p className="text-xs text-slate-500">{c.agent_name} · from {c.from_number} · {total} contact{total === 1 ? "" : "s"}, {c.counts.completed ?? 0} reached · <When iso={c.created_at} /></p>
                  </div>
                  <Badge tone={CAMPAIGN_TONE[c.status]}>{c.status}</Badge>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      {manage && (
        <Card>
          <h2 className="mb-3 font-medium">New campaign</h2>
          {!canCall ? <Notice>Add a phone number that places calls first, on the Phone numbers page.</Notice> : (
            <ActionForm action={createCampaignAction} submit="Create draft">
              <CampaignFields agents={agents} numbers={numbers} />
            </ActionForm>
          )}
        </Card>
      )}
    </div>
  );
}
