// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import type { ReactNode } from "react";
import { Copyright, Logo } from "@/components/brand";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 py-12">
      <div className="mb-8"><Logo /></div>
      <div className="w-full max-w-md">{children}</div>
      <div className="mt-10"><Copyright /></div>
    </div>
  );
}
