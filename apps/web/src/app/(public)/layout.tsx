// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";
import { Copyright, Logo } from "@/components/brand";

const NAV = [
  ["Features", "/features"], ["Solutions", "/solutions"], ["Industries", "/industries"], ["Pricing", "/pricing"],
  ["Healthcare", "/healthcare"], ["Security", "/security"], ["Docs", "/docs"], ["Contact", "/contact"],
];

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-4 py-4">
          <Logo />
          <nav className="hidden gap-5 text-sm text-slate-600 lg:flex">
            {NAV.map(([label, href]) => <Link key={href} href={href} className="hover:text-slate-900">{label}</Link>)}
          </nav>
          <div className="flex gap-2 text-sm">
            <Link href="/login" className="rounded-md px-3 py-2 text-slate-700 hover:bg-slate-100">Sign in</Link>
            <Link href="/register" className="rounded-md bg-brand-600 px-3 py-2 font-medium text-white hover:bg-brand-700">
              Get started
            </Link>
          </div>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-slate-200">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 sm:flex-row sm:justify-between">
          <Copyright />
          <p className="text-xs text-slate-500">XploVoice — Intelligent Conversations. Automated Business.</p>
        </div>
      </footer>
    </div>
  );
}
