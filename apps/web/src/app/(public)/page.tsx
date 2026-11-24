// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import Link from "next/link";

const POINTS = [
  ["One voice engine", "Browser and phone calls run through the same agent, tools and billing."],
  ["Built for India and the US", "Hindi, Hinglish, Indian English and US English, with INR and USD."],
  ["Your business, connected", "Appointments, leads, knowledge base and CRM workflows (rolling out by phase)."],
  ["Secure by design", "Tenant isolation in the database, MFA, audit trails and least-privilege access."],
];

export default function Home() {
  return (
    <div>
      <section className="mx-auto max-w-6xl px-4 py-20">
        <p className="text-sm font-medium text-brand-600">XploVoice by Xplosys</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          AI voice agents that talk to your customers naturally, on the phone and on the web.
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-slate-600">
          Create agents, give them your business knowledge and tools, then deploy them to answer calls, book
          appointments and qualify leads.
        </p>
        <div className="mt-8 flex gap-3">
          <Link href="/register" className="rounded-md bg-brand-600 px-5 py-3 font-medium text-white hover:bg-brand-700">
            Create your organization
          </Link>
          <Link href="/features" className="rounded-md border border-slate-300 px-5 py-3 font-medium hover:bg-slate-50">
            See features
          </Link>
        </div>
        <p className="mt-6 text-sm text-slate-500">
          Early access: XploVoice is in active development. Voice calling features are released phase by phase.
        </p>
      </section>
      <section className="border-t border-slate-100 bg-slate-50">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-16 sm:grid-cols-2 lg:grid-cols-4">
          {POINTS.map(([t, d]) => (
            <div key={t}>
              <h2 className="font-semibold">{t}</h2>
              <p className="mt-2 text-sm text-slate-600">{d}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
