// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Appearance: light or dark mode, and the dark theme. Stored in the browser only (localStorage), applied to <html>
// as data-mode and data-theme before the page paints, so there is no flash of the wrong colours.

export type Mode = "light" | "dark" | "system";
export type DarkTheme = { id: string; name: string; deep: string; sheen: string };

/** Every dark theme has the same near-black to colour gradient with a diagonal sheen; only the hue changes. */
export const DARK_THEMES: DarkTheme[] = [
  { id: "violet", name: "Violet", deep: "#3f219a", sheen: "#6c4fb1" },
  { id: "indigo", name: "Indigo", deep: "#1f2f9c", sheen: "#5068cf" },
  { id: "orchid", name: "Orchid", deep: "#7a1f86", sheen: "#b75cc0" },
  { id: "ocean", name: "Ocean", deep: "#0d5a72", sheen: "#3d9fba" },
  { id: "ember", name: "Ember", deep: "#8a1f3c", sheen: "#d0607a" },
  { id: "emerald", name: "Emerald", deep: "#0f6248", sheen: "#3fae86" },
];

export const MODE_KEY = "xv-mode";
export const THEME_KEY = "xv-theme";
export const DEFAULT_THEME = "violet";

/** Runs inline in <head> before first paint. Must stay self-contained (no imports). */
export const THEME_BOOT_SCRIPT = `(function(){try{
var d=document.documentElement,m=localStorage.getItem("${MODE_KEY}")||"light",t=localStorage.getItem("${THEME_KEY}")||"${DEFAULT_THEME}";
var ok=${JSON.stringify(DARK_THEMES.map((t) => t.id))};if(ok.indexOf(t)<0)t="${DEFAULT_THEME}";
var dark=m==="dark"||(m==="system"&&window.matchMedia("(prefers-color-scheme: dark)").matches);
d.dataset.mode=dark?"dark":"light";d.dataset.theme=t;
}catch(e){}})();`;

export function applyAppearance(mode: Mode, theme: string) {
  const d = document.documentElement;
  const dark = mode === "dark" || (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  d.dataset.mode = dark ? "dark" : "light";
  d.dataset.theme = theme;
}
