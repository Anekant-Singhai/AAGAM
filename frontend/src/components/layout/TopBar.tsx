import { Check, FilePlus2, HelpCircle, Image, Moon, Palette, Search, Sun, SunDim, Sunrise } from "lucide-react";
import { ReactNode, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { aagam } from "../../api/aagam";
import { THEMES, useDesk, type Theme } from "../../lib/theme";

const ICONS: Record<Theme, ReactNode> = { system: <Palette size={16} />, light: <Sun size={16} />, night: <SunDim size={16} />, dark: <Moon size={16} />, banaras: <Sunrise size={16} /> };

export default function TopBar({ theme, setTheme }: { theme: Theme; setTheme: (t: Theme) => void }) {
  const desk = useDesk();
  const { data: ai } = useQuery({ queryKey: ["ai-status"], queryFn: aagam.aiStatus, refetchInterval: 15_000 });
  const queued = ai?.jobs?.queued ?? 0;
  const ready = Boolean(ai?.running && ai?.model_installed);
  const aiText = ai?.enabled === false ? "Local AI is off" : ready ? `Local AI ready${queued ? `, ${queued} waiting` : ""}` : "Local AI isn't running";

  return (
    <header className="topbar h-12 border-b border-bg-border bg-bg-secondary/75 backdrop-blur flex items-center px-4 gap-2 shrink-0 relative z-30">
      <button
        onClick={desk.openPalette}
        className="group flex-1 max-w-xl flex items-center gap-2 bg-bg-primary/70 border border-bg-border rounded-lg px-3 py-1.5 text-left hover:border-text-muted transition-colors"
        aria-label="Search documents"
      >
        <Search size={14} className="text-text-muted shrink-0 group-hover:text-accent-brand transition-colors" />
        <span className="text-sm text-text-muted flex-1 truncate">Search or jump to… a word, a company, a DIN, a note</span>
        <kbd className="kbd">Ctrl K</kbd>
      </button>
      <div className="flex-1" />
      <button className="btn btn-ghost py-1 text-text-secondary" onClick={() => desk.openUpload()} title="Add documents (or drop files anywhere)">
        <FilePlus2 size={15} /> <span className="hidden md:inline">Add documents</span>
      </button>
      <span title={ai?.message ?? aiText} className="flex items-center px-2" aria-label={aiText}>
        <span className={clsx("w-2 h-2 rounded-full", ready ? "bg-accent-green breathe" : "bg-text-muted/50")} />
        <span className="hidden xl:inline text-xs text-text-muted ml-1.5">{ready ? "AI ready" : "AI off"}</span>
      </span>
      <button className="btn btn-ghost px-2 py-1 text-text-secondary" onClick={desk.openHelp} aria-label="Help" title="Help for this page (?)">
        <HelpCircle size={16} />
      </button>
      <ThemeMenu theme={theme} setTheme={setTheme} />
    </header>
  );
}

function ThemeMenu({ theme, setTheme }: { theme: Theme; setTheme: (t: Theme) => void }) {
  const { art, setArt } = useDesk();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);
  const current = THEMES.find((t) => t.key === theme) ?? THEMES[0];

  return (
    <div ref={box} className="relative">
      <button className="btn btn-ghost px-2 py-1 text-text-secondary" onClick={() => setOpen(!open)} aria-label="Theme" aria-expanded={open} title={`Theme: ${current.label}`}>
        <span key={theme} className="pop-in inline-flex">{ICONS[theme]}</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full mt-1.5 w-72 card p-1.5 z-40 pop-in" style={{ boxShadow: "0 16px 40px rgb(var(--shadow) / 0.2)" }}>
          <p className="label px-2.5 pt-1.5 pb-1">Theme</p>
          {THEMES.map((t) => (
            <button
              key={t.key}
              role="menuitemradio"
              aria-checked={t.key === theme}
              onClick={() => { setTheme(t.key); setOpen(false); }}
              className={clsx("w-full flex items-start gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-bg-hover", t.key === theme && "bg-bg-hover")}
            >
              <ThemeSwatch theme={t.key} />
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-medium">{t.label}</span>
                <span className="block text-xs text-text-muted">{t.hint}</span>
              </span>
              {t.key === theme && <Check size={14} className="text-accent-brand mt-1" />}
            </button>
          ))}
          <div className="border-t border-bg-border mt-1.5 pt-1.5">
            <button
              role="menuitemcheckbox"
              aria-checked={art}
              onClick={() => setArt(!art)}
              className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-bg-hover"
            >
              <Image size={15} className="text-text-muted" />
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-medium">Background drawings</span>
                <span className="block text-xs text-text-muted">Justice, the ledger, the seal, the minute book; the ghats in Banaras</span>
              </span>
              <span className={clsx("w-8 h-[18px] rounded-full relative transition-colors", art ? "bg-accent-brand" : "bg-bg-border")}>
                <span className={clsx("absolute top-[2px] w-[14px] h-[14px] rounded-full bg-bg-surface shadow transition-all", art ? "left-[16px]" : "left-[2px]")} />
              </span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** A little picture of each theme: page, panel and accent colours. */
function ThemeSwatch({ theme }: { theme: Theme }) {
  const looks: Record<Theme, [string, string, string]> = {
    light: ["#f5f4f0", "#ffffff", "#1e5c8c"],
    night: ["#eee4cf", "#f7eedd", "#8a4b1f"],
    dark: ["#101217", "#1d2027", "#74b2e0"],
    system: ["#f5f4f0", "#1d2027", "#1e5c8c"],
    banaras: ["#f5ecda", "#701026", "#c49428"],
  };
  const [page, panel, accent] = looks[theme];
  return (
    <span className="w-9 h-7 rounded-md border border-bg-border overflow-hidden shrink-0 mt-0.5 relative" style={{ background: page }} aria-hidden>
      {theme === "system" && <span className="absolute inset-y-0 right-0 w-1/2" style={{ background: "#101217" }} />}
      {theme === "banaras" && <span className="absolute inset-y-0 left-0 w-2" style={{ background: "linear-gradient(#701026,#560a1c)", borderRight: "1.5px solid #c49428" }} />}
      <span className="absolute left-1 top-1 right-1 h-2 rounded-sm" style={{ background: panel, border: "1px solid rgba(0,0,0,0.08)" }} />
      <span className="absolute left-1 bottom-1 w-3 h-1.5 rounded-sm" style={{ background: accent }} />
    </span>
  );
}
