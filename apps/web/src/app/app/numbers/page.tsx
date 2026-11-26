// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, type Agent, type CallQueue, type DestinationPolicy, type PhoneNumber, type TelephonyProvider,
  type Trunk } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { label } from "@/lib/tones";
import { ActionForm } from "@/components/forms/action-form";
import { SimulateInbound } from "@/components/forms/telephony";
import { Badge, Card, Input, Label, Notice, Select } from "@/components/ui";
import { When } from "@/components/when";
import { addNumberAction, createQueueAction, createTrunkAction, deleteQueueAction, killSwitchAction, policyAction,
  releaseNumberAction, routeAction, syncTrunkAction, trunkStatusAction } from "../telephony-actions";

export const metadata = { title: "Phone numbers · XploVoice" };

const SYNC_TONE = { synced: "green", not_required: "slate", pending: "amber", error: "red" } as const;

export default async function NumbersPage() {
  const me = await getMe();
  if (!can(me, "telephony:read")) redirect("/app");
  const manage = can(me, "telephony:manage");
  const [providers, trunks, numbers, queues, policy, agents] = await Promise.all([
    api<TelephonyProvider[]>("/v1/telephony/providers"),
    api<Trunk[]>("/v1/telephony/trunks"),
    api<PhoneNumber[]>("/v1/phone-numbers"),
    api<CallQueue[]>("/v1/queues"),
    api<DestinationPolicy>("/v1/destination-policy"),
    can(me, "agents:read") ? api<Agent[]>("/v1/agents").catch(() => [] as Agent[]) : Promise.resolve([] as Agent[]),
  ]);
  const live = agents.filter((a) => a.status !== "archived");
  const simulated = numbers.filter((n) => n.status === "active" && n.provider_key === "simulated");
  const paused = !policy.telephony_enabled || !policy.platform_enabled;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Phone numbers</h1>
        <p className="text-sm text-slate-600">Connect your carrier&apos;s SIP trunk, add the numbers it gives you, and choose which agent answers each one. Outbound calls are limited by your destination policy below.</p>
      </div>

      <Card className={paused ? "border-red-300 bg-red-50" : ""}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-medium">{paused ? "Phone calls are paused" : "Phone calls are on"}</h2>
            <p className="text-sm text-slate-600">{!policy.platform_enabled ? "XploVoice has paused phone calls for every organisation." : paused
              ? "No call is answered or placed until you resume. Calls already in progress finish normally."
              : `Pausing stops every inbound and outbound phone call at once. ${policy.live_outbound} outbound call${policy.live_outbound === 1 ? "" : "s"} in progress now.`}</p>
          </div>
          {manage && policy.platform_enabled && (
            <ActionForm action={killSwitchAction} submit={paused ? "Resume phone calls" : "Pause all phone calls"} variant={paused ? "primary" : "danger"} className="">
              <input type="hidden" name="enable" value={paused ? "true" : "false"} />
            </ActionForm>
          )}
        </div>
      </Card>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">Numbers</h2>
        {numbers.length === 0 ? <p className="px-6 pb-6 pt-2 text-sm text-slate-600">No numbers yet. Add a trunk, then a number on it.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {numbers.map((n) => (
              <li key={n.id} className="space-y-3 px-6 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <span className="font-mono font-medium">{n.e164}</span> {n.label && <span className="text-slate-600">· {n.label}</span>}
                    <p className="text-xs text-slate-500">{n.trunk_name} · {n.inbound ? "receives calls" : "no inbound"} · {n.outbound ? "places calls" : "no outbound"}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={n.status === "active" ? "green" : "slate"}>{n.status}</Badge>
                    {n.route ? <Badge tone={n.route.status === "active" ? "brand" : "amber"}>answers: {n.route.agent_name}</Badge> : n.status === "active" && <Badge tone="amber">no route</Badge>}
                  </div>
                </div>
                {manage && n.status === "active" && (
                  <details className="rounded-md border border-slate-200 p-3">
                    <summary className="cursor-pointer text-sm font-medium">Inbound route</summary>
                    <ActionForm key={JSON.stringify(n.route)} action={routeAction} submit="Save route" className="mt-3 space-y-3">
                      <input type="hidden" name="id" value={n.id} />
                      <div className="grid gap-3 sm:grid-cols-3">
                        <div><Label htmlFor={`ag-${n.id}`}>Agent</Label>
                          <Select id={`ag-${n.id}`} name="agent_id" defaultValue={n.route?.agent_id ?? ""}>
                            <option value="">No route (callers are hung up on)</option>
                            {live.map((a) => <option key={a.id} value={a.id}>{a.name}{a.status !== "published" ? ` (${a.status}: takes no calls)` : ""}</option>)}
                          </Select></div>
                        <div><Label htmlFor={`q-${n.id}`}>Queue when busy</Label>
                          <Select id={`q-${n.id}`} name="queue_id" defaultValue={n.route?.queue_id ?? ""}>
                            <option value="">No queue</option>
                            {queues.map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
                          </Select></div>
                        <div><Label htmlFor={`fa-${n.id}`}>When nobody can answer</Label>
                          <Select id={`fa-${n.id}`} name="fallback_action" defaultValue={n.route?.fallback_action ?? "message"}>
                            <option value="message">Say a message, then hang up</option><option value="hangup">Hang up</option>
                          </Select></div>
                      </div>
                      <div><Label htmlFor={`fm-${n.id}`}>Fallback message</Label>
                        <Input id={`fm-${n.id}`} name="fallback_message" maxLength={300} defaultValue={n.route?.fallback_message ?? "Sorry, we can't take your call right now. Please try again later."} /></div>
                      <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="disabled" defaultChecked={n.route?.status === "disabled"} /> Route turned off</label>
                    </ActionForm>
                    <ActionForm action={releaseNumberAction} submit="Release number" variant="secondary" className="mt-3">
                      <input type="hidden" name="id" value={n.id} />
                    </ActionForm>
                  </details>
                )}
              </li>
            ))}
          </ul>
        )}
        {manage && trunks.some((t) => t.status === "active") && (
          <div className="border-t border-slate-200 px-6 py-5">
            <h3 className="mb-3 text-sm font-medium">Add a number you have from your carrier</h3>
            <ActionForm action={addNumberAction} submit="Add number">
              <div className="grid gap-3 sm:grid-cols-3">
                <div><Label htmlFor="number">Number</Label><Input id="number" name="number" required placeholder="+91 80 4123 4567" maxLength={30} /></div>
                <div><Label htmlFor="trunk_id">Trunk</Label><Select id="trunk_id" name="trunk_id">{trunks.filter((t) => t.status === "active").map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></div>
                <div><Label htmlFor="nlabel">Label</Label><Input id="nlabel" name="label" maxLength={120} placeholder="Reception" /></div>
              </div>
              <div className="flex gap-4 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" name="inbound" defaultChecked /> Receives calls</label>
                <label className="flex items-center gap-2"><input type="checkbox" name="outbound" defaultChecked /> Places campaign calls</label>
              </div>
            </ActionForm>
          </div>
        )}
      </Card>

      <Card className="p-0">
        <h2 className="px-6 pt-5 font-medium">SIP trunks</h2>
        {trunks.length === 0 ? <p className="px-6 pb-4 pt-2 text-sm text-slate-600">No trunk yet.</p> : (
          <ul className="mt-2 divide-y divide-slate-100 text-sm">
            {trunks.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-3">
                <div>
                  <p className="font-medium">{t.name} <span className="text-xs font-normal text-slate-500">· {providers.find((p) => p.key === t.provider_key)?.name ?? t.provider_key} · {t.direction}</span></p>
                  <p className="text-xs text-slate-500">{t.address ? `${t.address} (${t.transport})` : "no outbound address"} · {t.numbers} number{t.numbers === 1 ? "" : "s"} · billed in {t.billing_pulse_seconds}-second pulses{t.has_password ? " · password set" : ""}</p>
                  {t.sync_error && <p className="text-xs text-red-700">{t.sync_error}</p>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={SYNC_TONE[t.sync_status as keyof typeof SYNC_TONE] ?? "slate"}>{label(t.sync_status)}</Badge>
                  <Badge tone={t.status === "active" ? "green" : "slate"}>{t.status}</Badge>
                  {manage && <>
                    <ActionForm action={syncTrunkAction} submit="Sync" variant="secondary" className=""><input type="hidden" name="id" value={t.id} /></ActionForm>
                    <ActionForm action={trunkStatusAction} submit={t.status === "active" ? "Disable" : "Enable"} variant="ghost" className="">
                      <input type="hidden" name="id" value={t.id} /><input type="hidden" name="status" value={t.status === "active" ? "disabled" : "active"} />
                    </ActionForm>
                  </>}
                </div>
              </li>
            ))}
          </ul>
        )}
        {manage && (
          <div className="border-t border-slate-200 px-6 py-5">
            <h3 className="mb-1 text-sm font-medium">Add a trunk</h3>
            <p className="mb-3 text-xs text-slate-500">{providers.filter((p) => p.status === "awaiting_configuration").map((p) => `${p.name}: ${p.note}`).join(" ")}</p>
            <ActionForm action={createTrunkAction} submit="Add trunk">
              <div className="grid gap-3 sm:grid-cols-3">
                <div><Label htmlFor="tname">Name</Label><Input id="tname" name="name" required maxLength={120} placeholder="Main carrier" /></div>
                <div><Label htmlFor="prov">Type</Label><Select id="prov" name="provider_key">{providers.filter((p) => p.status !== "awaiting_configuration").map((p) => <option key={p.key} value={p.key}>{p.name}{p.status === "development_only" ? " (development only)" : ""}</option>)}</Select></div>
                <div><Label htmlFor="dir">Direction</Label><Select id="dir" name="direction" defaultValue="both"><option value="both">Inbound and outbound</option><option value="inbound">Inbound only</option><option value="outbound">Outbound only</option></Select></div>
                <div><Label htmlFor="addr">Carrier SIP address (outbound)</Label><Input id="addr" name="address" maxLength={255} placeholder="sip.your-carrier.example" /></div>
                <div><Label htmlFor="tr">Transport</Label><Select id="tr" name="transport"><option value="udp">UDP</option><option value="tcp">TCP</option><option value="tls">TLS</option></Select></div>
                <div><Label htmlFor="pulse">Billing pulse (seconds)</Label><Input id="pulse" name="billing_pulse_seconds" type="number" min={1} max={60} defaultValue={60} /></div>
                <div><Label htmlFor="user">Username</Label><Input id="user" name="auth_username" maxLength={120} autoComplete="off" /></div>
                <div><Label htmlFor="pw">Password</Label><Input id="pw" name="auth_password" type="password" maxLength={200} autoComplete="new-password" /></div>
                <div><Label htmlFor="allow">Allowed carrier IPs (inbound)</Label><Input id="allow" name="allowed_addresses" placeholder="203.0.113.10, 203.0.113.11" /></div>
              </div>
              <p className="text-xs text-slate-500">The password is encrypted and never shown again.</p>
            </ActionForm>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-1 font-medium">Call queues</h2>
          <p className="mb-3 text-sm text-slate-600">When your organisation&apos;s call limit is reached, callers to a number with a queue wait for the next free agent, then get the fallback.</p>
          <ul className="mb-4 space-y-2 text-sm">
            {queues.length === 0 && <li className="text-slate-600">No queues.</li>}
            {queues.map((q) => (
              <li key={q.id} className="flex items-center justify-between gap-2">
                <span>{q.name} <span className="text-xs text-slate-500">· up to {q.max_waiting} waiting, {q.max_wait_seconds} s each · {q.waiting} waiting now</span></span>
                {manage && <ActionForm action={deleteQueueAction} submit="Remove" variant="ghost" className=""><input type="hidden" name="id" value={q.id} /></ActionForm>}
              </li>
            ))}
          </ul>
          {manage && <ActionForm action={createQueueAction} submit="Add queue">
            <div className="grid gap-3 sm:grid-cols-3">
              <div><Label htmlFor="qn">Name</Label><Input id="qn" name="name" required maxLength={120} /></div>
              <div><Label htmlFor="qw">Max waiting</Label><Input id="qw" name="max_waiting" type="number" min={1} max={50} defaultValue={5} /></div>
              <div><Label htmlFor="qs">Max wait (s)</Label><Input id="qs" name="max_wait_seconds" type="number" min={10} max={600} defaultValue={60} /></div>
            </div>
          </ActionForm>}
        </Card>

        <Card>
          <h2 className="mb-1 font-medium">Destination policy</h2>
          <p className="mb-3 text-sm text-slate-600">Every outbound call and transfer is checked against these limits before the carrier is asked to dial. Today: {policy.outbound_minutes_today} of {policy.daily_outbound_minutes} outbound minutes used.</p>
          {manage ? (
            <ActionForm key={policy.updated_at} action={policyAction} submit="Save policy">
              <div><Label htmlFor="cc">Countries you may call (two-letter codes)</Label><Input id="cc" name="allowed_countries" defaultValue={policy.allowed_countries.join(", ")} required /></div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div><Label htmlFor="mco">Outbound calls at once</Label><Input id="mco" name="max_concurrent_outbound" type="number" min={1} max={50} defaultValue={policy.max_concurrent_outbound} /></div>
                <div><Label htmlFor="dom">Outbound minutes per day</Label><Input id="dom" name="daily_outbound_minutes" type="number" min={1} max={100000} defaultValue={policy.daily_outbound_minutes} /></div>
              </div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="block_premium" defaultChecked={policy.block_premium} /> Block premium-rate and shared-cost numbers</label>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="telephony_enabled" defaultChecked={policy.telephony_enabled} /> Phone calls on</label>
            </ActionForm>
          ) : (
            <ul className="text-sm"><li>Countries: {policy.allowed_countries.join(", ")}</li><li>Outbound at once: {policy.max_concurrent_outbound}</li>
              <li>Minutes per day: {policy.daily_outbound_minutes}</li><li>Premium numbers: {policy.block_premium ? "blocked" : "allowed"}</li></ul>
          )}
          <p className="mt-3 text-xs text-slate-500">Last changed <When iso={policy.updated_at} />.</p>
        </Card>
      </div>

      {manage && simulated.length > 0 && (
        <Card>
          <h2 className="mb-1 font-medium">Simulate an inbound call</h2>
          <Notice>Development only. Rings one of your numbers on the simulated carrier and routes it exactly like a real call. Nobody is dialled.</Notice>
          <SimulateInbound numbers={simulated.map((n) => n.e164)} />
        </Card>
      )}
    </div>
  );
}
