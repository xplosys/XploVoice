// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 font-semibold text-slate-900">
      <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">X</span>
      <span>XploVoice</span>
    </Link>
  );
}

export function Copyright() {
  return (
    <p className="text-xs text-slate-500">
      XploVoice by Xplosys · Copyright © 2026 Xplosys. All rights reserved.
    </p>
  );
}
