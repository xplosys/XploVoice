// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import { redirect } from "next/navigation";
import { can, getMe } from "@/lib/me";
import { Notice } from "@/components/ui";
import { Playground } from "@/components/forms/ai-playground";

export const metadata = { title: "AI playground · XploVoice" };

export default async function PlaygroundPage() {
  const me = await getMe();
  if (!can(me, "ai:test")) redirect("/app");
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold">AI playground</h1>
        <p className="text-sm text-slate-600">Try your routed models before building agents. Every run is metered like a real call, and nothing you type is stored.</p></div>
      <Notice>Use test content only. Do not enter patient or other personal information here.</Notice>
      <Playground />
    </div>
  );
}
