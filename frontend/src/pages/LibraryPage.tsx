import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BookMarked, Check, FilePlus2, Files, FileSpreadsheet, FileText, Inbox, Landmark, Mail, Pencil, Search, Tags, Trash2, X } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { day, titleCase } from "../lib/format";
import { tagClass } from "../types";
import { useDesk } from "../lib/theme";
import TagBadge from "../components/tags/TagBadge";
import { Empty, PageHeader, Skeleton } from "../components/ui";
import { Modal, useConfirm } from "../components/dialogs";

function TypeIcon({ type }: { type: string }) {
  const Icon = type === "financial_statements" ? Landmark : type === "notice" || type === "annual_report" ? BookMarked : type.includes("mail") ? Mail : type.includes("sheet") ? FileSpreadsheet : FileText;
  return (
    <span className="w-9 h-9 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0">
      <Icon size={16} />
    </span>
  );
}

export default function LibraryPage() {
  const navigate = useNavigate();
  const desk = useDesk();
  const [params, setParams] = useSearchParams();
  const tag = params.get("tag") ?? "";
  const docType = params.get("type") ?? "";
  const company = params.get("company") ?? "";
  const year = params.get("year") ?? "";
  const name = params.get("name") ?? "";
  const [nameInput, setNameInput] = useState(name);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [managing, setManaging] = useState(false);
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: aagam.allTags, staleTime: 30_000 });
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity });
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies() });
  const { data } = useQuery({
    queryKey: ["documents", tag, docType, company, year, name],
    queryFn: () => aagam.documents({ tag: tag || undefined, doc_type: docType || undefined, company: company || undefined, year: year || undefined, name: name || undefined, limit: 200 }),
    placeholderData: (prev) => prev,
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  // Filter by name as she types, a moment after she stops.
  useEffect(() => {
    const t = setTimeout(() => nameInput !== name && set("name", nameInput.trim()), 250);
    return () => clearTimeout(t);
  }, [nameInput]); // eslint-disable-line react-hooks/exhaustive-deps
  const years = Array.from({ length: 12 }, (_, i) => String(new Date().getFullYear() + 1 - i));
  const filtered = Boolean(tag || docType || company || year || name);

  const togglePick = (docId: number) => {
    const next = new Set(picked);
    if (next.has(docId)) next.delete(docId);
    else next.add(docId);
    setPicked(next);
  };
  const deletePicked = async () => {
    const n = picked.size;
    const ok = await confirm({
      title: `Delete ${n} document${n === 1 ? "" : "s"}?`,
      body: "They leave the library with their pages, facts, resolutions, tags and statements.",
      items: ["The files themselves are moved to the bin folder in your AAGAM folder", "Your notes on them are kept, as general notes"],
      action: `Delete ${n}`,
      danger: true,
    });
    if (!ok) return;
    let done = 0;
    for (const docId of picked) {
      try {
        await aagam.deleteDocument(docId);
        done += 1;
      } catch (e) {
        toast.error((e as Error).message);
      }
    }
    setPicked(new Set());
    queryClient.invalidateQueries();
    toast.success(`${done} document${done === 1 ? "" : "s"} deleted. The files are in the bin folder.`);
  };

  const inbox = async () => {
    const { results } = await aagam.inbox();
    toast.success(results.length ? `Brought in ${results.length} file(s) from the inbox.` : "The inbox is empty.");
  };

  return (
    <div className="px-8 py-6 max-w-6xl">
      <PageHeader
        icon={<Files size={19} />}
        title="Library"
        subtitle="Every document, read page by page. Drop files anywhere in the window to add them."
        actions={
          <>
            <button className="btn btn-ghost" onClick={() => setManaging(true)}><Tags size={14} /> Tags</button>
            <button className="btn btn-ghost" onClick={inbox} title={meta?.inbox}><Inbox size={14} /> Check inbox</button>
            <button className="btn btn-primary" onClick={() => desk.openUpload()}><FilePlus2 size={14} /> Add documents</button>
          </>
        }
      />

      <div className="card p-3 mb-3 flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-2 input py-1 flex-1 min-w-[220px]">
          <Search size={13} className="text-text-muted" />
          <input className="bg-transparent outline-none flex-1" placeholder="Filter by name or company" value={nameInput} onChange={(e) => setNameInput(e.target.value)} aria-label="Filter by name" />
        </label>
        <select className="input py-1" value={docType} onChange={(e) => set("type", e.target.value)} aria-label="Filter by type">
          <option value="">All types</option>
          {Object.entries(meta?.doc_types ?? {}).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
        <select className="input py-1" value={company} onChange={(e) => set("company", e.target.value)} aria-label="Filter by client">
          <option value="">All clients</option>
          {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
        </select>
        <select className="input py-1" value={year} onChange={(e) => set("year", e.target.value)} aria-label="Filter by year">
          <option value="">Any year</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        {filtered && (
          <button className="btn btn-ghost py-1 text-xs" onClick={() => { setNameInput(""); setParams({}, { replace: true }); }}><X size={12} /> Clear</button>
        )}
      </div>

      {tags && tags.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4" aria-label="Tags">
          {tags.tags.slice(0, 18).map((t) => (
            <button
              key={t.name}
              onClick={() => set("tag", tag === t.name ? "" : t.name)}
              aria-pressed={tag === t.name}
              className={clsx("chip transition-all", tagClass(t.name), tag === t.name ? "ring-2 ring-accent-brand/50 scale-105" : tag ? "opacity-50 hover:opacity-100" : "hover:opacity-80")}
            >
              {t.name} <span className="opacity-60">{t.documents}</span>
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 mb-2 min-h-[30px]">
        <p className="text-xs text-text-muted flex-1">{data ? `${data.total} document${data.total === 1 ? "" : "s"}${filtered ? " match" : ""}` : ""}</p>
        {picked.size > 0 && (
          <div className="flex items-center gap-2 pop-in">
            <span className="text-sm text-text-secondary">{picked.size} chosen</span>
            <button className="btn btn-ghost py-1 text-xs" onClick={() => setPicked(new Set())}>Clear</button>
            <button className="btn py-1 text-xs text-accent-red" onClick={deletePicked}><Trash2 size={13} /> Delete</button>
          </div>
        )}
      </div>
      {!data ? (
        <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : data.documents.length === 0 ? (
        <Empty icon={<Files size={20} />} title={filtered ? "No documents match." : "The library is empty."} hint={filtered ? "Try fewer filters." : "Drop PDFs, Word, Excel or emails anywhere in this window."}
          action={!filtered && <button className="btn btn-primary" onClick={() => desk.openUpload()}><FilePlus2 size={14} /> Add documents</button>} />
      ) : (
        <div className="card overflow-hidden">
          <ul key={`${tag}-${docType}-${company}-${year}-${name}`} className="divide-y divide-bg-border stagger">
            {data.documents.map((doc) => (
              <li key={doc.id} className={clsx("group relative", picked.has(doc.id) && "bg-accent-brand/[0.06]")}>
                <span
                  role="checkbox"
                  aria-checked={picked.has(doc.id)}
                  aria-label={`Choose ${doc.title || doc.original_name}`}
                  tabIndex={0}
                  onClick={() => togglePick(doc.id)}
                  onKeyDown={(e) => (e.key === " " || e.key === "Enter") && (e.preventDefault(), togglePick(doc.id))}
                  className={clsx(
                    "absolute left-4 top-1/2 -translate-y-1/2 z-10 w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-all",
                    picked.has(doc.id) ? "bg-accent-brand text-on-accent" : "opacity-0 group-hover:opacity-100 bg-bg-surface border border-bg-border"
                  )}
                >
                  {picked.has(doc.id) ? <Check size={16} className="tick" /> : <span className="w-3.5 h-3.5 rounded border border-text-muted" />}
                </span>
                <button onClick={() => (picked.size ? togglePick(doc.id) : navigate(`/documents/${doc.id}`))} className="w-full text-left px-4 py-3 flex gap-3 items-center hover:bg-bg-hover/70 transition-colors">
                  <TypeIcon type={doc.doc_type} />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium truncate">{doc.title || doc.original_name}</p>
                    <p className="text-xs text-text-muted truncate mt-0.5">
                      {titleCase(doc.doc_type)} · {doc.pages} page{doc.pages === 1 ? "" : "s"}
                      {doc.company_name && ` · ${doc.company_name}`}
                      {doc.meeting_date && ` · meeting ${day(doc.meeting_date)}`}
                      {doc.client && ` · client: ${doc.client}`} · added {day(doc.ingested_at.slice(0, 10))}
                    </p>
                  </div>
                  <div className="hidden md:flex flex-wrap justify-end gap-1 max-w-[280px]">
                    {doc.tags.slice(0, 3).map((t) => <TagBadge key={t} tag={t} />)}
                    {doc.tags.length > 3 && <span className="chip bg-bg-hover text-text-muted">+{doc.tags.length - 3}</span>}
                  </div>
                  {doc.resolutions > 0 && <span className="text-xs text-accent-brand shrink-0 w-24 text-right">{doc.resolutions} resolutions</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {managing && <ManageTags onClose={() => setManaging(false)} />}
    </div>
  );
}

/** All the tags: rename (or merge into another), delete. Automatic tagging follows what she does here. */
function ManageTags({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const { data } = useQuery({ queryKey: ["tags"], queryFn: aagam.allTags });
  const [editing, setEditing] = useState<string | null>(null);
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const done = () => {
    queryClient.invalidateQueries({ queryKey: ["tags"] });
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["document"] });
  };
  const rename = async (name: string) => {
    if (!to.trim() || to.trim() === name) return setEditing(null);
    try {
      const r = await aagam.renameTag(name, to);
      toast.success(r.merged ? `Merged into “${r.tag}”.` : `Renamed to “${r.tag}”.`);
      setEditing(null);
      done();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const remove = async (name: string, documents: number) => {
    const ok = await confirm({
      title: `Delete the tag “${name}”?`,
      body: `It comes off ${documents} document${documents === 1 ? "" : "s"}, and automatic tagging won't add it again. The documents themselves stay.`,
      action: "Delete tag",
      danger: true,
    });
    if (!ok) return;
    await aagam.deleteTag(name);
    toast.success("Tag deleted.");
    done();
  };
  const tags = (data?.tags ?? []).filter((t) => t.name.includes(q.trim().toLowerCase()));
  return (
    <Modal title="Tags" onClose={onClose} width="max-w-xl">
      <p className="text-sm text-text-muted mb-3">Rename a tag (giving it the name of another merges the two) or delete it. Automatic tagging follows: a renamed tag is added under its new name, a deleted one isn't added again.</p>
      <label className="flex items-center gap-2 input py-1 mb-2">
        <Search size={13} className="text-text-muted" />
        <input className="bg-transparent outline-none flex-1" placeholder="Find a tag" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      <ul className="divide-y divide-bg-border max-h-[55vh] overflow-auto">
        {tags.map((t) => (
          <li key={t.name} className="group flex items-center gap-2 py-1.5">
            {editing === t.name ? (
              <form className="flex items-center gap-2 flex-1" onSubmit={(e) => { e.preventDefault(); rename(t.name); }}>
                <input className="input py-1 flex-1" autoFocus value={to} onChange={(e) => setTo(e.target.value)} aria-label="New name" list="tag-names" />
                <datalist id="tag-names">{data?.tags.map((x) => <option key={x.name} value={x.name} />)}</datalist>
                <button className="btn btn-primary py-1 text-xs">Save</button>
                <button type="button" className="btn py-1 text-xs" onClick={() => setEditing(null)}>Cancel</button>
              </form>
            ) : (
              <>
                <span className={clsx("chip", tagClass(t.name))}>{t.name}</span>
                <span className="text-xs text-text-muted flex-1">{t.documents} document{t.documents === 1 ? "" : "s"}</span>
                <span className="opacity-0 group-hover:opacity-100 transition-opacity">
                  <button className="btn btn-ghost px-1.5 py-1" onClick={() => { setEditing(t.name); setTo(t.name); }} aria-label={`Rename ${t.name}`} title="Rename or merge"><Pencil size={13} /></button>
                  <button className="btn btn-ghost px-1.5 py-1 hover:text-accent-red" onClick={() => remove(t.name, t.documents)} aria-label={`Delete ${t.name}`} title="Delete"><Trash2 size={13} /></button>
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
    </Modal>
  );
}
