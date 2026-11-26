// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
// Dates are formatted in the viewer's own time zone. The server renders in UTC, so the first paint shows UTC with
// a label and the browser replaces it with local time once loaded.
import { useEffect, useState } from "react";

export function When({ iso, time }: { iso: string; time?: boolean }) {
  const d = new Date(iso);
  const utc = time ? `${d.toISOString().slice(11, 19)} UTC` : `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
  const [text, setText] = useState(utc);
  useEffect(() => setText(time ? d.toLocaleTimeString() : d.toLocaleString()), [iso, time]); // eslint-disable-line react-hooks/exhaustive-deps
  return <time dateTime={iso} suppressHydrationWarning>{text}</time>;
}
