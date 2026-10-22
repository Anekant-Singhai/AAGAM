import { Link } from "react-router-dom";
import {
  BookMarked, Bot, Briefcase, Building2, CalendarClock, Calculator, ClipboardCheck, Command, FilePen, Files, Globe, Landmark, LifeBuoy, Lock, ScanSearch, Search,
  ShieldCheck, Sparkles, StickyNote, Trash2, Users,
} from "lucide-react";
import clsx from "clsx";
import { GROUPS, POWER, SHORTCUTS, type Power } from "../lib/help";

export const HELP_ICONS: Record<string, React.ReactNode> = {
  files: <Files size={18} />, command: <Command size={18} />, search: <Search size={18} />, users: <Users size={18} />,
  note: <StickyNote size={18} />, briefcase: <Briefcase size={18} />, book: <BookMarked size={18} />, check: <ClipboardCheck size={18} />,
  calendar: <CalendarClock size={18} />, globe: <Globe size={18} />, landmark: <Landmark size={18} />, calculator: <Calculator size={18} />,
  bot: <Bot size={18} />, sparkles: <Sparkles size={18} />, building: <Building2 size={18} />, pen: <FilePen size={18} />, trash: <Trash2 size={18} />,
  scan: <ScanSearch size={18} />,
};

export function PowerBadge({ power }: { power: Power }) {
  const looks: Record<Power, string> = { rules: "tag-1", local: "tag-0", claude: "tag-3" };
  return <span className={clsx("chip", looks[power])} title={POWER[power].hint}>{POWER[power].label}</span>;
}

export default function HelpPage() {
  return (
    <div className="p-6 max-w-6xl">
      <div className="card p-6 mb-6 overflow-hidden relative">
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-2xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0"><LifeBuoy size={22} /></div>
          <div className="flex-1">
            <h1 className="text-2xl font-semibold">What AAGAM does</h1>
            <p className="text-text-secondary mt-1 max-w-3xl leading-6">
              AAGAM keeps your documents and your clients' records, reads what comes in, finds anything, lays out each job with the law behind it,
              reads the accounts and tests them against the thresholds. You decide, sign and file; AAGAM never submits, signs or pays.
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              {(Object.keys(POWER) as Power[]).map((p) => (
                <span key={p} className="flex items-center gap-1.5 text-xs text-text-secondary"><PowerBadge power={p} /> {POWER[p].hint}</span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_300px] gap-6 items-start">
        <div className="space-y-8">
          {GROUPS.map((g) => (
            <section key={g.title}>
              <h2 className="display text-lg font-semibold">{g.title}</h2>
              <p className="text-sm text-text-muted mb-3">{g.blurb}</p>
              <div className="grid md:grid-cols-2 gap-3 stagger">
                {g.features.map((f) => (
                  <article key={f.key} id={f.key} className="card p-4 flex flex-col">
                    <div className="flex items-start gap-3">
                      <span className="w-9 h-9 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0">{HELP_ICONS[f.icon]}</span>
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold">{f.title}</p>
                        <p className="text-sm text-text-secondary leading-6 mt-0.5">{f.what}</p>
                      </div>
                    </div>
                    <ul className="mt-3 space-y-1.5 text-sm text-text-secondary leading-6 list-disc pl-5 marker:text-text-muted">
                      {f.how.map((h, i) => <li key={i}>{h}</li>)}
                    </ul>
                    <div className="mt-auto pt-3 flex items-center gap-1.5 flex-wrap">
                      {f.power.map((p) => <PowerBadge key={p} power={p} />)}
                      {!f.to.startsWith("/help") && <Link to={f.to} className="ml-auto text-xs font-medium text-accent-brand hover:underline">Open →</Link>}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-4">
          <section className="card p-4">
            <p className="label mb-2">Keyboard</p>
            <dl className="space-y-2 text-sm">
              {SHORTCUTS.map(([keys, what]) => (
                <div key={keys} className="flex items-center gap-3">
                  <dt className="w-[88px] shrink-0 flex gap-1">{keys.split(" ").map((k) => <kbd key={k} className="kbd">{k}</kbd>)}</dt>
                  <dd className="text-text-secondary">{what}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="card p-4 text-sm space-y-2">
            <p className="label flex items-center gap-1.5"><ShieldCheck size={12} /> Safe by design</p>
            <p className="text-text-secondary leading-6 flex gap-2"><Lock size={14} className="mt-1 shrink-0" /> It answers only this computer, and your data stays in your AAGAM folder.</p>
            <p className="text-text-secondary leading-6">PAN, Aadhaar and passport numbers are masked in everything AAGAM shows or tells Claude.</p>
            <p className="text-text-secondary leading-6">You log in to MCA yourself. Nothing is ever submitted, signed or paid for you.</p>
            <p className="text-text-secondary leading-6">Your own figures, tags and summaries are never overwritten.</p>
          </section>
          <section className="card p-4 text-sm">
            <p className="label mb-2">Look and feel</p>
            <p className="text-text-secondary leading-6">The icon at the right of the top bar chooses the theme: Light, Night light (warm, for late reading), Dark, or Banaras ghat (maroon silk and zari, with the ghats at dawn along the foot of the page). It also turns the background drawings on or off.</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
