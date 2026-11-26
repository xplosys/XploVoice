// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"use client";
import { Check, Monitor, Moon, Palette, Sun } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { applyAppearance, DARK_THEMES, DEFAULT_THEME, MODE_KEY, THEME_KEY, type Mode } from "@/lib/theme";

function read(key: string, fallback: string) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function write(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* private window: applies for this page only */ }
}

const MODES: { id: Mode; label: string; Icon: typeof Sun }[] = [
  { id: "light", label: "Light", Icon: Sun }, { id: "dark", label: "Dark", Icon: Moon }, { id: "system", label: "System", Icon: Monitor },
];

/** Header button that opens the appearance menu: light, dark or system mode, and the dark theme. */
export function ThemePicker() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("light");
  const [theme, setTheme] = useState(DEFAULT_THEME);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMode(read(MODE_KEY, "light") as Mode);
    setTheme(read(THEME_KEY, DEFAULT_THEME));
  }, []);

  // Follow the operating system while in System mode.
  useEffect(() => {
    if (mode !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyAppearance("system", theme);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [mode, theme]);

  useEffect(() => {
    if (!open) return;
    const click = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", click);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", click); document.removeEventListener("keydown", key); };
  }, [open]);

  function choose(nextMode: Mode, nextTheme: string) {
    setMode(nextMode); setTheme(nextTheme);
    write(MODE_KEY, nextMode); write(THEME_KEY, nextTheme);
    applyAppearance(nextMode, nextTheme);
  }

  return (
    <div ref={box} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog" aria-label="Appearance"
        className="xv-icon-btn inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100">
        <Palette className="h-4 w-4" aria-hidden /><span className="hidden sm:inline">Appearance</span>
      </button>
      {open && (
        <div role="dialog" aria-label="Appearance"
          className="xv-menu absolute right-0 z-50 mt-2 w-72 rounded-xl border border-slate-200 bg-white p-4 shadow-lg">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Mode</p>
          <div role="radiogroup" aria-label="Mode" className="xv-segment mb-4 grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
            {MODES.map(({ id, label, Icon }) => (
              <button key={id} type="button" role="radio" aria-checked={mode === id} onClick={() => choose(id, theme)}
                className={cn("flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-sm",
                  mode === id ? "xv-segment-on bg-white font-medium text-slate-900 shadow-sm" : "text-slate-600")}>
                <Icon className="h-4 w-4" aria-hidden />{label}
              </button>
            ))}
          </div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Dark theme</p>
          <div role="radiogroup" aria-label="Dark theme" className="grid grid-cols-2 gap-2">
            {DARK_THEMES.map((t) => (
              <button key={t.id} type="button" role="radio" aria-checked={theme === t.id}
                onClick={() => choose(mode === "light" ? "dark" : mode, t.id)}
                className={cn("xv-swatch relative flex h-12 items-end rounded-lg px-2.5 py-1.5 text-left text-sm font-semibold text-white",
                  theme === t.id && "ring-2 ring-brand-500 ring-offset-2")}
                style={{ backgroundImage:
                  `linear-gradient(100deg, #1a191c 0%, #1b1a1e 30%, ${t.deep}aa 48%, ${t.sheen} 62%, ${t.deep} 78%, ${t.deep} 100%)` }}>
                {t.name}
                {theme === t.id && <Check className="absolute right-2 top-2 h-4 w-4" aria-hidden />}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">Picking a theme turns dark mode on. Saved in this browser.</p>
        </div>
      )}
    </div>
  );
}
