import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, FileText, MessageSquarePlus, Paperclip, Plus, Scale, Search, Trash2, X } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { day, titleCase } from "../lib/format";
import { Progress, Section } from "../components/ui";
import NotesPanel from "../components/NotesPanel";
import { MoreMenu, useConfirm } from "../components/dialogs";
import { StatusChip } from "./WorkPage";
import type { ChecklistStep, Work } from "../types";

export default function WorkDetailPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: work, error } = useQuery({ queryKey: ["work", id], queryFn: () => aagam.work(id) });
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies() });
  const confirm = useConfirm();

  const refresh = (w: Work) => {
    queryClient.setQueryData(["work", id], w);
    queryClient.invalidateQueries({ queryKey: ["works"] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
  };
  const change = useMutation({ mutationFn: (body: Record<string, unknown>) => aagam.changeWork(id, body), onSuccess: refresh, onError: (e: Error) => toast.error(e.message) });
  const save = useMutation({ mutationFn: (steps: ChecklistStep[]) => aagam.setChecklist(id, steps), onSuccess: refresh, onError: (e: Error) => toast.error(e.message) });

  if (error) return <p className="p-6 text-accent-red">{(error as Error).message}</p>;
  if (!work) return <p className="p-6 text-text-muted">Loading…</p>;

  const steps = work.checklist;
  const next = steps.findIndex((s) => !s.done);
  const update = (index: number, patch: Partial<ChecklistStep>) =>
    save.mutate(steps.map((s, i) => (i === index ? { ...s, ...patch } : s)));

  return (
    <div className="px-8 py-6 max-w-6xl">
      <div className="flex items-start gap-3 mb-5">
        <button onClick={() => navigate("/work")} className="text-text-muted hover:text-text-primary mt-1.5" aria-label="Back to work"><ArrowLeft size={16} /></button>
        <div className="flex-1 min-w-0">
          <EditableTitle value={work.title} onSave={(title) => change.mutate({ title })} />
          <p className="text-sm text-text-secondary mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{work.kind_label}</span>
            {work.company && <><span className="text-text-muted">·</span><Link className="hover:text-accent-brand" to={`/companies/${work.company_id}`}>{work.company}</Link></>}
            <span className="text-text-muted">·</span>
            <StatusChip status={work.status} />
          </p>
        </div>
        <select className="input" value={work.status} onChange={(e) => change.mutate({ status: e.target.value })} aria-label="Status">
          <option value="open">In hand</option>
          <option value="waiting">Waiting on someone</option>
          <option value="done">Done</option>
          <option value="dropped">Dropped</option>
        </select>
        <MoreMenu items={[{
          label: "Delete this work", icon: <Trash2 size={14} />, danger: true,
          onClick: async () => {
            const ok = await confirm({
              title: `Delete “${work.title}”?`,
              body: "Its checklist goes. The documents attached stay in the library. To keep it on record instead, mark it Done or Dropped.",
              items: work.notes.length ? [`Your ${work.notes.length} note${work.notes.length === 1 ? "" : "s"} on it are kept, as general notes`] : [],
              action: "Delete work",
              danger: true,
            });
            if (!ok) return;
            await aagam.deleteWork(id);
            queryClient.invalidateQueries({ queryKey: ["works"] });
            queryClient.invalidateQueries({ queryKey: ["overview"] });
            toast.success("Work deleted.");
            navigate("/work");
          },
        }]} />
      </div>

      <div className="grid lg:grid-cols-[1fr_340px] gap-5 items-start">
        <section className="card">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-bg-border">
            <p className="label flex-1">Checklist</p>
            <div className="w-48"><Progress done={work.progress.done} total={work.progress.total} /></div>
          </div>
          {steps.length === 0 && <p className="px-4 py-6 text-sm text-text-muted">No steps yet. Add the first one below.</p>}
          <ol className="stagger">
            {steps.map((step, index) => (
              <StepRow
                key={`${index}-${step.text}`}
                index={index}
                step={step}
                isNext={index === next}
                onToggle={() => update(index, { done: !step.done, done_at: step.done ? null : new Date().toISOString().slice(0, 16) })}
                onNote={(note) => update(index, { note })}
                onRemove={async () => {
                  if (await confirm({ title: "Remove this step?", body: step.text, action: "Remove step", danger: true })) save.mutate(steps.filter((_, i) => i !== index));
                }}
              />
            ))}
          </ol>
          <AddStep onAdd={(text) => save.mutate([...steps, { text, basis: null, done: false, done_at: null, note: null }])} />
        </section>

        <div className="space-y-4">
          <Section title="Details">
            <label className="block text-sm mb-2">
              <span className="text-xs text-text-muted">Company</span>
              <select className="input w-full mt-0.5" value={work.company_id ? String(work.company_id) : ""} onChange={(e) => change.mutate({ company: e.target.value || null })}>
                <option value="">Not for one company</option>
                {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <label className="block">
                <span className="text-xs text-text-muted">Meeting</span>
                <input type="date" className="input w-full mt-0.5" defaultValue={work.meeting_date ?? ""} onBlur={(e) => e.target.value !== (work.meeting_date ?? "") && change.mutate({ meeting_date: e.target.value || null })} />
              </label>
              <label className="block">
                <span className="text-xs text-text-muted">Due by</span>
                <input type="date" className="input w-full mt-0.5" defaultValue={work.due_on ?? ""} onBlur={(e) => e.target.value !== (work.due_on ?? "") && change.mutate({ due_on: e.target.value || null })} />
              </label>
            </div>
            <p className="text-xs text-text-muted mt-2">Started {day(work.created_at.slice(0, 10))}{work.closed_at ? ` · closed ${day(work.closed_at.slice(0, 10))}` : ""}</p>
          </Section>
          <Documents work={work} onChange={refresh} />
          <NotesPanel kind="work" target={String(work.id)} initial={work.notes} compact />
        </div>
      </div>
    </div>
  );
}

function EditableTitle({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return (
    <input
      className="display text-[1.6rem] leading-tight font-semibold bg-transparent w-full outline-none rounded px-1 -mx-1 hover:bg-bg-hover focus:bg-bg-secondary focus:ring-1 focus:ring-accent-brand"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => text.trim() && text !== value && onSave(text.trim())}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      aria-label="Title"
    />
  );
}

function StepRow({ index, step, isNext, onToggle, onNote, onRemove }: {
  index: number; step: ChecklistStep; isNext: boolean; onToggle: () => void; onNote: (note: string | null) => void; onRemove: () => void;
}) {
  const [noting, setNoting] = useState(false);
  const [note, setNote] = useState(step.note ?? "");
  return (
    <li className={clsx("group flex gap-3 px-4 py-3 border-b border-bg-border last:border-b-0", isNext && "bg-accent-brand/[0.04]")}>
      <button
        onClick={onToggle}
        role="checkbox"
        aria-checked={step.done}
        aria-label={`Step ${index + 1}`}
        className={clsx(
          "w-5 h-5 mt-0.5 rounded-md border flex items-center justify-center shrink-0 transition-colors",
          step.done ? "bg-accent-green border-accent-green text-on-accent" : "border-text-muted hover:border-accent-brand"
        )}
      >
        {step.done && <Check size={13} strokeWidth={3} className="tick" />}
      </button>
      <div className="flex-1 min-w-0">
        <p className={clsx("text-sm leading-6", step.done && "text-text-muted line-through decoration-text-muted/50")}>
          {isNext && <span className="chip tag-0 mr-2 align-[1px] no-underline">Next</span>}
          {step.text}
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-text-muted">
          {step.basis && <span className="inline-flex items-center gap-1 font-mono text-[11.5px] text-text-secondary" title="Where this step comes from"><Scale size={11} /> {step.basis}</span>}
          {step.done_at && <span>done {day(step.done_at.slice(0, 10))}</span>}
          <button className="opacity-0 group-hover:opacity-100 hover:text-text-primary inline-flex items-center gap-1 transition-opacity" onClick={() => setNoting(!noting)}>
            <MessageSquarePlus size={11} /> {step.note ? "Edit note" : "Note"}
          </button>
          <button className="opacity-0 group-hover:opacity-100 hover:text-accent-red inline-flex items-center gap-1 transition-opacity" onClick={onRemove}>
            <X size={11} /> Remove
          </button>
        </div>
        {step.note && !noting && <p className="mt-1.5 text-sm text-text-secondary border-l-2 border-accent-amber/60 pl-2.5">{step.note}</p>}
        {noting && (
          <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); onNote(note.trim() || null); setNoting(false); }}>
            <input className="input flex-1" autoFocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Shorter notice consent received from 96% on 12 Sept" />
            <button className="btn btn-primary py-1">Save</button>
          </form>
        )}
      </div>
    </li>
  );
}

function AddStep({ onAdd }: { onAdd: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <form className="flex items-center gap-2 px-4 py-3 border-t border-bg-border" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { onAdd(text.trim()); setText(""); } }}>
      <Plus size={14} className="text-text-muted" />
      <input className="bg-transparent outline-none text-sm flex-1 placeholder-text-muted" placeholder="Add a step" value={text} onChange={(e) => setText(e.target.value)} />
      {text.trim() && <button className="btn py-0.5">Add</button>}
    </form>
  );
}

function Documents({ work, onChange }: { work: Work; onChange: (w: Work) => void }) {
  const [finding, setFinding] = useState(false);
  const [name, setName] = useState("");
  const { data } = useQuery({ queryKey: ["documents", "name", name], queryFn: () => aagam.documents({ name, limit: 8 }), enabled: finding });
  const attach = useMutation({ mutationFn: (docId: number) => aagam.attach(work.id, docId), onSuccess: (w) => { onChange(w); setName(""); } });
  const detach = useMutation({ mutationFn: (docId: number) => aagam.detach(work.id, docId), onSuccess: onChange });
  const attached = new Set(work.documents.map((d) => d.id));

  return (
    <Section title={`Documents (${work.documents.length})`} actions={<button className="btn btn-ghost py-0.5 px-1.5 text-xs" onClick={() => setFinding(!finding)}><Paperclip size={12} /> Attach</button>}>
      <ul className="space-y-1">
        {work.documents.map((d) => (
          <li key={d.id} className="group flex items-center gap-2 text-sm">
            <FileText size={13} className="text-text-muted shrink-0" />
            <Link to={`/documents/${d.id}`} className="truncate flex-1 hover:text-accent-brand" title={d.original_name}>{d.title || d.original_name}</Link>
            <span className="text-xs text-text-muted shrink-0">{titleCase(d.doc_type)}</span>
            <button className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-accent-red" onClick={() => detach.mutate(d.id)} aria-label="Detach"><X size={12} /></button>
          </li>
        ))}
        {work.documents.length === 0 && !finding && <p className="text-sm text-text-muted">Attach the notice, drafts, minutes and filings as they come.</p>}
      </ul>
      {finding && (
        <div className="mt-2 space-y-1.5">
          <label className="flex items-center gap-2 input py-1">
            <Search size={13} className="text-text-muted" />
            <input className="bg-transparent outline-none flex-1" autoFocus placeholder="Find a document by name" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <ul className="max-h-56 overflow-auto">
            {data?.documents.filter((d) => !attached.has(d.id)).map((d) => (
              <li key={d.id}>
                <button className="w-full text-left text-sm px-2 py-1.5 rounded hover:bg-bg-hover flex gap-2" onClick={() => attach.mutate(d.id)}>
                  <Plus size={13} className="text-accent-brand mt-0.5 shrink-0" />
                  <span className="truncate">{d.title || d.original_name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}
