// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
import type { Metadata } from "next";
import "@fontsource-variable/dm-sans";
import "./globals.css";
import "./theme.css";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";

export const metadata: Metadata = {
  title: { default: "XploVoice — Intelligent Conversations. Automated Business.", template: "%s · XploVoice" },
  description: "AI voice agents for businesses in India and the United States, by Xplosys.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The boot script sets data-mode and data-theme on <html> before paint (see lib/theme.ts).
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} /></head>
      <body>{children}</body>
    </html>
  );
}
