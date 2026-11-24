// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Small shadcn/ui-style primitives (Tailwind). Kept local so the app has no runtime UI dependency.
import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function Button({ className, variant = "primary", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:opacity-50",
        variant === "primary" && "bg-brand-600 text-white hover:bg-brand-700",
        variant === "secondary" && "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700",
        variant === "ghost" && "text-slate-700 hover:bg-slate-100",
        className,
      )}
      {...p}
    />
  );
}

export function Input({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn("w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm",
        "focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500", className)}
      {...p}
    />
  );
}

export function Select({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm",
        "focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500", className)}
      {...p}
    />
  );
}

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-slate-700">{children}</label>;
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-xl border border-slate-200 bg-white p-6 shadow-sm", className)}>{children}</div>;
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "brand" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700", green: "bg-emerald-50 text-emerald-700", amber: "bg-amber-50 text-amber-800",
    red: "bg-red-50 text-red-700", brand: "bg-brand-50 text-brand-700",
  };
  return <span className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function FormError({ message }: { message?: string | null }) {
  if (!message) return null;
  return <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p>;
}

export function Notice({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">{children}</p>;
}
