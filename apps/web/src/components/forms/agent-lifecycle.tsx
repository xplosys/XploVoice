// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useActionState, useState } from "react";
import { createAgentAction, lifecycleAction, publishAction, rollbackAction } from "@/app/app/agents/actions";
import type { Agent, AgentTemplate, AgentVersion, Readiness } from "@/lib/api";
import { Button, FormError, Input, Label } from "@/components/ui";

function Status({ state }: { state: { ok?: string; error?: string } | undefined }) {
  return (<>
    <FormError message={state?.error} />
    {state?.ok && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{state.ok}</p>}
  </>);
}

/** Publish the latest version (with readiness and the test-call gate), pause, resume, archive, restore. */
export function LifecyclePanel({ agent, readiness, canPublish, canManage, canSkipTest }: {
  agent: Agent; readiness: Readiness; canPublish: boolean; canManage: boolean; canSkipTest: boolean;
}) {
  const [pub, publish, publishing] = useActionState(publishAction, undefined);
  const [life, act, acting] = useActionState(lifecycleAction, undefined);
  const [skip, setSkip] = useState(false);
  const latestLive = agent.published_version_id === agent.version_id;
  const archived = agent.status === "archived";
  return (
    <div className="space-y-3">
      {canPublish && !archived && !latestLive && (
        <form action={publish} className="space-y-2">
          <input type="hidden" name="id" value={agent.id} />
          <input type="hidden" name="version_id" value={agent.version_id} />
          {!readiness.tested && canSkipTest && (
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} /> Publish without a test call</label>
          )}
          {skip && (<div><Label htmlFor="skip">Why is it safe to skip the test? (recorded in the audit log)</Label>
            <Input id="skip" name="skip_test_reason" minLength={10} maxLength={300} required /></div>)}
          <Button type="submit" disabled={publishing || !readiness.ready || (!readiness.tested && !skip)}>
            {publishing ? "Publishing…" : `Publish version ${agent.version}`}</Button>
          {!readiness.ready && <p className="text-xs text-red-700">Fix the errors below before publishing.</p>}
          {readiness.ready && !readiness.tested && !skip && <p className="text-xs text-slate-600">Make a test call on version {agent.version} first. A completed test call unlocks publishing.</p>}
        </form>
      )}
      <form action={act} className="flex flex-wrap gap-2">
        <input type="hidden" name="id" value={agent.id} />
        {canPublish && agent.status === "published" && <Button name="op" value="pause" variant="secondary" disabled={acting}>Pause live calls</Button>}
        {canPublish && agent.status === "paused" && <Button name="op" value="resume" variant="secondary" disabled={acting}>Resume live calls</Button>}
        {canManage && !archived && (canPublish || !["published", "paused"].includes(agent.status)) && (
          <Button name="op" value="archive" variant="ghost" className="text-red-700" disabled={acting}>Archive</Button>)}
        {canManage && archived && <Button name="op" value="restore" variant="secondary" disabled={acting}>Restore</Button>}
      </form>
      <Status state={pub ?? life} />
    </div>
  );
}

/** Publish an older version for the first time, or roll back to one that was published before. */
export function VersionAction({ agent, v }: { agent: Agent; v: AgentVersion }) {
  const [rb, rollback, rolling] = useActionState(rollbackAction, undefined);
  const [pub, publish, publishing] = useActionState(publishAction, undefined);
  if (v.is_published || agent.status === "archived") return null;
  const canRollback = v.was_published && ["published", "paused"].includes(agent.status);
  return (
    <div className="space-y-1">
      {canRollback ? (
        <form action={rollback} className="flex gap-2">
          <input type="hidden" name="id" value={agent.id} /><input type="hidden" name="version_id" value={v.id} />
          <Input name="reason" aria-label="Reason for rolling back" placeholder="Reason (optional)" maxLength={300} className="h-8 w-44 py-1" />
          <Button type="submit" variant="secondary" className="py-1" disabled={rolling}>Roll back to this</Button>
        </form>
      ) : v.test_calls > 0 || v.was_published ? (
        <form action={publish}>
          <input type="hidden" name="id" value={agent.id} /><input type="hidden" name="version_id" value={v.id} />
          <Button type="submit" variant="secondary" className="py-1" disabled={publishing}>Publish this version</Button>
        </form>
      ) : null}
      <Status state={rb ?? pub} />
    </div>
  );
}

export function NewAgentForm({ templates }: { templates: AgentTemplate[] }) {
  const [state, action, pending] = useActionState(createAgentAction, undefined);
  const [key, setKey] = useState("receptionist");
  const chosen = templates.find((t) => t.key === key);
  return (
    <form action={action} className="space-y-6">
      <fieldset>
        <legend className="mb-3 font-medium">Start from a template</legend>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((t) => (
            <label key={t.key} className={`cursor-pointer rounded-lg border p-4 text-sm ${key === t.key ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:border-slate-300"}`}>
              <input type="radio" name="template_key" value={t.key} checked={key === t.key} onChange={() => setKey(t.key)} className="sr-only" />
              <span className="block text-xs uppercase tracking-wide text-slate-500">{t.category}</span>
              <span className="block font-medium">{t.name}</span>
              <span className="mt-1 block text-slate-600">{t.description}</span>
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">A template is only a starting point. You can change every setting afterwards.</p>
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        <div><Label htmlFor="name">Agent name</Label><Input id="name" name="name" required maxLength={120} defaultValue={chosen?.name ?? ""} key={key} /></div>
        <div><Label htmlFor="description">Description (optional)</Label><Input id="description" name="description" maxLength={500} /></div>
      </div>
      <FormError message={state?.error} />
      <Button type="submit" disabled={pending}>{pending ? "Creating…" : "Create agent"}</Button>
    </form>
  );
}
