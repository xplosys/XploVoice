// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Marketing pages. Statements describe the product as designed; nothing here claims certification or
// capabilities that are not yet available (master prompt sections 21 and 31).
import Link from "next/link";
import { notFound } from "next/navigation";

type Page = { title: string; lead: string; sections: [string, string][] };

const PAGES: Record<string, Page> = {
  features: {
    title: "Features",
    lead: "Everything a business needs to run AI voice agents, delivered in phases.",
    sections: [
      ["Agent builder", "Instructions, personality, greeting, language, voice and model per agent, with versioning so every call records the exact configuration it used."],
      ["Browser and phone", "Test agents in the browser and deploy them on phone numbers or your own SIP trunk, through one common voice engine."],
      ["Knowledge base", "Upload PDF, DOCX, TXT and CSV files. Retrieval is isolated per organization."],
      ["Business tools", "Appointment booking, lead capture and qualification, support tickets and notifications, each permission-controlled."],
      ["Usage and billing", "Usage measured in real provider units with spending limits and alerts, in INR or USD."],
      ["Team and security", "Roles, MFA, audit logs and organization-level isolation."],
    ],
  },
  solutions: {
    title: "Solutions",
    lead: "Start from a template and adapt it to your business.",
    sections: [
      ["AI receptionist", "Answer calls, share business information and route callers."],
      ["Appointment booking", "Check availability, book, reschedule and cancel."],
      ["Lead qualification", "Capture and qualify leads, then hand them to your team or CRM."],
      ["Customer support and FAQ", "Answer common questions from your knowledge base and escalate to a person when needed."],
      ["Follow-up", "Consent-checked outbound follow-up calls within permitted calling windows."],
    ],
  },
  industries: {
    title: "Industries",
    lead: "Designed for service businesses of every size.",
    sections: [
      ["Clinics and healthcare administration", "Front-desk tasks such as appointment requests and clinic FAQs. No clinical advice."],
      ["Real estate", "Lead capture and site-visit scheduling."],
      ["Education", "Admissions enquiries and counselling bookings."],
      ["Home and local services", "Service booking and job follow-ups."],
      ["Retail and e-commerce", "Order and policy questions with escalation to your team."],
    ],
  },
  pricing: {
    title: "Pricing",
    lead: "Plans will combine a subscription with pay-as-you-go usage, billed in INR or USD.",
    sections: [
      ["Usage-based", "You pay for what calls actually use: telephony, speech and AI, measured from provider records."],
      ["Spending limits", "Set monthly limits and alerts so costs never surprise you."],
      ["Published plans", "Plan prices will be published when billing launches. Contact us for early-access terms."],
    ],
  },
  healthcare: {
    title: "Healthcare",
    lead: "A dedicated Healthcare Mode for US healthcare organizations is planned, with strict safeguards.",
    sections: [
      ["Administrative use only", "Appointment requests, clinic FAQs and call routing. Diagnosis, prescribing and triage are out of scope."],
      ["Gated activation", "Processing of protected health information stays disabled until agreements, vendor approvals and safeguards are verified."],
      ["No compliance claims", "XploVoice does not claim HIPAA compliance or certification. Compliance depends on contracts, configuration and independent assessment."],
    ],
  },
  security: {
    title: "Security",
    lead: "Security and tenant isolation are built into the foundation.",
    sections: [
      ["Organization isolation", "PostgreSQL row-level security on every organization's data, enforced for the application's own database role."],
      ["Accounts", "Argon2id password hashing, TOTP multi-factor authentication, short-lived tokens with rotation and reuse detection."],
      ["Least privilege", "Role-based permissions enforced by the API, not just hidden in the interface."],
      ["Audit trail", "Tamper-evident, append-only audit log of sign-ins, permission denials and administrative changes."],
    ],
  },
  docs: {
    title: "Documentation",
    lead: "Product and API documentation.",
    sections: [
      ["API reference", "The OpenAPI reference is generated from the live API and published with each release."],
      ["Guides", "Setup guides for agents, phone numbers and integrations are added as each feature launches."],
    ],
  },
  contact: {
    title: "Contact",
    lead: "Talk to the Xplosys team about XploVoice.",
    sections: [
      ["Sales and early access", "Ask your Xplosys contact for an early-access organization."],
      ["Security", "Report a security concern to your Xplosys contact. Please include steps to reproduce."],
    ],
  },
};

export function generateStaticParams() {
  return Object.keys(PAGES).map((slug) => ({ slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const p = PAGES[(await params).slug];
  return { title: p?.title ?? "Not found" };
}

export default async function MarketingPage({ params }: { params: Promise<{ slug: string }> }) {
  const page = PAGES[(await params).slug];
  if (!page) notFound();
  return (
    <div className="mx-auto max-w-4xl px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">{page.title}</h1>
      <p className="mt-3 text-lg text-slate-600">{page.lead}</p>
      <div className="mt-10 grid gap-6 sm:grid-cols-2">
        {page.sections.map(([t, d]) => (
          <div key={t} className="rounded-xl border border-slate-200 p-5">
            <h2 className="font-semibold">{t}</h2>
            <p className="mt-2 text-sm text-slate-600">{d}</p>
          </div>
        ))}
      </div>
      <Link href="/register" className="mt-10 inline-block font-medium text-brand-600 hover:underline">
        Create your organization →
      </Link>
    </div>
  );
}
