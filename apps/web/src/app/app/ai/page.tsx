// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, type AiCredential, type AiProvider, type KindRoutes, type RouteCheck } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Badge, Button, Card, FormError, Select } from "@/components/ui";
import { AiKeyForm } from "@/components/forms/ai-key-form";
import { revokeKeyAction, saveRoutesAction, verifyKeyAction } from "./actions";

export const metadata = { title: "AI providers · XploVoice" };

const KIND = { llm: "Language model (LLM)", stt: "Speech-to-text (STT)", tts: "Text-to-speech (TTS)" } as const;
const tone = (s: string) => (s === "available" ? "green" : s === "development only" ? "brand" : "amber");

export default async function AiPage({ searchParams }: { searchParams: Promise<{ error?: string; ok?: string }> }) {
  const me = await getMe();
  if (!can(me, "ai:read")) redirect("/app");
  const { error, ok } = await searchParams;
  const manage = can(me, "ai:manage");
  const [catalog, routes, keys] = await Promise.all([
    api<AiProvider[]>("/v1/ai/catalog"),
    api<KindRoutes[]>("/v1/ai/routes"),
    api<AiCredential[]>("/v1/ai/credentials"),
  ]);
  const checks = await Promise.all(routes.map((r) => api<RouteCheck>(`/v1/ai/routes/${r.kind}/check`)));
  const models = (kind: string) => catalog.flatMap((p) => p.models.filter((m) => m.kind === kind).map((m) => ({ ...m, provider: p })));
  const keyProviders = catalog.filter((p) => p.hosting === "cloud" && p.customer_keys_allowed);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">AI providers</h1>
        <p className="text-sm text-slate-600">Choose which models your voice agents use, in order. If the first is unavailable, XploVoice moves to the next automatically.</p>
      </div>
      <FormError message={error} />
      {ok && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{ok}</p>}

      {routes.map((r, idx) => {
        const options = models(r.kind);
        const check = checks[idx];
        return (
          <Card key={r.kind}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-medium">{KIND[r.kind]}</h2>
              <Badge tone={r.source === "none" ? "amber" : "slate"}>{r.source === "none" ? "not set" : r.source}</Badge>
            </div>
            {manage ? (
              <form action={saveRoutesAction} className="space-y-2">
                <input type="hidden" name="kind" value={r.kind} />
                {[0, 1, 2].map((i) => {
                  const cur = r.source === "organisation" ? r.routes[i] : undefined;
                  return (
                    <div key={i} className="grid gap-2 sm:grid-cols-[2rem_1fr_14rem] sm:items-center">
                      <span className="text-sm text-slate-500">{i + 1}.</span>
                      <Select name={`model_${i}`} defaultValue={cur?.model_id ?? ""} aria-label={`${r.kind} choice ${i + 1}`}>
                        <option value="">{i === 0 ? "Use XploVoice default" : "None"}</option>
                        {options.map((m) => <option key={m.id} value={m.id}>{m.provider.name} · {m.display_name}</option>)}
                      </Select>
                      <Select name={`cred_${i}`} defaultValue={cur?.credential_id ?? ""} aria-label={`Account for choice ${i + 1}`}>
                        <option value="">XploVoice account</option>
                        {keys.map((k) => <option key={k.id} value={k.id}>Your key: {k.label} ({k.provider_name})</option>)}
                      </Select>
                    </div>
                  );
                })}
                <Button type="submit" variant="secondary">Save {r.kind.toUpperCase()} order</Button>
              </form>
            ) : (
              <ol className="list-decimal pl-5 text-sm">{r.routes.map((x) => <li key={x.priority}>{x.provider} · {x.model}</li>)}</ol>
            )}
            <div className="mt-4 rounded-md bg-slate-50 p-3 text-sm">
              <p className="font-medium">Right now</p>
              {check.usable.length === 0 && <p className="text-amber-800">No provider can serve {r.kind.toUpperCase()} requests yet.</p>}
              {check.usable.map((u, i) => <p key={i} className="text-emerald-800">✓ {u.provider} · {u.model} ({u.account === "customer" ? "your key" : "XploVoice account"})</p>)}
              {check.skipped.map((s, i) => <p key={i} className="text-slate-600">– {s.provider} · {s.model}: {s.reason}</p>)}
            </div>
          </Card>
        );
      })}

      <Card>
        <h2 className="mb-3 font-medium">Your own API keys</h2>
        {keys.length > 0 && (
          <ul className="mb-4 divide-y divide-slate-100 text-sm">
            {keys.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span><span className="font-medium">{k.label}</span> · {k.provider_name} · <code>{k.secret_hint}</code>{" "}
                  {k.last_verified_at ? <Badge tone="green">verified</Badge> : k.last_error ? <Badge tone="amber">{k.last_error}</Badge> : <Badge>not checked</Badge>}</span>
                {manage && (
                  <span className="flex gap-2">
                    <form action={verifyKeyAction}><input type="hidden" name="id" value={k.id} /><Button type="submit" variant="ghost">Check</Button></form>
                    <form action={revokeKeyAction}><input type="hidden" name="id" value={k.id} /><Button type="submit" variant="ghost" className="text-red-700">Revoke</Button></form>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {manage ? <AiKeyForm providers={keyProviders} /> : <p className="text-sm text-slate-600">Only owners and admins can add keys.</p>}
      </Card>

      <Card className="overflow-x-auto p-0">
        <h2 className="px-6 pt-5 font-medium">Catalog</h2>
        <table className="mt-3 w-full text-left text-sm">
          <thead className="border-y border-slate-200 text-slate-500"><tr>
            <th className="px-6 py-2 font-medium">Provider</th><th className="px-4 py-2 font-medium">Does</th>
            <th className="px-4 py-2 font-medium">XploVoice account</th><th className="px-4 py-2 font-medium">Models</th></tr></thead>
          <tbody>
            {catalog.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 last:border-0 align-top">
                <td className="px-6 py-2"><div className="font-medium">{p.name}</div><div className="text-xs text-slate-500">{p.hosting.replace("_", "-")}{p.regions.length ? ` · ${p.regions.join(", ")}` : ""}</div></td>
                <td className="px-4 py-2 uppercase text-slate-600">{p.kinds.join(" · ")}</td>
                <td className="px-4 py-2"><Badge tone={tone(p.managed_status)}>{p.managed_status}</Badge></td>
                <td className="px-4 py-2 text-slate-600">{p.models.length === 0 ? "None added yet" : p.models.map((m) => (
                  <div key={m.id}>{m.display_name} <span className="text-xs">({m.kind}{m.languages.length ? `, ${m.languages.join(", ")}` : ""})</span></div>))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
