// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { getMe } from "@/lib/me";
import { Copyright, Logo } from "@/components/brand";
import { ThemePicker } from "@/components/theme-picker";
import { Badge, Button, Card, FormError, Input, Label, Select } from "@/components/ui";
import { addModelAction, addPriceAction, setDefaultsAction, updateProviderAction } from "./actions";

export const metadata = { title: "AI catalog · Platform admin · XploVoice" };
export const dynamic = "force-dynamic";

type P = { id: string; key: string; name: string; hosting: string; kinds: string[]; base_url: string | null; managed_available: boolean;
  managed_key_configured: boolean; customer_keys_allowed: boolean; phi_eligible: boolean; baa_status: string; rate_limit_rpm: number | null;
  status: string; models: number; health: { state: string; recent_failures: number | null } };
type M = { id: string; provider_id: string; kind: string; model_key: string; display_name: string; languages: string[]; status: string };
type R = Record<"llm" | "stt" | "tts", { priority: number; model_id: string; model: string }[]>;

const Reason = () => <Input name="reason" required minLength={5} maxLength={500} placeholder="Reason (audited)" />;

export default async function AdminAi({ searchParams }: { searchParams: Promise<{ error?: string; ok?: string }> }) {
  await getMe();
  const { error, ok } = await searchParams;
  let providers: P[] = [], models: M[] = [], routes: R = { llm: [], stt: [], tts: [] };
  let denied: string | null = null;
  try {
    [providers, models, routes] = await Promise.all([api<P[]>("/admin/v1/ai/providers"), api<M[]>("/admin/v1/ai/models"), api<R>("/admin/v1/ai/routes")]);
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 403) throw e;
    denied = e.message;
  }
  const name = (id: string) => providers.find((p) => p.id === id)?.name ?? "";
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3"><Logo href="/admin" /><Badge tone="red">Platform admin</Badge></div>
        <nav className="flex items-center gap-4 text-sm"><Link href="/admin" className="text-brand-700 underline">Tenants</Link><Link href="/app" className="text-brand-700 underline">Back to workspace</Link><ThemePicker /></nav>
      </header>
      <main className="mx-auto max-w-6xl space-y-6 p-6">
        <div><h1 className="text-2xl font-semibold">AI catalog</h1>
          <p className="text-sm text-slate-600">Models and prices are entered from each provider&apos;s current price list; XploVoice ships none by default. Every change needs a reason and is audited.</p></div>
        {denied ? <FormError message={`${denied}. This needs a platform admin signed in with two-factor authentication.`} /> : (<>
          <FormError message={error} />
          {ok && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{ok}</p>}
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-500"><tr>
                <th className="px-4 py-3 font-medium">Provider</th><th className="px-4 py-3 font-medium">XploVoice account</th>
                <th className="px-4 py-3 font-medium">Health</th><th className="px-4 py-3 font-medium">Health data</th><th className="px-4 py-3 font-medium">Change</th></tr></thead>
              <tbody>
                {providers.map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 align-top last:border-0">
                    <td className="px-4 py-3"><div className="font-medium">{p.name}</div>
                      <div className="text-xs text-slate-500">{p.hosting} · {p.kinds.join(", ")} · {p.models} models</div>
                      {p.status !== "active" && <Badge tone="red">disabled</Badge>}</td>
                    <td className="px-4 py-3">{p.managed_key_configured ? <Badge tone="green">key configured</Badge> : <Badge tone="amber">awaiting configuration</Badge>}
                      <div className="mt-1 text-xs text-slate-500">offered to tenants: {p.managed_available ? "yes" : "no"}</div></td>
                    <td className="px-4 py-3"><Badge tone={p.health.state === "closed" ? "green" : p.health.state === "open" ? "red" : "amber"}>{p.health.state === "closed" ? "healthy" : p.health.state}</Badge>
                      {!!p.health.recent_failures && <div className="text-xs text-slate-500">{p.health.recent_failures} recent failures</div>}</td>
                    <td className="px-4 py-3">{p.phi_eligible ? <Badge tone="green">PHI allowed</Badge> : <Badge>not for PHI</Badge>}<div className="text-xs text-slate-500">BAA: {p.baa_status}</div></td>
                    <td className="px-4 py-3">
                      <form action={updateProviderAction} className="flex flex-wrap gap-2">
                        <input type="hidden" name="id" value={p.id} />
                        <Select name="managed_available" defaultValue="" className="w-40" aria-label="Offer XploVoice account">
                          <option value="">Offer account…</option><option value="true">Offer to tenants</option><option value="false">Do not offer</option></Select>
                        <Select name="status" defaultValue="" className="w-32" aria-label="Status">
                          <option value="">Status…</option><option value="active">Enable</option><option value="disabled">Disable</option></Select>
                        <Reason /><Button type="submit" variant="secondary">Apply</Button>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card><h2 className="mb-3 font-medium">Add a model</h2>
              <form action={addModelAction} className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div><Label>Provider</Label><Select name="provider_id">{providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></div>
                  <div><Label>Kind</Label><Select name="kind"><option value="llm">LLM</option><option value="stt">STT</option><option value="tts">TTS</option></Select></div>
                  <div><Label>Model id (as the provider names it)</Label><Input name="model_key" required /></div>
                  <div><Label>Display name</Label><Input name="display_name" required /></div>
                </div>
                <div><Label>Languages (comma separated, empty = any)</Label><Input name="languages" placeholder="en-IN, hi-IN, en-US" /></div>
                <div className="flex gap-4 text-sm"><label><input type="checkbox" name="streaming" /> Streaming</label><label><input type="checkbox" name="function_calling" /> Function calling</label></div>
                <Reason /><Button type="submit">Add model</Button>
              </form>
            </Card>
            <Card><h2 className="mb-3 font-medium">Add a price</h2>
              <form action={addPriceAction} className="space-y-3">
                <div><Label>Model</Label><Select name="model_id">{models.map((m) => <option key={m.id} value={m.id}>{name(m.provider_id)} · {m.display_name} ({m.kind})</option>)}</Select></div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div><Label>Unit</Label><Select name="unit">{["input_token", "output_token", "audio_second", "character", "request"].map((u) => <option key={u}>{u}</option>)}</Select></div>
                  <div><Label>Price per unit</Label><Input name="unit_price" required inputMode="decimal" placeholder="0.0000025" /></div>
                  <div><Label>Currency</Label><Select name="currency"><option>USD</option><option>INR</option></Select></div>
                </div>
                <div><Label>Source</Label><Input name="source" required minLength={5} placeholder="Provider price page, checked 2026-11-25" /></div>
                <Reason /><Button type="submit">Add price</Button>
              </form>
            </Card>
          </div>

          <Card><h2 className="mb-3 font-medium">Platform default order</h2>
            <p className="mb-3 text-sm text-slate-600">Used by organisations that have not chosen their own models.</p>
            <div className="grid gap-6 lg:grid-cols-3">
              {(["llm", "stt", "tts"] as const).map((k) => (
                <form key={k} action={setDefaultsAction} className="space-y-2">
                  <input type="hidden" name="kind" value={k} /><p className="text-sm font-medium uppercase">{k}</p>
                  {[0, 1, 2].map((i) => (
                    <Select key={i} name={`model_${i}`} defaultValue={routes[k][i]?.model_id ?? ""} aria-label={`${k} default ${i + 1}`}>
                      <option value="">{i === 0 ? "None" : "—"}</option>
                      {models.filter((m) => m.kind === k).map((m) => <option key={m.id} value={m.id}>{name(m.provider_id)} · {m.display_name}</option>)}
                    </Select>
                  ))}
                  <Reason /><Button type="submit" variant="secondary">Save</Button>
                </form>
              ))}
            </div>
          </Card>
        </>)}
        <Copyright />
      </main>
    </div>
  );
}
