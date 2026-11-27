// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, type Healthcare, type VendorEligibility } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { ActionForm } from "@/components/forms/action-form";
import { Badge, Card, Input, Label, Notice, Select } from "@/components/ui";
import { When } from "@/components/when";
import {
  approvePolicyAction, classifyAction, draftPolicyAction, requestHealthcareAction, withdrawHealthcareAction,
} from "../healthcare-actions";
import { HealthcareTabs } from "./tabs";

export const metadata = { title: "Healthcare · XploVoice" };

const MODE = {
  off: ["Off", "slate"], requested: ["Requested", "amber"], active: ["Active", "green"], suspended: ["Suspended", "red"],
  withdrawn: ["Withdrawn", "slate"],
} as const;
const CLASS = { phi: ["Holds PHI", "red"], review: ["Review", "amber"], not_phi: ["No PHI", "green"] } as const;
const label = (s: string) => s.replaceAll("_", " ");

export default async function HealthcarePage() {
  const me = await getMe();
  if (!can(me, "healthcare:read")) redirect("/app");
  const manage = can(me, "healthcare:manage");
  const [hc, vendors] = await Promise.all([
    api<Healthcare>("/v1/healthcare"),
    api<VendorEligibility[]>("/v1/vendors/eligibility"),
  ]);
  const [modeLabel, tone] = MODE[hc.mode];
  const draft = hc.policies.find((p) => p.status === "draft");
  const inForce = hc.policies.find((p) => p.status === "approved");
  const canRequest = manage && (hc.mode === "off" || hc.mode === "withdrawn");
  const passed = hc.gate.filter((c) => c.ok).length;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Healthcare Mode <Badge tone={tone}>{modeLabel}</Badge></h1>
        <p className="text-sm text-slate-600">For US healthcare organisations. When it is on, health information (PHI) goes only to AI providers with a signed business associate agreement (BAA), transcripts and callers&apos; numbers are shown only to roles allowed to see PHI, every look at PHI is logged, webhooks carry ids instead of details, and every agent keeps to administrative tasks (no diagnosis, prescribing or triage).</p>
      </div>
      <HealthcareTabs me={me} current="/app/healthcare" />
      {!hc.platform_enabled && <Notice>Healthcare Mode is not available on this platform yet. You can prepare everything below; Xplosys turns it on.</Notice>}
      {hc.mode === "suspended" && <Notice>Healthcare Mode is suspended{hc.profile?.suspended_reason ? `: ${hc.profile.suspended_reason}` : ""}. New calls are refused. Every PHI protection stays on.</Notice>}

      {canRequest && (
        <Card>
          <h2 className="mb-1 text-lg font-medium">Ask for Healthcare Mode</h2>
          <p className="mb-4 text-sm text-slate-600">Asking changes nothing yet. Xplosys checks the activation gate below and turns it on only when every item passes. You need to be signed in with two-factor authentication.</p>
          <ActionForm action={requestHealthcareAction} submit="Ask for Healthcare Mode">
            <div className="grid gap-3 sm:grid-cols-2">
              <div><Label htmlFor="hc-entity">Your organisation is a</Label>
                <Select id="hc-entity" name="entity_type" defaultValue="covered_entity">
                  <option value="covered_entity">Covered entity (for example a clinic or practice)</option>
                  <option value="business_associate">Business associate (you serve covered entities)</option>
                </Select></div>
              <div><Label htmlFor="hc-contact">Privacy contact</Label><Input id="hc-contact" name="privacy_contact" required minLength={3} maxLength={200} placeholder="Privacy Office, privacy@clinic.example" /></div>
            </div>
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="synthetic_data_only" defaultChecked className="mt-1" />
              <span>Only synthetic (made-up) data will be used{hc.environment !== "production" ? ". Required outside production." : " (recommended for testing)."}</span></label>
          </ActionForm>
        </Card>
      )}

      {hc.profile && (
        <Card className="space-y-1 text-sm">
          <h2 className="mb-2 text-lg font-medium">Profile</h2>
          <p>{label(hc.profile.entity_type)} · {hc.profile.jurisdiction} · privacy contact: {hc.profile.privacy_contact}</p>
          <p className="text-slate-600">Requested <When iso={hc.profile.requested_at} />{hc.profile.activated_at && <> · active since <When iso={hc.profile.activated_at} /></>}
            {hc.profile.synthetic_data_only && <> · synthetic data only</>}</p>
          {manage && hc.mode === "requested" && <ActionForm action={withdrawHealthcareAction} submit="Withdraw the request" variant="secondary" className="pt-2" />}
        </Card>
      )}

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-medium">Activation gate</h2>
          <Badge tone={hc.gate_passed ? "green" : "amber"}>{passed} of {hc.gate.length} passed</Badge>
        </div>
        <ul className="divide-y divide-slate-100 text-sm">
          {hc.gate.map((c) => (
            <li key={c.key} className="flex items-start gap-3 py-2">
              <span aria-hidden className={c.ok ? "text-emerald-600" : "text-amber-600"}>{c.ok ? "✓" : "○"}</span>
              <div><p className="font-medium">{c.label}</p><p className="text-slate-600">{c.detail}</p></div>
            </li>
          ))}
        </ul>
      </Card>

      {hc.profile && (
        <Card className="space-y-4">
          <div>
            <h2 className="text-lg font-medium">Healthcare policy</h2>
            <p className="text-sm text-slate-600">{inForce ? <>Version {inForce.version} is in force: recording {inForce.recording_mode === "off" ? "off" : "only with the caller's consent"}, outbound campaigns {inForce.allow_outbound_campaigns ? "allowed" : "not allowed"}{inForce.privacy_notice && <>, notice: &ldquo;{inForce.privacy_notice}&rdquo;</>}.</> : "No version is approved yet, so the strictest settings apply: no recording and no outbound campaigns."}</p>
          </div>
          {draft && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
              <p className="font-medium">Draft version {draft.version}: {draft.change_note}</p>
              <p>Recording {draft.recording_mode === "off" ? "off" : "with consent"} · campaigns {draft.allow_outbound_campaigns ? "allowed" : "not allowed"}{draft.privacy_notice && <> · notice: &ldquo;{draft.privacy_notice}&rdquo;</>}</p>
              {manage && (draft.written_by_you
                ? <p className="mt-2 text-slate-600">You wrote this draft, so someone else must approve it.</p>
                : <ActionForm action={approvePolicyAction} submit="Approve this version" className="mt-2"><input type="hidden" name="id" value={draft.id} /></ActionForm>)}
            </div>
          )}
          {manage && (
            <details>
              <summary className="cursor-pointer text-sm text-brand-700 underline">Write a new version</summary>
              <ActionForm action={draftPolicyAction} submit="Save draft" className="mt-3 space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div><Label htmlFor="p-rec">Call recording</Label>
                    <Select id="p-rec" name="recording_mode" defaultValue={inForce?.recording_mode ?? "off"}>
                      <option value="off">Off</option><option value="consent_required">Only with the caller&apos;s consent</option>
                    </Select></div>
                  <label className="flex items-center gap-2 pt-6 text-sm"><input type="checkbox" name="allow_outbound_campaigns" defaultChecked={inForce?.allow_outbound_campaigns} /> Allow outbound campaign calls</label>
                </div>
                <div><Label htmlFor="p-notice">Privacy notice spoken at the start of every call (optional)</Label><Input id="p-notice" name="privacy_notice" maxLength={400} defaultValue={inForce?.privacy_notice} /></div>
                <div><Label htmlFor="p-note">What changed and why</Label><Input id="p-note" name="change_note" required minLength={3} maxLength={500} /></div>
              </ActionForm>
            </details>
          )}
          {hc.policies.length > 0 && (
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500"><tr><th className="py-1">Version</th><th>Status</th><th>Change</th><th>Written</th></tr></thead>
              <tbody>{hc.policies.map((p) => <tr key={p.id} className="border-t border-slate-100"><td className="py-1">{p.version}</td>
                <td><Badge tone={p.status === "approved" ? "green" : p.status === "draft" ? "amber" : "slate"}>{p.status}</Badge></td>
                <td>{p.change_note}</td><td><When iso={p.created_at} /></td></tr>)}</tbody>
            </table>
          )}
        </Card>
      )}

      {hc.classifications.length > 0 && (
        <Card>
          <h2 className="mb-1 text-lg font-medium">What holds PHI</h2>
          <p className="mb-3 text-sm text-slate-600">Your inventory of records. Locked kinds always hold PHI.</p>
          <table className="w-full text-left text-sm">
            <tbody>{hc.classifications.map((c) => {
              const [cl, ct] = CLASS[c.classification];
              return (
                <tr key={c.resource_type} className="border-t border-slate-100 align-top">
                  <td className="py-2 font-medium capitalize">{label(c.resource_type)}</td>
                  <td className="py-2 text-slate-600">{c.note}</td>
                  <td className="py-2">{c.locked || !manage ? <Badge tone={ct}>{cl}{c.locked ? " · locked" : ""}</Badge> : (
                    <ActionForm action={classifyAction} submit="Save" variant="secondary" className="flex items-center gap-2">
                      <input type="hidden" name="resource_type" value={c.resource_type} />
                      <Select name="classification" defaultValue={c.classification} aria-label={`Classification of ${label(c.resource_type)}`}>
                        <option value="phi">Holds PHI</option><option value="review">Review</option><option value="not_phi">No PHI</option>
                      </Select>
                    </ActionForm>)}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </Card>
      )}

      <Card>
        <h2 className="mb-1 text-lg font-medium">Providers allowed to receive PHI</h2>
        <p className="mb-3 text-sm text-slate-600">In Healthcare Mode, calls use only the providers marked allowed, including for fallback. Your own provider keys are not used, because XploVoice can&apos;t see your agreement with that vendor.</p>
        <table className="w-full text-left text-sm">
          <tbody>{vendors.map((v) => (
            <tr key={`${v.vendor_type}:${v.vendor_key}`} className="border-t border-slate-100">
              <td className="py-2 font-medium">{v.name}</td>
              <td className="py-2 text-slate-600">{v.kinds.map((k) => k.toUpperCase()).join(", ") || label(v.vendor_type)}</td>
              <td className="py-2">{v.eligible ? <Badge tone="green">Allowed</Badge> : <Badge>Not allowed</Badge>}</td>
              <td className="py-2 text-slate-600">{v.reason}{v.baa_expires_on && <> · until {v.baa_expires_on}</>}</td>
            </tr>
          ))}</tbody>
        </table>
      </Card>
    </div>
  );
}
