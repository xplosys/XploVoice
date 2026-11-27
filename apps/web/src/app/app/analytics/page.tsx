// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { redirect } from "next/navigation";
import { api, type Analytics } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { label } from "@/lib/tones";
import { fmtMoney } from "@/lib/utils";
import { Card } from "@/components/ui";

export const metadata = { title: "Analytics · XploVoice" };

const RANGES = [7, 30, 90];
const CHANNEL: Record<string, string> = { "sip:inbound": "Phone, inbound", "sip:outbound": "Phone, outbound", "browser:test": "Browser test calls" };

function Tile({ title, value, note }: { title: string; value: string; note?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs text-slate-500">{title}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="text-xs text-slate-500">{note}</p>}
    </Card>
  );
}

/** One series (calls per day): thin bars from a shared baseline, a hover tooltip on each, and the table below. */
function CallsByDay({ rows }: { rows: Analytics["by_day"] }) {
  const max = Math.max(1, ...rows.map((r) => r.calls));
  return (
    <div>
      <div className="flex h-40 items-end gap-[2px] border-b border-slate-200" role="img" aria-label="Calls per day">
        {rows.map((r) => (
          <div key={r.day} className="group relative flex h-full flex-1 items-end justify-center" tabIndex={0}>
            <div className="w-full max-w-6 rounded-t bg-brand-500" style={{ height: `${(r.calls / max) * 100}%`, minHeight: 2 }} />
            <div className="pointer-events-none absolute bottom-full z-10 mb-1 hidden whitespace-nowrap rounded-md border border-slate-200 bg-white px-2 py-1 text-xs shadow group-hover:block group-focus:block">
              <span className="font-medium">{r.day}</span><br />{r.calls} calls · {r.completed} completed · {r.failed} not connected
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-slate-500"><span>{rows[0]?.day}</span><span>{rows.at(-1)?.day}</span></div>
    </div>
  );
}

export default async function AnalyticsPage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const me = await getMe();
  if (!can(me, "analytics:read")) redirect("/app");
  const { days: d } = await searchParams;
  const days = RANGES.includes(Number(d)) ? Number(d) : 30;
  const a = await api<Analytics>(`/v1/analytics/overview?days=${days}`);
  const t = a.totals;
  const money = a.by_day.some((r) => r.charges !== null);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Analytics</h1>
          <p className="text-sm text-slate-600">Calls and what the agents did, by day in {a.timezone}. Text chat tests are left out.</p></div>
        <nav className="flex gap-1 text-sm" aria-label="Time range">
          {RANGES.map((r) => <Link key={r} href={`/app/analytics?days=${r}`} aria-current={r === days ? "page" : undefined}
            className={r === days ? "rounded-md bg-brand-50 px-3 py-1 font-medium text-brand-700" : "rounded-md px-3 py-1 text-slate-600 hover:bg-slate-100"}>Last {r} days</Link>)}
        </nav>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile title="Calls" value={t.calls.toLocaleString()} note={`${t.completed} completed · ${t.failed} not connected`} />
        <Tile title="Talk time" value={`${Number(t.talk_minutes).toLocaleString()} min`} note={t.average_seconds ? `${Math.round(Number(t.average_seconds))} s on average` : undefined} />
        <Tile title="Handled by the agent" value={t.contained_percent !== null ? `${t.contained_percent}%` : "—"} note="of completed calls, without a transfer or escalation" />
        <Tile title="Transferred to a person" value={String(t.transferred)} note={`${t.escalated} escalated`} />
      </div>
      <Card className="space-y-3">
        <h2 className="font-medium">Calls per day</h2>
        {a.by_day.length ? <CallsByDay rows={a.by_day} /> : <p className="text-sm text-slate-600">No calls in this range.</p>}
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-0">
          <h2 className="px-6 pt-5 font-medium">Agents</h2>
          <table className="mt-2 w-full text-left text-sm"><thead className="text-slate-500"><tr>
            <th className="px-6 py-2 font-medium">Agent</th><th className="px-3 py-2 text-right font-medium">Calls</th>
            <th className="px-3 py-2 text-right font-medium">Completed</th><th className="px-6 py-2 text-right font-medium">Avg</th></tr></thead>
            <tbody>{a.by_agent.map((r) => (
              <tr key={r.agent_id} className="border-t border-slate-100"><td className="px-6 py-2"><Link className="underline" href={`/app/agents/${r.agent_id}`}>{r.agent}</Link></td>
                <td className="px-3 py-2 text-right tabular-nums">{r.calls}</td><td className="px-3 py-2 text-right tabular-nums">{r.completed}</td>
                <td className="px-6 py-2 text-right tabular-nums">{r.average_seconds ? `${Math.round(Number(r.average_seconds))} s` : "—"}</td></tr>))}
              {a.by_agent.length === 0 && <tr><td colSpan={4} className="px-6 py-3 text-slate-500">No calls.</td></tr>}</tbody></table>
        </Card>
        <Card className="space-y-4">
          <div><h2 className="font-medium">Channels</h2>
            <ul className="mt-1 text-sm">{a.by_channel.map((c) => <li key={c.key} className="flex justify-between"><span>{CHANNEL[c.key] ?? c.key}</span><span className="tabular-nums">{c.count}</span></li>)}</ul></div>
          <div><h2 className="font-medium">How calls ended</h2>
            <ul className="mt-1 text-sm">{a.end_reasons.map((c) => <li key={c.key} className="flex justify-between"><span>{label(c.key)}</span><span className="tabular-nums">{c.count}</span></li>)}</ul></div>
        </Card>
      </div>
      <Card>
        <h2 className="font-medium">What the agents did</h2>
        <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          {([["Appointments booked", a.outcomes.appointments_booked], ["Leads", a.outcomes.leads_created], ["Tickets", a.outcomes.tickets_created],
            ["Tool runs", a.outcomes.tool_runs], ["Tool failures", a.outcomes.tool_failures], ["Asked not to be called", a.outcomes.opt_outs]] as const).map(([k, v]) => (
            <div key={k}><dt className="text-slate-500">{k}</dt><dd className="text-lg font-semibold tabular-nums">{v}</dd></div>))}
        </dl>
      </Card>
      {a.by_day.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <h2 className="px-6 pt-5 font-medium">By day</h2>
          <table className="mt-2 w-full text-left text-sm"><thead className="text-slate-500"><tr>
            <th className="px-6 py-2 font-medium">Day</th><th className="px-3 py-2 text-right font-medium">Calls</th><th className="px-3 py-2 text-right font-medium">Completed</th>
            <th className="px-3 py-2 text-right font-medium">Not connected</th><th className="px-3 py-2 text-right font-medium">Minutes</th>
            {money && <th className="px-6 py-2 text-right font-medium">Charges</th>}</tr></thead>
            <tbody>{[...a.by_day].reverse().map((r) => (
              <tr key={r.day} className="border-t border-slate-100"><td className="px-6 py-2">{r.day}</td><td className="px-3 py-2 text-right tabular-nums">{r.calls}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.completed}</td><td className="px-3 py-2 text-right tabular-nums">{r.failed}</td>
                <td className="px-3 py-2 text-right tabular-nums">{Number(r.talk_minutes).toLocaleString()}</td>
                {money && <td className="px-6 py-2 text-right tabular-nums">{fmtMoney(r.charges, a.currency)}</td>}</tr>))}</tbody></table>
        </Card>
      )}
    </div>
  );
}
