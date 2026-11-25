// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { api, ApiError, type Agent, type AgentVersion, type AgentVersionDetail } from "@/lib/api";
import { flatten } from "@/lib/agents";
import { can, getMe } from "@/lib/me";
import { Badge, Card } from "@/components/ui";

export const metadata = { title: "Agent version · XploVoice" };

export default async function VersionPage({ params, searchParams }: {
  params: Promise<{ id: string; n: string }>; searchParams: Promise<{ compare?: string; all?: string }>;
}) {
  const me = await getMe();
  if (!can(me, "agents:read")) redirect("/app");
  const { id, n } = await params;
  const base = `/v1/agents/${encodeURIComponent(id)}`;
  const get = (num: string) => api<AgentVersionDetail>(`${base}/versions/${encodeURIComponent(num)}`).catch((e) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const [agent, versions, v] = await Promise.all([api<Agent>(base), api<AgentVersion[]>(`${base}/versions`), get(n)]);
  const sp = await searchParams;
  const cmpNum = sp.compare ?? (v.version > 1 ? String(v.version - 1) : undefined);
  const other = cmpNum && cmpNum !== n ? await get(cmpNum) : undefined;
  const mine = flatten(v.config);
  const theirs = other ? flatten(other.config) : {};
  const keys = Object.keys(mine).sort();
  const changed = other ? keys.filter((k) => mine[k] !== theirs[k]) : [];
  const showAll = !other || sp.all === "1" || changed.length === 0;
  const rows = showAll ? keys : changed;
  return (
    <div className="space-y-6">
      <div>
        <Link href={`/app/agents/${agent.id}`} className="text-sm text-brand-700 underline">{agent.name}</Link>
        <h1 className="flex items-center gap-3 text-2xl font-semibold">Version {v.version}
          {v.is_published && <Badge tone="green">live</Badge>}{!v.is_published && v.was_published && <Badge>was live</Badge>}</h1>
        <p className="text-sm text-slate-600">Saved {new Date(v.created_at).toLocaleString()}{v.created_by ? ` by ${v.created_by}` : ""}. {v.test_calls} completed test call{v.test_calls === 1 ? "" : "s"}. Versions can never be changed; editing the agent saves a new one.</p>
        {v.note && <p className="text-sm text-slate-700">Note: {v.note}</p>}
        <p className="mt-1 font-mono text-xs text-slate-500">Content hash {v.content_hash.slice(0, 16)}</p>
      </div>
      <Card>
        <form className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <label htmlFor="compare">Compare with</label>
          <select id="compare" name="compare" defaultValue={other ? String(other.version) : ""} className="rounded-md border border-slate-300 px-2 py-1">
            {versions.filter((x) => x.version !== v.version).map((x) => <option key={x.id} value={x.version}>Version {x.version}</option>)}
          </select>
          <button className="rounded-md border border-slate-300 px-3 py-1 hover:bg-slate-50">Compare</button>
        </form>
        {other && (
          <p className="mb-3 text-sm text-slate-700">
            {changed.length === 0 ? `No settings differ from version ${other.version}.` : `${changed.length} setting${changed.length === 1 ? " differs" : "s differ"} from version ${other.version}.`}
            {changed.length > 0 && <> <Link className="text-brand-700 underline" href={`?compare=${other.version}${showAll ? "" : "&all=1"}`}>{showAll ? "Show only the differences" : "Show all settings"}</Link></>}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full table-fixed text-left text-sm">
            <thead><tr className="border-b text-xs uppercase text-slate-500"><th className="w-1/4 py-2 pr-4">Setting</th><th className="py-2 pr-4">Version {v.version}</th>{other && <th className="py-2">Version {other.version}</th>}</tr></thead>
            <tbody>
              {rows.map((k) => {
                const diff = changed.includes(k);
                return (
                  <tr key={k} className={`border-b border-slate-100 align-top ${diff ? "bg-amber-50" : ""}`}>
                    <td className="break-words py-1 pr-4 font-mono text-xs">{k}</td>
                    <td className="break-words py-1 pr-4 text-xs">{mine[k]}</td>
                    {other && <td className="break-words py-1 text-xs">{theirs[k] ?? "—"}</td>}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
