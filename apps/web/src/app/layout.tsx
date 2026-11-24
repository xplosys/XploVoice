// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "XploVoice — Intelligent Conversations. Automated Business.", template: "%s · XploVoice" },
  description: "AI voice agents for businesses in India and the United States, by Xplosys.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
