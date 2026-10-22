import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Check, Copy, Loader2, Pencil, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam, type PrecedentFilter } from "../api/aagam";
import type { PrecedentFull } from "../types";
import { crore, day, titleCase } from "../lib/format";
import { MoreMenu, useConfirm } from "../components/dialogs";

const SECTIONS = ["180", "185", "186", "188", "139", "149", "152", "196", "197", "13", "14", "42", "62", "61", "123"];

export default function PrecedentsPage() {
  const [params, setParams] = useSearchParams();
  const openId = params.get("open") ? Number(params.get("open")) : null;
  const [filter, setFilter] = useState<PrecedentFilter>({ section: params.get("section") ?? "" });
  const [words, setWords] = useState("");
  const { data: topics } = useQuery({ queryKey: ["topics"], queryFn: aagam.topics });
  const { data, isFetching } = useQuery({ queryKey: ["precedents", filter], queryFn: () => aagam.precedents(filter) });
  const update = (patch: PrecedentFilter) => setFilter((f) => ({ ...f, ...patch }));
  const open = (id: number) => {
    const next = new URLSearchParams(params);
    next.set("open", String(id));
    setParams(next);
  };

  return (
    <div className="flex h-full">
      <div className="w-[46%] min-w-[420px] border-r border-bg-border flex flex-col">
        <div className="p-4 border-b border-bg-border bg-bg-secondary space-y-3">
          <h1 className="text-[1.6rem] leading-tight font-semibold">Precedents</h1>
          <p className="text-xs text-text-muted">Every resolution from the notices in the library. Add listed companies' notices to grow it.</p>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); update({ q: words.trim() }); }}>
            <input className="input flex-1" placeholder="Words in the resolution or its statement" value={words} onChange={(e) => setWords(e.target.value)} />
            <button className="btn">Find</button>
          </form>
          <div className="flex flex-wrap gap-1.5">
            {SECTIONS.map((s) => (
              <button key={s} onClick={() => update({ section: filter.section === s ? "" : s })}
                className={clsx("chip font-mono", filter.section === s ? "bg-accent-brand text-on-accent" : "tag-section")}>
                s.{s}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 text-sm items-center">
            <select className="input py-1" value={filter.topic ?? ""} onChange={(e) => update({ topic: e.target.value })} aria-label="Topic">
              <option value="">Any topic</option>
              {topics?.topics.map((t) => <option key={t.topic} value={t.topic}>{titleCase(t.topic)} ({t.resolutions})</option>)}
            </select>
            <select className="input py-1" value={filter.kind ?? ""} onChange={(e) => update({ kind: e.target.value })} aria-label="Kind">
              <option value="">Special or ordinary</option>
              <option value="special">Special resolutions</option>
              <option value="ordinary">Ordinary resolutions</option>
            </select>
            <label className="flex items-center gap-1 text-text-secondary">
              at least ₹
              <input className="input py-1 w-20" type="number" min={0} placeholder="crore" onChange={(e) => update({ min_crore: e.target.value ? Number(e.target.value) : undefined })} />
              crore
            </label>
            <label className="flex items-center gap-1 text-text-secondary">
              <input type="checkbox" checked={!!filter.with_statement} onChange={(e) => update({ with_statement: e.target.checked })} /> with statement
            </label>
          </div>
        </div>
        <div className="flex-1 overflow-auto divide-y divide-bg-border">
          {isFetching && !data && <p className="p-4 text-text-muted flex gap-2 items-center"><Loader2 size={14} className="animate-spin" /> Finding…</p>}
          {data?.resolutions.map((r) => (
            <button key={r.id} onClick={() => open(r.id)} className={clsx("w-full text-left p-3 hover:bg-bg-hover", openId === r.id && "bg-bg-hover border-l-2 border-accent-brand")}>
              <p className="text-sm font-medium">{r.title}</p>
              <p className="text-xs text-text-muted mt-1 flex flex-wrap gap-x-2">
                <span>{r.company_name ?? r.original_name}</span>
                {r.meeting_kind && <span>{r.meeting_kind.toUpperCase()}{r.meeting_date ? ` ${day(r.meeting_date)}` : ""}</span>}
                <span className={clsx(r.resolution_kind === "special" && "text-accent-amber")}>{r.resolution_kind ? titleCase(r.resolution_kind) : "—"}</span>
                {r.sections.filter((s) => !s.includes("(")).map((s) => <span key={s} className="font-mono">s.{s}</span>)}
                {r.max_amount ? <span>{crore(r.max_amount)}</span> : null}
                {r.has_statement ? <span>statement</span> : null}
              </p>
            </button>
          ))}
          {data && data.count === 0 && <p className="p-6 text-center text-text-muted text-sm">No resolutions match. Add notices to the library to grow this.</p>}
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {openId ? (
          <PrecedentView
            key={openId}
            id={openId}
            editing={params.get("edit") === "1"}
            setEditing={(on) => { const next = new URLSearchParams(params); if (on) next.set("edit", "1"); else next.delete("edit"); setParams(next, { replace: true }); }}
            onDeleted={() => { const next = new URLSearchParams(params); next.delete("open"); next.delete("edit"); setParams(next); }}
          />
        ) : <p className="p-8 text-text-muted">Choose a resolution to read it in full.</p>}
      </div>
    </div>
  );
}

function PrecedentView({ id, editing, setEditing, onDeleted }: { id: number; editing: boolean; setEditing: (on: boolean) => void; onDeleted: () => void }) {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const { data } = useQuery({ queryKey: ["precedent", id], queryFn: () => aagam.precedent(id) });
  if (!data) return <p className="p-8 text-text-muted">Loading…</p>;
  const changed = () => {
    queryClient.invalidateQueries({ queryKey: ["precedents"] });
    queryClient.invalidateQueries({ queryKey: ["precedent", id] });
    queryClient.invalidateQueries({ queryKey: ["document", data.document_id] });
  };
  const remove = async () => {
    const ok = await confirm({
      title: "Delete this resolution from the precedent library?",
      body: "It is taken out of the library and stays out when the notice is read again. The notice itself is kept.",
      action: "Delete resolution",
      danger: true,
    });
    if (!ok) return;
    await aagam.deletePrecedent(id);
    toast.success("Resolution deleted from the library.");
    changed();
    onDeleted();
  };
  if (editing) return <PrecedentEditor data={data} onDone={() => { changed(); setEditing(false); }} onCancel={() => setEditing(false)} />;
  return (
    <div className="p-8 max-w-3xl space-y-5">
      <div className="relative">
        <div className="absolute right-0 top-0 flex gap-1">
          <button className="btn btn-ghost py-1 text-xs" onClick={() => setEditing(true)}><Pencil size={13} /> Correct</button>
          <MoreMenu items={[{ label: "Delete from the library", icon: <Trash2 size={14} />, danger: true, onClick: remove }]} />
        </div>
        <p className="text-xs text-text-muted pr-36">
          Item {data.item_no} · {data.business ? `${titleCase(data.business)} business` : ""} ·{" "}
          <Link className="underline" to={`/documents/${data.document_id}?page=${data.page_from}`}>{data.company_name ?? data.original_name}, page {data.page_from}</Link>
        </p>
        <h2 className="text-lg font-semibold mt-1">{data.title}</h2>
        <p className="text-sm text-text-secondary mt-1">
          {data.resolution_kind ? `${titleCase(data.resolution_kind)} resolution` : "No resolution text"}
          {data.max_amount ? ` · ${crore(data.max_amount)}` : ""}
          {data.sections.length ? ` · ${data.sections.map((s) => `s.${s}`).join(", ")}` : ""}
        </p>
      </div>
      <Block title="Resolution" text={data.body || "This item has no resolution text in the notice."} />
      {data.statement && <Block title="Explanatory statement" text={data.statement} />}
      <p className="text-xs text-text-muted">This is another company's wording. Adapt the names, amounts and dates to her company, and check it against the Act before using it.</p>
    </div>
  );
}

function Block({ title, text }: { title: string; text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success(`${title} copied.`);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <section className="card p-5">
      <div className="flex items-center mb-2">
        <p className="label flex-1">{title}</p>
        <button className="btn py-0.5 px-2 text-xs" onClick={copy}>{copied ? <Check size={12} /> : <Copy size={12} />} Copy</button>
      </div>
      <div className="legal">{text}</div>
    </section>
  );
}

/** She corrects what the splitter read: the title, the kind of resolution, the sections, the amount, the words. */
function PrecedentEditor({ data, onDone, onCancel }: { data: PrecedentFull; onDone: () => void; onCancel: () => void }) {
  const [form, setForm] = useState({
    title: data.title,
    resolution_kind: data.resolution_kind ?? "",
    business: data.business ?? "",
    sections: data.sections.join(" "),
    topics: data.topics.join(" "),
    crore: data.max_amount ? String(data.max_amount / 10_000_000) : "",
    body: data.body,
    statement: data.statement ?? "",
  });
  const save = useMutation({
    mutationFn: () =>
      aagam.editPrecedent(data.id, {
        title: form.title,
        resolution_kind: form.resolution_kind || null,
        business: form.business || null,
        sections: form.sections.split(/[\s,]+/).filter(Boolean),
        topics: form.topics.split(/[\s,]+/).filter(Boolean),
        max_amount: form.crore ? Math.round(Number(form.crore) * 10_000_000) : null,
        body: form.body,
        statement: form.statement || null,
      }),
    onSuccess: () => { toast.success("Saved. Your corrections stay when the notice is read again."); onDone(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  return (
    <div className="p-8 max-w-3xl space-y-4 fade-in">
      <p className="display text-lg font-semibold">Correct this resolution</p>
      <label className="block"><span className="text-xs text-text-muted">Title</span><input className="input w-full mt-0.5" value={form.title} onChange={set("title")} /></label>
      <div className="grid sm:grid-cols-4 gap-3">
        <label className="block"><span className="text-xs text-text-muted">Resolution</span>
          <select className="input w-full mt-0.5" value={form.resolution_kind} onChange={set("resolution_kind")}>
            <option value="">Not stated</option><option value="ordinary">Ordinary</option><option value="special">Special</option><option value="board">Board</option>
          </select>
        </label>
        <label className="block"><span className="text-xs text-text-muted">Business</span>
          <select className="input w-full mt-0.5" value={form.business} onChange={set("business")}>
            <option value="">Not stated</option><option value="ordinary">Ordinary</option><option value="special">Special</option>
          </select>
        </label>
        <label className="block"><span className="text-xs text-text-muted">Sections</span><input className="input w-full mt-0.5 font-mono" placeholder="185 186(3)" value={form.sections} onChange={set("sections")} /></label>
        <label className="block"><span className="text-xs text-text-muted">Amount (₹ crore)</span><input className="input w-full mt-0.5 tabular" inputMode="decimal" value={form.crore} onChange={set("crore")} /></label>
      </div>
      <label className="block"><span className="text-xs text-text-muted">Topics (tags, separated by spaces)</span><input className="input w-full mt-0.5" value={form.topics} onChange={set("topics")} /></label>
      <label className="block"><span className="text-xs text-text-muted">Resolution text</span><textarea className="input legal w-full mt-0.5 h-56" value={form.body} onChange={set("body")} /></label>
      <label className="block"><span className="text-xs text-text-muted">Explanatory statement</span><textarea className="input legal w-full mt-0.5 h-56" value={form.statement} onChange={set("statement")} /></label>
      <div className="flex gap-2">
        <button className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>Save</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
