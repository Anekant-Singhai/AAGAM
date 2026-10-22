import { createContext, useContext, useEffect, useState } from "react";
import type { UploadItem } from "../api/aagam";

export type Theme = "system" | "light" | "night" | "dark" | "banaras";
export const THEMES: { key: Theme; label: string; hint: string }[] = [
  { key: "system", label: "Follow Windows", hint: "Light by day, dark when Windows is dark" },
  { key: "light", label: "Light", hint: "Clean paper white" },
  { key: "night", label: "Night light", hint: "Warm and low in blue light, for reading late" },
  { key: "dark", label: "Dark", hint: "Dark grey" },
  { key: "banaras", label: "Banaras ghat", hint: "Banarasi silk and zari, the ghats at dawn" },
];
const KEY = "aagam.theme";

function read<T extends string>(key: string, fallback: T, allowed?: readonly T[]): T {
  try {
    const value = localStorage.getItem(key) as T | null;
    return value && (!allowed || allowed.includes(value)) ? value : fallback;
  } catch {
    return fallback;
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private window: the choice lasts for this visit */
  }
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => read(KEY, "system", THEMES.map((t) => t.key)));
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    write(KEY, theme);
  }, [theme]);
  // Colours glide from one theme to the next, for a moment only (so hovering stays instant).
  const change = (t: Theme) => {
    const root = document.documentElement;
    root.classList.add("theming");
    setTheme(t);
    window.setTimeout(() => root.classList.remove("theming"), 500);
  };
  return [theme, change];
}

/** A yes/no preference kept in this browser. */
export function usePreference(key: string, initial: boolean): [boolean, (v: boolean) => void] {
  const [value, setValue] = useState(() => read(key, initial ? "1" : "0") === "1");
  useEffect(() => write(key, value ? "1" : "0"), [key, value]);
  return [value, setValue];
}

/** What the shell offers every page: the upload box, the help panel, the find box, the art switch. */
export interface Desk {
  theme: Theme;
  /** Plain files, or files with their place inside a dropped folder. */
  openUpload: (files?: (File | UploadItem)[]) => void;
  openHelp: () => void;
  openPalette: () => void;
  art: boolean;
  setArt: (v: boolean) => void;
}
export const DeskContext = createContext<Desk>({ theme: "system", openUpload: () => {}, openHelp: () => {}, openPalette: () => {}, art: true, setArt: () => {} });
export const useDesk = () => useContext(DeskContext);

/** Documents she opened lately, kept in this browser only. */
const RECENT = "aagam.recent";
export function rememberOpened(entry: { id: number; title: string }) {
  try {
    const list: { id: number; title: string; at: string }[] = JSON.parse(localStorage.getItem(RECENT) ?? "[]");
    const next = [{ ...entry, at: new Date().toISOString() }, ...list.filter((e) => e.id !== entry.id)].slice(0, 12);
    localStorage.setItem(RECENT, JSON.stringify(next));
  } catch {
    /* ignore */
  }
}
export function recentlyOpened(): { id: number; title: string; at: string }[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT) ?? "[]");
  } catch {
    return [];
  }
}
