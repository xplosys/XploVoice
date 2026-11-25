// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, type Delivery, type Integration, type IntegrationCatalog } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { DELIVERY_TONE } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { SecretForm } from "@/components/forms/phase5";
import { Badge, Card, Input, Label } from "@/components/ui";
import { createWebhookAction, webhookAction } from "../workflow-actions";

export const metadata = { title: "Integrations · XploVoice" };

export default async function IntegrationsPage() {
  const me = await getMe();
  if (!can(me, "tenant:read")) redirect("/app");
  const [catalog, events, hooks] = await Promise.all([
    api<IntegrationCatalog[]>("/v1/integrations/catalog"), api<string[]>("/v1/integrations/events"),
    api<Integration[]>("/v1/integrations"),
  ]);
  const deliveries = await Promise.all(hooks.map((h) => api<Delivery[]>(`/v1/integrations/${h.id}/deliveries`).catch(() => [])));
  const manage = can(me, "integrations:manage");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Integrations</h1>
        <p className="text-sm text-slate-600">Send what happens on calls to your own systems. Webhooks post signed JSON to an https address you choose, and retry with backoff if your server is down.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {catalog.map((c) => (
          <Card key={c.provider}>
            <p className="flex items-center justify-between font-medium">{c.name} <Badge tone={c.status === "available" ? "green" : "slate"}>{c.status.replaceAll("_", " ")}</Badge></p>
            <p className="mt-1 text-sm text-slate-600">{c.description}</p>
            {c.note && <p className="mt-2 text-xs text-slate-500">{c.note}</p>}
          </Card>
        ))}
      </div>

      <Card>
        <h2 className="mb-3 font-medium">Webhooks</h2>
        <div className="space-y-4">
          {hooks.length === 0 && <p className="text-sm text-slate-600">No webhooks yet.</p>}
          {hooks.map((h, i) => (
            <div key={h.id} className="rounded-md border border-slate-200 p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{h.name} <Badge tone={h.status === "active" ? "green" : "slate"}>{h.status}</Badge></p>
                  <p className="break-all font-mono text-xs text-slate-600">{h.url}</p>
                  <p className="text-xs text-slate-500">Events: {h.events.length ? h.events.join(", ") : "all"}</p>
                </div>
                {manage && <div className="flex flex-wrap gap-2">
                  <ActionForm action={webhookAction} submit={h.status === "active" ? "Disable" : "Enable"} variant="ghost" className="">
                    <input type="hidden" name="id" value={h.id} /><input type="hidden" name="op" value={h.status === "active" ? "disabled" : "active"} />
                  </ActionForm>
                </div>}
              </div>
              {manage && <SecretForm action={webhookAction} submit="Rotate signing secret" variant="secondary" className="mt-2 space-y-2">
                <input type="hidden" name="id" value={h.id} /><input type="hidden" name="op" value="rotate" />
              </SecretForm>}
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-slate-600">Recent deliveries ({deliveries[i].length})</summary>
                <ul className="mt-2 space-y-1 text-xs">
                  {deliveries[i].length === 0 && <li className="text-slate-500">None yet.</li>}
                  {deliveries[i].map((d) => (
                    <li key={d.id}>{new Date(d.created_at).toLocaleString()} · {d.event_type} · <Badge tone={DELIVERY_TONE[d.status] ?? "slate"}>{d.status}</Badge> · {d.attempts} attempt{d.attempts === 1 ? "" : "s"}{d.last_error && ` · ${d.last_error}`}{d.status === "retrying" && ` · next ${new Date(d.next_attempt_at).toLocaleTimeString()}`}</li>
                  ))}
                </ul>
              </details>
            </div>
          ))}
        </div>
        {manage && <div className="mt-6 border-t border-slate-200 pt-4">
          <h3 className="mb-2 text-sm font-medium">Add a webhook</h3>
          <SecretForm action={createWebhookAction} submit="Add webhook">
            <div className="grid gap-3 sm:grid-cols-2">
              <div><Label htmlFor="name">Name</Label><Input id="name" name="name" required maxLength={120} placeholder="CRM sync" /></div>
              <div><Label htmlFor="url">URL (https)</Label><Input id="url" name="url" type="url" required maxLength={500} placeholder="https://example.com/xplovoice" /></div>
            </div>
            <fieldset><legend className="mb-1 text-sm font-medium">Events (none ticked means all)</legend>
              <div className="grid gap-1 text-sm sm:grid-cols-3">{events.map((e) => <label key={e} className="flex items-center gap-1"><input type="checkbox" name="events" value={e} /> {e}</label>)}</div>
            </fieldset>
          </SecretForm>
        </div>}
      </Card>
    </div>
  );
}
