import { Fragment, ReactNode } from "react";
import clsx from "clsx";
import { CalendarClock, CheckCircle2, CircleDot, FileDiff, Gavel, Handshake, HelpCircle, Scale, ScanSearch, TrendingUp } from "lucide-react";
import { crore, day } from "../lib/format";
import { tagClass, type InsightColumn, type InsightItem } from "../types";

/** One icon per purpose, the same everywhere. */
export function KindIcon({ kind, size = 16 }: { kind: string; size?: number }) {
  const Icon = { investments: TrendingUp, legal: Gavel, law: Scale, amendments: FileDiff, obligations: CalendarClock, agreements: Handshake }[kind] ?? ScanSearch;
  return <Icon size={size} />;
}

/** A value shown as its column says: money in crore, dates as days, lists as chips, long text clamped. */
export function Cell({ value, type, compact = false }: { value: unknown; type: InsightColumn["type"]; compact?: boolean }) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) return <span className="text-text-muted">—</span>;
  switch (type) {
    case "money": {
      const n = typeof value === "number" ? value : Number(value);
      return <span className="tabular whitespace-nowrap">{Number.isFinite(n) ? crore(n) : String(value)}</span>;
    }
    case "date":
      return <span className="tabular whitespace-nowrap">{day(String(value))}</span>;
    case "number":
      return <span className="tabular">{typeof value === "number" ? value.toLocaleString("en-IN") : String(value)}</span>;
    case "list": {
      const list = Array.isArray(value) ? value.map(String) : String(value).split(/\s*[,;]\s*/).filter(Boolean);
      const shown = compact ? list.slice(0, 3) : list.slice(0, 8);
      return (
        <span className="inline-flex flex-wrap gap-1">
          {shown.map((v) => <span key={v} className={clsx("chip", tagClass(v))}>{v}</span>)}
          {list.length > shown.length && <span className="chip bg-bg-hover text-text-muted" title={list.slice(shown.length).join(", ")}>+{list.length - shown.length}</span>}
        </span>
      );
    }
    case "long": {
      const text = String(value);
      return <span className={clsx(compact ? "line-clamp-2" : "line-clamp-3 max-w-md")} title={text}>{text}</span>;
    }
    default:
      return <span>{Array.isArray(value) ? value.join(", ") : String(value)}</span>;
  }
}

/** How sure the reading is: an icon and a word, never colour alone. */
export function Confidence({ value, showLabel = true }: { value: number | null | undefined; showLabel?: boolean }) {
  const v = value ?? 0;
  const s = v >= 0.75
    ? { Icon: CheckCircle2, cls: "text-accent-green", label: "Clear" }
    : v >= 0.5
      ? { Icon: CircleDot, cls: "text-accent-blue", label: "Likely" }
      : { Icon: HelpCircle, cls: "text-accent-amber", label: "Check" };
  return (
    <span className={clsx("inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap", s.cls)} title={`${s.label}: read with ${Math.round(v * 100)}% confidence`}>
      <s.Icon size={13} aria-hidden />
      {showLabel ? s.label : <span className="sr-only">{s.label}</span>}
    </span>
  );
}

/** The words of an item (and her search) marked in the sentence it came from. */
export function markItem(context: string, item: InsightItem, columns: InsightColumn[], query = ""): ReactNode {
  const words = new Set<string>();
  for (const c of columns) {
    if (c.type === "money" || c.type === "date" || c.type === "number") continue;
    const v = item[c.key];
    const values = Array.isArray(v) ? v.map(String) : typeof v === "string" ? [v] : [];
    values.map((x) => x.replace(/^[.…\s]+|[.…\s]+$/g, "")).forEach((x) => x.length >= 3 && x.length <= 160 && words.add(x));
  }
  (query.match(/[\p{L}\p{N}.]{2,}/gu) ?? []).forEach((w) => words.add(w));
  if (!words.size) return context;
  const escaped = [...words].sort((a, b) => b.length - a.length).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  return context.split(pattern).map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : <Fragment key={i}>{part}</Fragment>));
}

/** How much a document is about a purpose: a small bar with its figure. */
export function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  return (
    <span className="inline-flex items-center gap-1.5" title={`How much the document is about this: ${pct}%`}>
      <span className="h-1.5 w-16 rounded-full bg-bg-hover overflow-hidden">
        <span className="block h-full rounded-full bg-accent-brand grow-x" style={{ width: `${pct}%` }} />
      </span>
      <span className="text-[11px] text-text-muted tabular">{pct}%</span>
    </span>
  );
}
