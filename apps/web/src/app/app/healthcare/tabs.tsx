// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import type { Me } from "@/lib/api";
import { can } from "@/lib/me";
import { Notice } from "@/components/ui";

const TABS: [string, string, string][] = [
  ["/app/healthcare", "Overview", "healthcare:read"],
  ["/app/healthcare/access-log", "PHI access log", "phi_audit:read"],
  ["/app/healthcare/incidents", "Incidents", "incidents:report"],
  ["/app/healthcare/retention", "Retention and rights", "retention:manage"],
  ["/app/healthcare/compliance", "Evidence and report", "healthcare:read"],
];

export function HealthcareTabs({ me, current }: { me: Me; current: string }) {
  return (
    <div className="space-y-3 print:hidden">
      <nav className="flex flex-wrap gap-2 text-sm" aria-label="Healthcare">
        {TABS.filter(([, , p]) => can(me, p)).map(([href, label]) => (
          <Link key={href} href={href} aria-current={href === current ? "page" : undefined}
            className={href === current ? "rounded-md bg-brand-50 px-3 py-1.5 font-medium text-brand-700" : "rounded-md px-3 py-1.5 text-slate-600 hover:bg-slate-100"}>
            {label}
          </Link>
        ))}
      </nav>
      <Notice>Synthetic data only outside production. XploVoice does not claim HIPAA compliance: that depends on your agreements, your configuration and an independent assessment.</Notice>
    </div>
  );
}
