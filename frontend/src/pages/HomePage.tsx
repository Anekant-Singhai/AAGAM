import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowRight, CalendarClock, FilePlus2, FileText, LifeBuoy, Pin, Plus, X } from "lucide-react";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { ago, day, daysTo, titleCase } from "../lib/format";
import { recentlyOpened, useDesk, usePreference } from "../lib/theme";
import { NoteItem } from "../components/NotesPanel";
import { CountUp, PageSkeleton, Progress, Tabs } from "../components/ui";

function greeting(banaras: boolean): string {
  const h = new Date().getHours();
  if (banaras) return h < 12 ? "Suprabhat" : h < 17 ? "Namaskar" : "Shubh sandhya";
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function HomePage() {
  const navigate = useNavigate();
  const desk = useDesk();
  const queryClient = useQueryClient();
  const [welcomed, setWelcomed] = usePreference("aagam.welcomed", false);
  const [recentTab, setRecentTab] = useState<"added" | "opened">("added");
  const { data } = useQuery({ queryKey: ["overview"], queryFn: aagam.overview, refetchInterval: 20_000 });

  if (!data) return <PageSkeleton />;
  const { stats, due, due_count, recent, works, works_open, pinned } = data;
  const overdue = due.filter((d) => d.state === "overdue").length;
  const late = works.filter((w) => (daysTo(w.due_on) ?? 1) < 0).length;
  const opened = recentlyOpened().slice(0, 8);

  const summary = [
    works_open ? `${works_open} job${works_open === 1 ? "" : "s"} in hand${late ? `, ${late} late` : ""}` : "nothing in hand",
    overdue ? `${overdue} filing${overdue === 1 ? "" : "s"} overdue` : null,
    due_count - overdue > 0 ? `${due_count - overdue} due in the next 30 days` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div className="px-8 py-7 max-w-[880px]">
      <div className="flex items-end gap-3 flex-wrap mb-6">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-text-muted">{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
          <h1 className="flourish text-[2rem] leading-tight font-semibold mt-0.5">{greeting(desk.theme === "banaras")}</h1>
          <p className="text-text-secondary mt-1">{summary.charAt(0).toUpperCase() + summary.slice(1)}.</p>
        </div>
        <Link to="/work?new=1" className="btn"><Plus size={14} /> New work</Link>
        <button className="btn btn-primary" onClick={() => desk.openUpload()}><FilePlus2 size={14} /> Add documents</button>
      </div>

      {!welcomed && (
        <div className="card p-4 mb-5 flex items-center gap-4 pop-in border-accent-brand/30">
          <span className="w-10 h-10 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0"><LifeBuoy size={20} /></span>
          <div className="flex-1 min-w-0">
            <p className="font-medium">New here? See everything AAGAM does, in two minutes.</p>
            <p className="text-sm text-text-muted">Press <kbd className="kbd">?</kbd> on any page for help with that page, and <kbd className="kbd">Ctrl K</kbd> to find anything.</p>
          </div>
          <Link to="/help" className="btn btn-primary" onClick={() => setWelcomed(true)}>Take the tour <ArrowRight size={14} /></Link>
          <button className="btn btn-ghost px-1.5" onClick={() => setWelcomed(true)} aria-label="Dismiss"><X size={15} /></button>
        </div>
      )}

      <div className="space-y-5">
        <section className="card">
          <div className="flex items-center gap-2 px-5 pt-4 pb-2">
            <p className="label flex-1">Work in hand</p>
            <Link to="/work" className="text-xs text-accent-brand hover:underline">All work</Link>
          </div>
          {works.length === 0 ? (
            <p className="px-5 pb-5 text-sm text-text-muted leading-6">Nothing open. <Link to="/work?new=1" className="text-accent-brand underline">Start a piece of work</Link> and AAGAM lays out its checklist, with the law behind each step.</p>
          ) : (
            <ul className="stagger pb-2">
              {works.map((w) => {
                const left = daysTo(w.due_on);
                return (
                  <li key={w.id}>
                    <button onClick={() => navigate(`/work/${w.id}`)} className="w-full text-left px-5 py-2.5 flex items-center gap-4 hover:bg-bg-hover/70 transition-colors">
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium truncate">{w.title}</span>
                        <span className="block text-xs text-text-muted truncate">{w.kind_label}{w.status === "waiting" ? " · waiting on someone" : ""}</span>
                      </span>
                      <span className="w-28 shrink-0"><Progress done={w.progress.done} total={w.progress.total} /></span>
                      <span className={clsx("w-20 text-right text-xs shrink-0", left !== null && left < 0 ? "text-accent-red font-medium" : left !== null && left <= 7 ? "text-accent-amber font-medium" : "text-text-muted")}>
                        {w.due_on && left !== null ? (left < 0 ? `${-left}d late` : left === 0 ? "due today" : `in ${left}d`) : ""}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="card">
          <div className="flex items-center px-5 pt-4 pb-2">
            <p className="label flex-1">Coming up</p>
            <Link to="/due" className="text-xs text-accent-brand hover:underline">Calendar</Link>
          </div>
          {due.length === 0 && <p className="px-5 pb-5 text-sm text-text-muted">Nothing due in the next 30 days for the companies on file.</p>}
          <ul className="stagger pb-3 grid md:grid-cols-2">
            {due.slice(0, 7).map((d) => (
              <li key={`${d.company_id}-${d.trigger}-${d.form}`} className="flex items-start gap-3 px-5 py-2">
                <span className={clsx("mt-0.5 w-11 shrink-0 rounded-lg border text-center leading-none py-1", d.state === "overdue" ? "border-accent-red/40 text-accent-red" : "border-bg-border text-text-secondary")}>
                  <span className="block text-[15px] font-semibold tabular">{d.due.slice(8, 10)}</span>
                  <span className="block text-[9.5px] uppercase tracking-wider mt-0.5">{new Date(d.due).toLocaleDateString("en-IN", { month: "short" })}</span>
                </span>
                <span className="min-w-0 text-sm">
                  <span className="block truncate"><span className="font-medium">{d.form}</span> · {d.company}</span>
                  <span className={clsx("block text-xs truncate", d.state === "overdue" ? "text-accent-red" : "text-text-muted")}>
                    {d.state === "overdue" ? <><AlertTriangle size={11} className="inline -mt-0.5" /> overdue</> : `in ${d.days_left} days`} · {d.law}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {pinned.length > 0 && (
        <section className="mt-5">
          <p className="label mb-2 flex items-center gap-1.5"><Pin size={11} /> Pinned</p>
          <ul className="grid md:grid-cols-2 gap-3 stagger">
            {pinned.map((n) => <NoteItem key={n.id} note={n} onChange={() => queryClient.invalidateQueries({ queryKey: ["overview"] })} />)}
          </ul>
        </section>
      )}

      <section className="card mt-5">
        <div className="flex items-center px-5 pt-2">
          <Tabs
            value={recentTab}
            onChange={setRecentTab}
            className="border-b-0 flex-1"
            tabs={[{ key: "added", label: "Recently added" }, { key: "opened", label: "Opened lately", count: opened.length }]}
          />
          <Link to="/library" className="text-xs text-accent-brand hover:underline">Library</Link>
        </div>
        <ul key={recentTab} className="px-3 pb-3 grid md:grid-cols-2 gap-x-4 stagger">
          {(recentTab === "added" ? recent.map((d) => ({ id: d.id, title: d.title || d.original_name, hint: titleCase(d.doc_type) })) : opened.map((o) => ({ id: o.id, title: o.title, hint: ago(o.at) }))).map((r) => (
            <li key={r.id}>
              <button onClick={() => navigate(`/documents/${r.id}`)} className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg text-left hover:bg-bg-hover/70">
                <FileText size={14} className="text-text-muted shrink-0" />
                <span className="text-sm truncate flex-1">{r.title}</span>
                <span className="text-xs text-text-muted shrink-0">{r.hint}</span>
              </button>
            </li>
          ))}
          {recentTab === "added" && recent.length === 0 && <li className="px-2 py-3 text-sm text-text-muted">Nothing yet. Drop files anywhere in this window.</li>}
          {recentTab === "opened" && opened.length === 0 && <li className="px-2 py-3 text-sm text-text-muted">Documents you open appear here.</li>}
        </ul>
      </section>

      <p className="mt-6 text-xs text-text-muted flex flex-wrap gap-x-4 gap-y-1">
        <Link to="/library" className="hover:text-text-primary"><b className="tabular text-text-secondary"><CountUp value={stats.documents} /></b> documents, <CountUp value={stats.pages} /> pages</Link>
        <Link to="/precedents" className="hover:text-text-primary"><b className="tabular text-text-secondary"><CountUp value={stats.resolutions} /></b> resolutions on file</Link>
        <Link to="/financials" className="hover:text-text-primary"><b className="tabular text-text-secondary"><CountUp value={stats.financials ?? 0} /></b> sets of accounts read</Link>
        <span><b className="tabular text-text-secondary">{stats.companies}</b> client compan{stats.companies === 1 ? "y" : "ies"}</span>
        <span className="flex items-center gap-1"><CalendarClock size={11} /> {due_count} due in 30 days</span>
      </p>
    </div>
  );
}
