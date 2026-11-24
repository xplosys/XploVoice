// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { useActionState, type ReactNode } from "react";
import { useFormStatus } from "react-dom";
import type { ActionState } from "@/lib/actions";
import { Button, FormError } from "@/components/ui";

type Action = (prev: ActionState, form: FormData) => Promise<ActionState>;

export function ActionForm({ action, children, submit, variant, className, render }: {
  action: Action; children?: ReactNode; submit: string; variant?: "primary" | "secondary" | "danger" | "ghost";
  className?: string; render?: (s: ActionState) => ReactNode;
}) {
  const [state, formAction] = useActionState(action, undefined);
  return (
    <form action={formAction} className={className ?? "space-y-4"}>
      {children}
      <FormError message={state?.error} />
      {state?.ok && <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{state.ok}</p>}
      {render?.(state)}
      <Submit label={submit} variant={variant} />
    </form>
  );
}

function Submit({ label, variant }: { label: string; variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const { pending } = useFormStatus();
  return <Button type="submit" variant={variant} disabled={pending}>{pending ? "Working…" : label}</Button>;
}
