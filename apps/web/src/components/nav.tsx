// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export type NavItem = { href: string; label: string; phase?: number };

/** Sidebar. Items for features not yet built are shown greyed out with the phase that delivers them. */
export function SideNav({ items }: { items: NavItem[] }) {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="space-y-1">
      {items.map((i) => i.phase ? (
        <span key={i.href} aria-disabled className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-slate-400">
          {i.label}<span className="text-[10px] uppercase tracking-wide">Phase {i.phase}</span>
        </span>
      ) : (
        <Link key={i.href} href={i.href} aria-current={path === i.href ? "page" : undefined}
          className={cn("block rounded-md px-3 py-2 text-sm",
            path === i.href ? "bg-brand-50 font-medium text-brand-700" : "text-slate-700 hover:bg-slate-100")}>
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
