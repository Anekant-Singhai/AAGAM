import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Briefcase, CalendarClock, FileText, Plus, Search } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { ago, day, daysTo } from "../lib/format";
import { Empty, PageHeader, Progress } from "../components/ui";
import type { WorkRow } from "../types";

const TABS = [
  { key: "active", label: "In hand" },
  { key: "done", label: "Done" },
  { key: "dropped", label: "Dropped" },
  { key: "all", label: "Everything" },
];

export default function WorkPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "active";
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(params.get("new") === "1");
  useEffect(() => setCreating(params.get("new") === "1" || creating), [params]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading } = useQuery({
    queryKey: ["works", tab, q],
    queryFn: () => aagam.works(tab === "active" || tab === "all" ? undefined : tab, q),
  });
  const works = (data?.works ?? []).filter((w) => tab !== "active" || w.status === "open" || w.status === "waiting");

  return (
    <div className="px-8 py-6 max-w-6xl">
      <PageHeader
        icon={<Briefcase size={18} />}
        title="Work register"
        subtitle="Every job in hand and done: its checklist with the law behind each step, its documents and notes."
        actions={<button className="btn btn-primary" onClick={() => setCreating(true)}><Plus size={14} /> New work</button>}
      />
      {creating && (
        <NewWork
          onClose={() => {
            setCreating(false);
            const next = new URLSearchParams(params);
            next.delete("new");
            setParams(next, { replace: true });
          }}
          onCreated={(id) => navigate(`/work/${id}`)}
        />
      )}

      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <div className="flex rounded-lg border border-bg-border bg-bg-secondary p-0.5" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setParams(t.key === "active" ? {} : { tab: t.key })}
              className={clsx("px-3 py-1 rounded-md text-sm", tab === t.key ? "bg-bg-surface shadow-sm font-medium text-text-primary" : "text-text-secondary hover:text-text-primary")}
            >
              {t.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 input py-1 w-72">
          <Search size={13} className="text-text-muted" />
          <input className="bg-transparent outline-none flex-1" placeholder="Find by title or company" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <span className="ml-auto text-sm text-text-muted">{data ? `${works.length} item${works.length === 1 ? "" : "s"}` : ""}</span>
      </div>

      {!isLoading && works.length === 0 ? (
        <Empty
          icon={<Briefcase size={18} />}
          title={tab === "active" ? "Nothing in hand." : "Nothing here."}
          hint="Start a piece of work (an AGM, a board meeting, an allotment, a charge, the annual filings) and AAGAM lays out its checklist, with the section or standard behind each step."
        />
      ) : (
        <div className="card divide-y divide-bg-border overflow-hidden stagger" key={tab}>
          {works.map((w) => <WorkLine key={w.id} work={w} onOpen={() => navigate(`/work/${w.id}`)} />)}
        </div>
      )}
    </div>
  );
}

function WorkLine({ work, onOpen }: { work: WorkRow; onOpen: () => void }) {
  const left = daysTo(work.due_on);
  const closed = work.status === "done" || work.status === "dropped";
  return (
    <button onClick={onOpen} className="w-full text-left px-4 py-3 flex items-center gap-4 hover:bg-bg-hover/70 transition-colors">
      <div className="min-w-0 flex-1">
        <p className={clsx("font-medium truncate", work.status === "dropped" && "line-through text-text-muted")}>{work.title}</p>
        <p className="text-xs text-text-muted truncate mt-0.5">
          {work.kind_label}
          {work.company && ` · ${work.company}`}
          {work.meeting_date && ` · meeting ${day(work.meeting_date)}`}
          {` · updated ${ago(work.updated_at)}`}
        </p>
      </div>
      {work.documents > 0 && (
        <span className="text-xs text-text-muted flex items-center gap-1 shrink-0" title="Documents attached"><FileText size={12} /> {work.documents}</span>
      )}
      <div className="w-36 shrink-0"><Progress done={work.progress.done} total={work.progress.total} /></div>
      <div className="w-36 shrink-0 text-right text-xs">
        {closed ? (
          <StatusChip status={work.status} />
        ) : work.due_on ? (
          <span className={clsx("inline-flex items-center gap-1", left !== null && left < 0 ? "text-accent-red font-medium" : left !== null && left <= 7 ? "text-accent-amber font-medium" : "text-text-secondary")}>
            {left !== null && left < 0 ? <AlertTriangle size={12} /> : <CalendarClock size={12} />}
            {day(work.due_on)}
            <span className="text-text-muted font-normal">{left === null ? "" : left < 0 ? ` (${-left}d late)` : left === 0 ? " (today)" : ` (${left}d)`}</span>
          </span>
        ) : (
          <StatusChip status={work.status} />
        )}
      </div>
    </button>
  );
}

export function StatusChip({ status }: { status: string }) {
  const looks: Record<string, string> = {
    open: "tag-0",
    waiting: "tag-2",
    done: "tag-1",
    dropped: "bg-bg-hover text-text-muted",
  };
  const words: Record<string, string> = { open: "In hand", waiting: "Waiting on someone", done: "Done", dropped: "Dropped" };
  return <span className={clsx("chip", looks[status])}>{words[status] ?? status}</span>;
}

function NewWork({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const queryClient = useQueryClient();
  const { data: kinds } = useQuery({ queryKey: ["work-kinds"], queryFn: aagam.workKinds, staleTime: Infinity });
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies() });
  const [kind, setKind] = useState("agm");
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [touched, setTouched] = useState(false);
  const [meeting, setMeeting] = useState("");
  const [due, setDue] = useState("");

  // Suggest a title from the kind and company until she types her own.
  useEffect(() => {
    if (touched) return;
    const label = kinds?.kinds[kind] ?? "";
    const name = companies?.companies.find((c) => String(c.id) === company)?.name;
    const year = (meeting || new Date().toISOString()).slice(0, 4);
    setTitle([label === "Other work" ? "" : label, ["agm", "board_meeting", "egm"].includes(kind) ? year : "", name ? `· ${name}` : ""].filter(Boolean).join(" "));
  }, [kind, company, meeting, kinds, companies, touched]);

  const create = useMutation({
    mutationFn: () => aagam.createWork({ title, kind, company: company || undefined, meeting_date: meeting || undefined, due_on: due || undefined }),
    onSuccess: (w) => {
      queryClient.invalidateQueries({ queryKey: ["works"] });
      toast.success("Work started, with its checklist.");
      onCreated(w.id);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <form
      className="card p-4 mb-5 grid md:grid-cols-2 gap-3 animate-fade-in"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <label className="block">
        <span className="label">Kind of work</span>
        <select className="input w-full mt-1" value={kind} onChange={(e) => setKind(e.target.value)}>
          {Object.entries(kinds?.kinds ?? {}).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      </label>
      <label className="block">
        <span className="label">Company</span>
        <select className="input w-full mt-1" value={company} onChange={(e) => setCompany(e.target.value)}>
          <option value="">Not for one company</option>
          {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
        </select>
      </label>
      <label className="block md:col-span-2">
        <span className="label">Title</span>
        <input className="input w-full mt-1" value={title} onChange={(e) => { setTitle(e.target.value); setTouched(true); }} placeholder="e.g. AGM 2026 · Acme Widgets" required />
      </label>
      <label className="block">
        <span className="label">Meeting date (if a meeting)</span>
        <input type="date" className="input w-full mt-1" value={meeting} onChange={(e) => setMeeting(e.target.value)} />
      </label>
      <label className="block">
        <span className="label">Due by</span>
        <input type="date" className="input w-full mt-1" value={due} onChange={(e) => setDue(e.target.value)} />
      </label>
      <div className="md:col-span-2 flex items-center gap-2">
        <button className="btn btn-primary" disabled={create.isPending || !title.trim()}>Start this work</button>
        <button type="button" className="btn" onClick={onClose}>Cancel</button>
        <span className="text-xs text-text-muted ml-auto">The checklist can be changed afterwards: add, remove or note against any step.</span>
      </div>
    </form>
  );
}
