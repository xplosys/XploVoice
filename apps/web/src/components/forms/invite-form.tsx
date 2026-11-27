// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { inviteAction } from "@/app/app/actions";
import { Input, Label, Notice, Select } from "@/components/ui";
import { ActionForm } from "./action-form";

export function InviteForm({ roles }: { roles: string[] }) {
  return (
    <ActionForm action={inviteAction} submit="Send invitation"
      render={(s) => s?.data?.accept_url ? (
        <div>
          <Notice>
            Email delivery is awaiting configuration, so share this link with the invitee yourself (development only):{" "}
            <code className="break-all">{s.data.accept_url}</code>
          </Notice>
        </div>
      ) : null}>
      <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
      <div><Label htmlFor="inv-email">Email</Label><Input id="inv-email" name="email" type="email" required /></div>
      <div><Label htmlFor="inv-role">Role</Label>
        <Select id="inv-role" name="role" defaultValue="viewer">
          {roles.map((r) => <option key={r} value={r}>{r.replaceAll("_", " ")}</option>)}
        </Select></div>
      </div>
    </ActionForm>
  );
}
