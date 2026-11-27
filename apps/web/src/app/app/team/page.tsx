// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { api, type Invitation, type Member } from "@/lib/api";
import { can, getMe } from "@/lib/me";
import { Badge, Button, Card, FormError, Select } from "@/components/ui";
import { InviteForm } from "@/components/forms/invite-form";
import { changeRoleAction, removeMemberAction, revokeInviteAction } from "../actions";

export const metadata = { title: "Team · XploVoice" };

const RANK: Record<string, number> = { viewer: 0, operator: 1, agent_designer: 2, privacy_officer: 2, admin: 3, owner: 4 };
const ROLES = Object.keys(RANK);

export default async function TeamPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const me = await getMe();
  if (!can(me, "members:read")) redirect("/app");
  const { error } = await searchParams;
  const manage = can(me, "members:manage");
  const [members, invites] = await Promise.all([
    api<Member[]>("/v1/members"),
    api<Invitation[]>("/v1/invitations"),
  ]);
  const pending = invites.filter((i) => !i.accepted_at && !i.revoked_at && new Date(i.expires_at) > new Date());
  // You can only assign roles at or below your own; only owners can create owners.
  const assignable = ROLES.filter((r) => RANK[r] <= RANK[me.role] && (r !== "owner" || me.role === "owner"));
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Team</h1>
      <FormError message={error} />
      {manage && (
        <Card><h2 className="mb-3 font-medium">Invite a teammate</h2>
          <InviteForm roles={assignable.filter((r) => r !== "owner")} /></Card>
      )}
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr><th className="px-4 py-3 font-medium">Member</th><th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">2FA</th>{manage && <th className="px-4 py-3" />}</tr>
          </thead>
          <tbody>
            {members.map((m) => {
              const self = m.user_id === me.user_id;
              const editable = manage && !self && RANK[m.role] <= RANK[me.role];
              return (
                <tr key={m.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3"><div className="font-medium">{m.display_name}{self && " (you)"}</div>
                    <div className="text-slate-500">{m.email}</div></td>
                  <td className="px-4 py-3">
                    {editable ? (
                      <form action={changeRoleAction} className="flex gap-2">
                        <input type="hidden" name="id" value={m.id} />
                        <Select name="role" defaultValue={m.role} aria-label={`Role for ${m.email}`} className="w-40">
                          {assignable.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
                        </Select>
                        <Button type="submit" variant="secondary">Save</Button>
                      </form>
                    ) : <Badge>{m.role.replaceAll("_", " ")}</Badge>}
                  </td>
                  <td className="px-4 py-3">{m.mfa_enabled ? <Badge tone="green">On</Badge> : <Badge tone="amber">Off</Badge>}</td>
                  {manage && (
                    <td className="px-4 py-3 text-right">
                      {editable && (
                        <form action={removeMemberAction}><input type="hidden" name="id" value={m.id} />
                          <Button type="submit" variant="ghost" className="text-red-700">Remove</Button></form>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
      {pending.length > 0 && (
        <Card><h2 className="mb-3 font-medium">Pending invitations</h2>
          <ul className="divide-y divide-slate-100 text-sm">
            {pending.map((i) => (
              <li key={i.id} className="flex items-center justify-between py-2">
                <span>{i.email} · <span className="text-slate-500">{i.role.replaceAll("_", " ")}, expires {new Date(i.expires_at).toLocaleDateString()}</span></span>
                {manage && (
                  <form action={revokeInviteAction}><input type="hidden" name="id" value={i.id} />
                    <Button type="submit" variant="ghost">Revoke</Button></form>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
