import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  BookMarked, Briefcase, Building2, CalendarClock, Calculator, CornerDownLeft, FilePlus2, FileText, Files, Fingerprint, Home, Landmark,
  LifeBuoy, Loader2, Moon, Palette, Plus, ScanSearch, Search, StickyNote, Sun, SunDim, Sunrise, Users,
} from "lucide-react";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { Marked, crore, day, titleCase } from "../lib/format";
import { recentlyOpened, THEMES, useDesk, type Theme } from "../lib/theme";

interface Item {
  id: string;
  group: string;
  label: ReactNode;
  hint?: ReactNode;
  icon: ReactNode;
  keywords?: string;
  run: () => void;
}

const GROUPS = ["Search", "Recently opened", "Documents", "Work", "Notes", "People and companies", "Company file", "Financial statements", "Resolutions", "Go to", "Create", "Theme"];
const THEME_ICON: Record<Theme, ReactNode> = { system: <Palette size={15} />, light: <Sun size={15} />, night: <SunDim size={15} />, dark: <Moon size={15} />, banaras: <Sunrise size={15} /> };

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Ctrl+K: one box that finds anything in AAGAM and goes anywhere. */
export default function CommandPalette({ open, onClose, setTheme }: { open: boolean; onClose: () => void; setTheme: (t: Theme) => void }) {
  const navigate = useNavigate();
  const desk = useDesk();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const term = useDebounced(q.trim(), 180);
  const { data, isFetching } = useQuery({
    queryKey: ["everything", term],
    queryFn: () => aagam.everything(term),
    enabled: open && term.length >= 2,
    placeholderData: (prev) => prev,
  });

  useEffect(() => {
    if (!open) {
      setQ("");
      setActive(0);
    }
  }, [open]);

  const go = (to: string) => () => {
    navigate(to);
    onClose();
  };

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    const words = q.trim().toLowerCase();
    const matches = (s: string) => !words || s.toLowerCase().includes(words);

    if (words) {
      out.push({ id: "search", group: "Search", icon: <Search size={15} />, label: <>Search every page for “{q.trim()}”</>, hint: "full text", run: go(`/search?q=${encodeURIComponent(q.trim())}`) });
      if (data?.looks_like && data.query === term && ["cin", "gstin", "din"].includes(data.looks_like)) {
        const kind = data.looks_like;
        const key = term.replace(/\s/g, "").toUpperCase();
        out.push({ id: "looks", group: "Search", icon: <Fingerprint size={15} />, label: <>That's a {kind.toUpperCase()}: open its dossier</>, hint: key, run: go(`/entities/${kind}/${encodeURIComponent(kind === "din" ? key.toLowerCase() : key)}`) });
      }
    } else {
      recentlyOpened().slice(0, 5).forEach((r) =>
        out.push({ id: `recent-${r.id}`, group: "Recently opened", icon: <FileText size={15} />, label: r.title, run: go(`/documents/${r.id}`) })
      );
    }

    if (data && words && data.query === term) {
      data.documents.forEach((d) =>
        out.push({
          id: `doc-${d.document_id}`, group: "Documents", icon: <FileText size={15} />,
          label: d.title || d.original_name,
          hint: d.passages[0] ? <Marked text={d.passages[0].text} /> : titleCase(d.doc_type),
          run: go(`/documents/${d.document_id}?page=${d.pages[0] ?? 1}&q=${encodeURIComponent(term.replace(/"/g, ""))}`),
        })
      );
      if (data.document_count > data.documents.length) {
        out.push({ id: "doc-more", group: "Documents", icon: <Files size={15} />, label: `All ${data.document_count} matching documents`, run: go(`/search?q=${encodeURIComponent(term)}`) });
      }
      data.works.forEach((w) =>
        out.push({ id: `work-${w.id}`, group: "Work", icon: <Briefcase size={15} />, label: w.title, hint: `${w.kind_label} · ${w.status}${w.company ? ` · ${w.company}` : ""}`, run: go(`/work/${w.id}`) })
      );
      data.notes.forEach((n) =>
        out.push({ id: `note-${n.id}`, group: "Notes", icon: <StickyNote size={15} />, label: n.snippet ? <Marked text={n.snippet} /> : n.text.slice(0, 120), run: go(noteHref(n.target_kind, n.target)) })
      );
      data.entities.slice(0, 8).forEach((e) =>
        out.push({
          id: `ent-${e.kind}-${e.key}`, group: "People and companies", icon: e.kind === "person" ? <Users size={15} /> : e.kind === "company" ? <Building2 size={15} /> : <Fingerprint size={15} />,
          label: e.name, hint: `${titleCase(e.kind)}${e.detail ? ` · ${e.detail}` : ""} · ${e.documents} document${e.documents === 1 ? "" : "s"}`,
          run: go(`/entities/${e.kind}/${encodeURIComponent(e.key)}`),
        })
      );
      data.companies.forEach((c) =>
        out.push({ id: `co-${c.id}`, group: "Company file", icon: <Building2 size={15} />, label: c.name, hint: c.cin ?? "client company", run: go(`/companies/${c.id}`) })
      );
      data.people.forEach((p) =>
        out.push({ id: `pp-${p.id}`, group: "Company file", icon: <Users size={15} />, label: p.name, hint: p.din ? `DIN ${p.din}` : "on file", run: go(`/entities/person/${encodeURIComponent(personKey(p.name))}`) })
      );
      data.financials.forEach((f) =>
        out.push({ id: `fin-${f.id}`, group: "Financial statements", icon: <Landmark size={15} />, label: f.company_name || f.client || "Financial statements", hint: `${titleCase(f.basis)}${f.period_end ? ` · year to ${day(f.period_end)}` : ""}`, run: go(`/financials/${f.id}`) })
      );
      data.resolutions.forEach((r) =>
        out.push({ id: `res-${r.id}`, group: "Resolutions", icon: <BookMarked size={15} />, label: r.title, hint: [r.company_name, r.max_amount ? crore(r.max_amount) : null, r.sections.slice(0, 2).map((s) => `s.${s}`).join(" ")].filter(Boolean).join(" · "), run: go(`/precedents?open=${r.id}`) })
      );
    }

    const pages: [string, string, ReactNode, string?][] = [
      ["Home", "/", <Home size={15} />],
      ["Work register", "/work", <Briefcase size={15} />, "tasks jobs agm board"],
      ["Clients", "/companies", <Building2 size={15} />, "company file directors kmp meetings charges"],
      ["Library", "/library", <Files size={15} />, "documents files"],
      ["Search", "/search", <Search size={15} />],
      ["Precedents", "/precedents", <BookMarked size={15} />, "resolutions"],
      ["Insights: what the documents say", "/insights", <ScanSearch size={15} />, "investments legal matters litigation law cited amendments obligations deadlines agreements register analysis"],
      ["Financial statements", "/financials", <Landmark size={15} />, "ratios balance sheet liabilities"],
      ["People and companies", "/entities", <Users size={15} />, "entities dossier din cin gstin"],
      ["Notes", "/notes", <StickyNote size={15} />],
      ["Calculators", "/calculators", <Calculator size={15} />, "186 180 185 loans limits"],
      ["Due dates", "/due", <CalendarClock size={15} />, "compliance calendar"],
      ["Help: what AAGAM does", "/help", <LifeBuoy size={15} />, "features guide shortcuts"],
    ];
    pages.forEach(([label, to, icon, kw]) => matches(`${label} ${kw ?? ""}`) && out.push({ id: `go-${to}`, group: "Go to", icon, label, run: go(to) }));
    if (matches("new work create task agm board")) out.push({ id: "new-work", group: "Create", icon: <Plus size={15} />, label: "New work", hint: "a meeting, filing, appointment, audit…", run: go("/work?new=1") });
    if (matches("new note write")) out.push({ id: "new-note", group: "Create", icon: <Plus size={15} />, label: "New note", run: go("/notes?new=1") });
    if (matches("add documents upload files")) out.push({ id: "add-docs", group: "Create", icon: <FilePlus2 size={15} />, label: "Add documents", hint: "or drop files anywhere", run: () => { onClose(); desk.openUpload(); } });
    THEMES.forEach((t) =>
      matches(`theme ${t.label} ${t.hint}`) && out.push({ id: `theme-${t.key}`, group: "Theme", icon: THEME_ICON[t.key], label: `Theme: ${t.label}`, hint: t.hint, run: () => { setTheme(t.key); onClose(); } })
    );
    // When the words are the start of a place or an action ("work reg", "new no"), that comes first; otherwise the search does.
    const named = (item: Item) => typeof item.label === "string" && item.label.toLowerCase().replace(/^theme: /, "").startsWith(words);
    const jump = words.length >= 2 && out.some((i) => ["Go to", "Create", "Theme"].includes(i.group) && named(i));
    const rank = (item: Item) => (jump && ["Go to", "Create", "Theme"].includes(item.group) && named(item) ? -1 : GROUPS.indexOf(item.group));
    return out.sort((a, b) => rank(a) - rank(b));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, data, term]);

  useEffect(() => setActive(0), [q, data]);
  useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); items[active]?.run(); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4" onMouseDown={onClose}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[3px] fade-in" />
      <div
        role="dialog"
        aria-label="Find anything"
        className="relative w-full max-w-2xl card overflow-hidden pop-in"
        style={{ boxShadow: "0 24px 60px rgb(var(--shadow) / 0.35)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 border-b border-bg-border">
          {isFetching ? <Loader2 size={17} className="text-text-muted animate-spin" /> : <Search size={17} className="text-text-muted" />}
          <input
            ref={input}
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey}
            placeholder="Find anything: a company, a DIN, a resolution, a note, a page… or go somewhere"
            className="flex-1 bg-transparent py-3.5 text-[15px] outline-none placeholder-text-muted"
            aria-label="What to find"
          />
          <kbd className="text-[11px] text-text-muted border border-bg-border rounded px-1.5 py-0.5">Esc</kbd>
        </div>
        <div ref={list} className="max-h-[60vh] overflow-auto py-1.5">
          {items.length === 0 && <p className="px-4 py-6 text-sm text-text-muted text-center">Nothing found.</p>}
          {items.map((item, index) => {
            const header = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            return (
              <div key={item.id}>
                {header && <p className="label px-4 pt-2.5 pb-1">{header}</p>}
                <button
                  data-index={index}
                  onMouseMove={() => setActive(index)}
                  onClick={item.run}
                  className={clsx("w-full flex items-center gap-3 px-4 py-2 text-left text-sm", index === active ? "bg-bg-hover" : "")}
                >
                  <span className={clsx("shrink-0", index === active ? "text-accent-brand" : "text-text-muted")}>{item.icon}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{item.label}</span>
                    {item.hint && <span className="block truncate text-xs text-text-muted">{item.hint}</span>}
                  </span>
                  {index === active && <CornerDownLeft size={13} className="text-text-muted shrink-0" />}
                </button>
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-4 px-4 py-2 border-t border-bg-border text-[11px] text-text-muted">
          <span><kbd className="font-sans">↑↓</kbd> move</span>
          <span><kbd className="font-sans">Enter</kbd> open</span>
          <span className="ml-auto">Searches documents, work, notes, people, companies, statements and resolutions</span>
        </div>
      </div>
    </div>
  );
}

export function noteHref(kind: string, target: string): string {
  switch (kind) {
    case "document": return `/documents/${target}`;
    case "work": return `/work/${target}`;
    case "financials": return `/financials/${target}`;
    case "entity": {
      const [k, ...rest] = target.split(":");
      return `/entities/${k}/${encodeURIComponent(rest.join(":"))}`;
    }
    case "company": return `/companies/${target}`;
    case "resolution": return `/precedents?open=${target}`;
    default: return "/notes";
  }
}

/** The same key the server groups people under: no titles, lower case, letters only. */
export function personKey(name: string): string {
  return name.trim().replace(/^(mr|ms|mrs|miss|shri|smt|sri|kum|dr|ca|cs|adv)\.?\s+/i, "").toLowerCase().replace(/[^a-z]+/g, " ").trim();
}
