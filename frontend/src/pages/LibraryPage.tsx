import { useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  BookMarked, Check, ChevronRight, FilePlus2, Files, FileSpreadsheet, FileText, FolderOpen, FolderPlus, Image, Inbox, Landmark, Loader2, Mail,
  Pencil, Presentation, Search, Tags, Trash2, X,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam, type LibraryFilter } from "../api/aagam";
import { missing } from "../api/client";
import { clientReason, count, day, month, titleCase } from "../lib/format";
import { tagClass, type DocumentRow, type Facet } from "../types";
import { useDesk } from "../lib/theme";
import TagBadge from "../components/tags/TagBadge";
import { Empty, PageHeader, Skeleton } from "../components/ui";
import { Modal, useConfirm } from "../components/dialogs";
import FolderDialog from "../components/FolderDialog";
import FoldersPanel, { useFolders } from "../components/FoldersPanel";

const PAGE = 200;
const GROUPS = { none: "Don't group", client: "Client", type: "Type", fy: "Financial year", month: "Month", folder: "Folder" } as const;
type Group = keyof typeof GROUPS;
const SORTS = { added: "Newest added", newest: "Newest by date", oldest: "Oldest by date", name: "Name" } as const;
// The URL keeps her filters, so the back button and a shared link bring them back.
const FILTER_KEYS = ["tag", "type", "company", "year", "name", "fy", "from", "to", "folder", "within", "kind", "scanned"] as const;

function TypeIcon({ type, kind }: { type: string; kind?: string | null }) {
  const Icon = type === "financial_statements" ? Landmark : type === "notice" || type === "annual_report" ? BookMarked
    : kind === "email" ? Mail : kind === "excel" ? FileSpreadsheet : kind === "image" ? Image : kind === "slides" ? Presentation : FileText;
  return (
    <span className="w-9 h-9 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0">
      <Icon size={16} />
    </span>
  );
}

const withCount = (label: string, n?: number) => (n === undefined ? label : `${label} (${n.toLocaleString("en-IN")})`);

export default function LibraryPage() {
  const navigate = useNavigate();
  const desk = useDesk();
  const [params, setParams] = useSearchParams();
  const get = (k: string) => params.get(k) ?? "";
  const tag = get("tag"), docType = get("type"), company = get("company"), year = get("year"), name = get("name");
  const fy = get("fy"), from = get("from"), to = get("to"), folder = get("folder"), within = get("within"), kind = get("kind"), scanned = get("scanned");
  const sort = (get("sort") || "added") as keyof typeof SORTS;
  const group = (get("group") || "none") as Group;
  const [nameInput, setNameInput] = useState(name);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [managing, setManaging] = useState(false);
  const [addingFolder, setAddingFolder] = useState(false);
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const folders = useFolders();
  const foldersWork = !folders.isError || !missing(folders.error);

  const filter: LibraryFilter = {
    tag: tag || undefined, doc_type: docType || undefined, company: company || undefined, year: year || undefined, name: name || undefined,
    fy: fy || undefined, date_from: from || undefined, date_to: to || undefined, folder: folder || undefined, within: within || undefined,
    kind: kind || undefined, scanned: scanned || undefined,
  };
  const filterKey = FILTER_KEYS.map((k) => get(k)).join("|");
  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: aagam.allTags, staleTime: 30_000 });
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity });
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies() });
  const { data: facets } = useQuery({
    queryKey: ["facets", filterKey],
    queryFn: () => aagam.facets(filter),
    placeholderData: (prev) => prev,
    retry: (n, e) => !missing(e) && n < 2,
  });
  const docs = useInfiniteQuery({
    queryKey: ["documents", "library", filterKey, sort],
    queryFn: ({ pageParam }) => aagam.documents({ ...filter, sort, limit: PAGE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.documents.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
    placeholderData: (prev) => prev,
  });
  const rows = useMemo(() => docs.data?.pages.flatMap((p) => p.documents) ?? [], [docs.data]);
  const total = docs.data?.pages[0]?.total;

  // While a folder is being read, documents arrive in the background: show them, but refresh at most every few seconds.
  const progress = (folders.data?.folders ?? []).map((f) => `${f.id}:${f.status}:${f.added}:${f.already}`).join("|");
  const seen = useRef<string | null>(null);
  const last = useRef(0);
  useEffect(() => {
    const changed = seen.current !== null && seen.current !== progress;
    seen.current = progress;
    if (!changed) return;
    const refresh = () => {
      last.current = Date.now();
      for (const key of ["documents", "facets", "tags", "overview"]) queryClient.invalidateQueries({ queryKey: [key] });
    };
    const wait = 5_000 - (Date.now() - last.current);
    if (wait <= 0) return refresh();
    const t = setTimeout(refresh, wait);
    return () => clearTimeout(t);
  }, [progress, queryClient]);

  // "Add a folder" from the command palette arrives as ?add=folder.
  useEffect(() => {
    if (params.get("add") === "folder") {
      setAddingFolder(true);
      const next = new URLSearchParams(params);
      next.delete("add");
      setParams(next, { replace: true });
    }
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  const setMany = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    setParams(next, { replace: true });
  };
  const set = (key: string, value: string) => setMany(key === "folder" ? { folder: value, within: "" } : { [key]: value });
  // Filter by name as she types, a moment after she stops.
  useEffect(() => {
    const t = setTimeout(() => nameInput !== name && set("name", nameInput.trim()), 250);
    return () => clearTimeout(t);
  }, [nameInput]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setNameInput(name), [name]);
  const filtered = FILTER_KEYS.some((k) => get(k));

  const togglePick = (docId: number) => {
    const next = new Set(picked);
    if (next.has(docId)) next.delete(docId);
    else next.add(docId);
    setPicked(next);
  };
  const trashPicked = async () => {
    const n = picked.size;
    const ok = await confirm({
      title: `Move ${count(n, "document")} to the Trash?`,
      body: "They leave the library straight away. From the Trash you can put them back as they were, with your corrections, tags and notes.",
      action: `Move ${n} to the Trash`,
      danger: true,
    });
    if (!ok) return;
    const ids = Array.from(picked);
    let moved = 0;
    try {
      const r = await aagam.trashDocuments(ids);
      moved = r.trashed.length;
      r.failed.forEach((f) => toast.error(f.error));
    } catch (e) {
      if (!missing(e)) {
        toast.error((e as Error).message);
      } else {
        // An AAGAM without the bulk call: one at a time.
        for (const docId of ids) {
          try {
            await aagam.deleteDocument(docId);
            moved += 1;
          } catch (err) {
            toast.error((err as Error).message);
          }
        }
      }
    }
    setPicked(new Set());
    queryClient.invalidateQueries();
    if (moved) toast.success(`${count(moved, "document")} moved to the Trash.`);
  };

  const inbox = async () => {
    try {
      const { results } = await aagam.inbox();
      toast.success(results.length ? `Brought in ${results.length} file(s) from the inbox.` : "The inbox is empty.");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const groups = useMemo(() => grouped(rows, group, sort, meta?.doc_types ?? {}), [rows, group, sort, meta]);
  const folderLabel = (id: string) => facets?.folders.find((f) => String(f.key) === id)?.label ?? folders.data?.folders.find((f) => String(f.id) === id)?.path ?? `Folder ${id}`;
  const chips = activeChips({ tag, docType, company, year, name, fy, from, to, folder, within, kind, scanned }, {
    type: (k) => meta?.doc_types[k] ?? titleCase(k),
    company: (k) => (k === "none" ? "No client" : companies?.companies.find((c) => String(c.id) === k)?.name ?? k),
    kind: (k) => meta?.file_kinds?.[k] ?? k,
    folder: folderLabel,
  });

  return (
    <div className="px-8 py-6 max-w-6xl">
      <PageHeader
        icon={<Files size={19} />}
        title="Library"
        subtitle="Every document, read page by page. Drop files or folders anywhere in the window to add them."
        actions={
          <>
            <button className="btn btn-ghost" onClick={() => setManaging(true)}><Tags size={14} /> Tags</button>
            <button className="btn btn-ghost" onClick={inbox} title={meta?.inbox}><Inbox size={14} /> Check inbox</button>
            {foldersWork && <button className="btn" onClick={() => setAddingFolder(true)}><FolderPlus size={14} /> Add a folder</button>}
            <button className="btn btn-primary" onClick={() => desk.openUpload()}><FilePlus2 size={14} /> Add documents</button>
          </>
        }
      />

      {foldersWork && <FoldersPanel onShow={(id) => set("folder", id ? String(id) : "")} shown={folder ? Number(folder) : null} />}

      <div className="card p-3 mb-3 space-y-2 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 input py-1 flex-1 min-w-[220px]">
            <Search size={13} className="text-text-muted" />
            <input className="bg-transparent outline-none flex-1" placeholder="Filter by name, company or folder" value={nameInput} onChange={(e) => setNameInput(e.target.value)} aria-label="Filter by name" />
          </label>
          <select className="input py-1 max-w-[230px]" value={docType} onChange={(e) => set("type", e.target.value)} aria-label="Filter by type">
            <option value="">All types</option>
            {typeOptions(meta?.doc_types ?? {}, facets?.types, docType).map(([k, label, n]) => <option key={k} value={k}>{withCount(label, n)}</option>)}
          </select>
          <select className="input py-1 max-w-[230px]" value={company} onChange={(e) => set("company", e.target.value)} aria-label="Filter by client">
            <option value="">All clients</option>
            <option value="none">{withCount("No client", facets?.clients.find((c) => c.key === null)?.documents)}</option>
            {companies?.companies.map((c) => (
              <option key={c.id} value={String(c.id)}>{withCount(c.name, facets ? (facets.clients.find((x) => x.key === c.id)?.documents ?? 0) : undefined)}</option>
            ))}
          </select>
          <select className="input py-1" value={kind} onChange={(e) => set("kind", e.target.value)} aria-label="Filter by kind of file">
            <option value="">Any kind of file</option>
            {Object.entries(meta?.file_kinds ?? {}).map(([k, label]) => {
              const n = facets?.kinds.find((x) => x.key === k)?.documents;
              return facets && !n && k !== kind ? null : <option key={k} value={k}>{withCount(label, facets ? n ?? 0 : undefined)}</option>;
            })}
          </select>
          <select className="input py-1" value={scanned} onChange={(e) => set("scanned", e.target.value)} aria-label="Filter by scans">
            <option value="">Scanned or not</option>
            <option value="true">Has scanned pages</option>
            <option value="false">No scanned pages</option>
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="input py-1" value={fy} onChange={(e) => setMany({ fy: e.target.value, year: "" })} aria-label="Filter by financial year">
            <option value="">Any financial year</option>
            {fyOptions(facets?.fys, fy).map((f) => <option key={String(f.key)} value={String(f.key)}>{withCount(`FY ${f.key}`, f.documents || undefined)}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-text-muted">
            Dated from
            <input type="date" className="input py-1 text-sm" value={from} max={to || undefined} onChange={(e) => set("from", e.target.value)} aria-label="Dated from" />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-text-muted">
            to
            <input type="date" className="input py-1 text-sm" value={to} min={from || undefined} onChange={(e) => set("to", e.target.value)} aria-label="Dated to" />
          </label>
          {(facets?.folders.length ?? 0) > 0 && (
            <select className="input py-1 max-w-[260px]" value={folder} onChange={(e) => set("folder", e.target.value)} aria-label="Filter by folder">
              <option value="">Any folder</option>
              {facets!.folders.map((f) => <option key={String(f.key)} value={String(f.key)}>{withCount(f.label ?? `Folder ${f.key}`, f.documents)}</option>)}
            </select>
          )}
          <span className="flex-1" />
          <select className="input py-1" value={sort} onChange={(e) => set("sort", e.target.value === "added" ? "" : e.target.value)} aria-label="Sort">
            {Object.entries(SORTS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
          <select className="input py-1" value={group} onChange={(e) => set("group", e.target.value === "none" ? "" : e.target.value)} aria-label="Group by">
            {Object.entries(GROUPS).map(([k, label]) => <option key={k} value={k}>{k === "none" ? label : `Group by ${label.toLowerCase()}`}</option>)}
          </select>
        </div>
        {folder && <FolderCrumbs folderPath={folderLabel(folder)} within={within} inside={facets?.inside ?? []} onWithin={(w) => set("within", w)} />}
        {chips.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 pt-0.5" aria-label="Filters in use">
            {chips.map((c) => (
              <button key={c.key} className="chip bg-accent-brand/10 text-accent-brand hover:bg-accent-brand/15" onClick={() => setMany(c.clear)} aria-label={`Remove the filter ${c.label}`}>
                {c.label} <X size={11} />
              </button>
            ))}
            <button className="btn btn-ghost py-0.5 text-xs" onClick={() => { setNameInput(""); setMany(Object.fromEntries(FILTER_KEYS.map((k) => [k, ""]))); }}><X size={12} /> Clear</button>
          </div>
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
        <p className="text-xs text-text-muted flex-1">{total !== undefined ? `${total} document${total === 1 ? "" : "s"}${filtered ? " match" : ""}` : ""}</p>
        {picked.size > 0 && (
          <div className="flex items-center gap-2 pop-in">
            <span className="text-sm text-text-secondary">{picked.size} chosen</span>
            <button className="btn btn-ghost py-1 text-xs" onClick={() => setPicked(new Set(rows.map((r) => r.id)))}>Choose all shown</button>
            <button className="btn btn-ghost py-1 text-xs" onClick={() => setPicked(new Set())}>Clear</button>
            <button className="btn py-1 text-xs text-accent-red" onClick={trashPicked}><Trash2 size={13} /> Move to Trash</button>
          </div>
        )}
      </div>
      {!docs.data ? (
        docs.isError ? <p className="text-sm text-accent-red">{(docs.error as Error).message}</p> : <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : rows.length === 0 ? (
        <Empty icon={<Files size={20} />} title={filtered ? "No documents match." : "The library is empty."} hint={filtered ? "Try fewer filters." : "Drop PDFs, Word, Excel, emails or whole folders anywhere in this window."}
          action={!filtered && (
            <div className="flex justify-center gap-2">
              <button className="btn btn-primary" onClick={() => desk.openUpload()}><FilePlus2 size={14} /> Add documents</button>
              {foldersWork && <button className="btn" onClick={() => setAddingFolder(true)}><FolderPlus size={14} /> Add a folder</button>}
            </div>
          )} />
      ) : (
        <div className="space-y-3">
          {groups.map((g) => (
            <div key={g.key} className="card overflow-hidden">
              {group !== "none" && (
                <div className="px-4 py-2 border-b border-bg-border bg-bg-hover/40 flex items-center gap-2">
                  <p className="text-sm font-semibold flex-1 truncate">{g.label}</p>
                  <span className="text-xs text-text-muted tabular">{count(g.rows.length, "document")}{docs.hasNextPage ? " shown" : ""}</span>
                </div>
              )}
              <ul key={`${filterKey}-${sort}-${group}`} className="divide-y divide-bg-border stagger">
                {g.rows.map((doc) => <Row key={doc.id} doc={doc} picked={picked} togglePick={togglePick} open={() => navigate(`/documents/${doc.id}`)} groupedBy={group} />)}
              </ul>
            </div>
          ))}
          {docs.hasNextPage && (
            <div className="text-center">
              <button className="btn" onClick={() => docs.fetchNextPage()} disabled={docs.isFetchingNextPage}>
                {docs.isFetchingNextPage ? <Loader2 size={14} className="animate-spin" /> : null} Show more ({(total ?? 0) - rows.length} more)
              </button>
            </div>
          )}
        </div>
      )}
      {managing && <ManageTags onClose={() => setManaging(false)} />}
      {addingFolder && <FolderDialog onClose={() => setAddingFolder(false)} />}
    </div>
  );
}

function Row({ doc, picked, togglePick, open, groupedBy }: {
  doc: DocumentRow; picked: Set<number>; togglePick: (id: number) => void; open: () => void; groupedBy: Group;
}) {
  const chosen = picked.has(doc.id);
  const when = doc.doc_date ?? doc.ingested_at.slice(0, 10);
  const dated = doc.doc_date_basis ? `Dated ${day(when)}: ${doc.doc_date_basis}` : `Dated ${day(when)}`;
  return (
    <li className={clsx("group relative", chosen && "bg-accent-brand/[0.06]")}>
      <span
        role="checkbox"
        aria-checked={chosen}
        aria-label={`Choose ${doc.title || doc.original_name}`}
        tabIndex={0}
        onClick={() => togglePick(doc.id)}
        onKeyDown={(e) => (e.key === " " || e.key === "Enter") && (e.preventDefault(), togglePick(doc.id))}
        className={clsx(
          "absolute left-4 top-1/2 -translate-y-1/2 z-10 w-9 h-9 rounded-xl flex items-center justify-center cursor-pointer transition-all",
          chosen ? "bg-accent-brand text-on-accent" : "opacity-0 group-hover:opacity-100 bg-bg-surface border border-bg-border"
        )}
      >
        {chosen ? <Check size={16} className="tick" /> : <span className="w-3.5 h-3.5 rounded border border-text-muted" />}
      </span>
      <button onClick={() => (picked.size ? togglePick(doc.id) : open())} className="w-full text-left px-4 py-3 flex gap-3 items-center hover:bg-bg-hover/70 transition-colors">
        <TypeIcon type={doc.doc_type} kind={doc.kind} />
        <div className="min-w-0 flex-1">
          <p className="font-medium truncate">{doc.title || doc.original_name}</p>
          <p className="text-xs text-text-muted truncate mt-0.5">
            {groupedBy !== "type" && <>{titleCase(doc.doc_type)} · </>}
            <span title={dated}>{day(when)}</span> · {doc.pages} page{doc.pages === 1 ? "" : "s"}
            {doc.company_name && ` · ${doc.company_name}`}
            {doc.client && groupedBy !== "client" && <> · <span title={clientReason(doc.client_why)}>client: {doc.client}</span></>}
          </p>
          {doc.source_folder && groupedBy !== "folder" && (
            <p className="text-[11px] text-text-muted truncate flex items-center gap-1 mt-0.5"><FolderOpen size={10} className="shrink-0" /> {doc.source_folder}</p>
          )}
        </div>
        <div className="hidden md:flex flex-wrap justify-end gap-1 max-w-[280px]">
          {doc.tags.slice(0, 3).map((t) => <TagBadge key={t} tag={t} />)}
          {doc.tags.length > 3 && <span className="chip bg-bg-hover text-text-muted">+{doc.tags.length - 3}</span>}
        </div>
        {doc.resolutions > 0 && <span className="text-xs text-accent-brand shrink-0 w-24 text-right">{doc.resolutions} resolutions</span>}
      </button>
    </li>
  );
}

/** Where she is inside a folder, and the folders inside it: a click goes in, or back up. */
function FolderCrumbs({ folderPath, within, inside, onWithin }: { folderPath: string; within: string; inside: Facet[]; onWithin: (w: string) => void }) {
  const parts = within ? within.split("/") : [];
  return (
    <div className="flex flex-wrap items-center gap-1 text-xs" aria-label="Folder">
      <FolderOpen size={13} className="text-accent-brand" />
      <button className={clsx("hover:underline font-mono", !within && "font-semibold")} onClick={() => onWithin("")}>{folderPath}</button>
      {parts.map((p, i) => (
        <span key={i} className="flex items-center gap-1">
          <ChevronRight size={11} className="text-text-muted" />
          <button className={clsx("hover:underline", i === parts.length - 1 && "font-semibold")} onClick={() => onWithin(parts.slice(0, i + 1).join("/"))}>{p}</button>
        </span>
      ))}
      {inside.length > 0 && (
        <>
          <span className="text-text-muted ml-2">Inside:</span>
          {inside.slice(0, 30).map((f) => (
            <button key={String(f.key)} className="chip tag-0 hover:opacity-80" onClick={() => onWithin(String(f.key))}>
              {f.label} <span className="opacity-60">{f.documents}</span>
            </button>
          ))}
          {inside.length > 30 && <span className="text-text-muted">and {inside.length - 30} more</span>}
        </>
      )}
    </div>
  );
}

/** Types that have documents (with their counts) come first; the rest stay choosable. */
function typeOptions(all: Record<string, string>, counts: Facet[] | undefined, current: string): [string, string, number | undefined][] {
  if (!counts) return Object.entries(all).map(([k, label]) => [k, label, undefined]);
  const n = new Map(counts.map((c) => [String(c.key), c.documents]));
  const present = Object.entries(all).filter(([k]) => n.get(k) || k === current).map(([k, label]): [string, string, number | undefined] => [k, label, n.get(k) ?? 0]);
  return present.sort((a, b) => (b[2] ?? 0) - (a[2] ?? 0));
}

function fyOptions(fys: Facet[] | undefined, current: string): Facet[] {
  const list = [...(fys ?? [])];
  if (current && !list.some((f) => f.key === current)) list.unshift({ key: current, documents: 0 });
  return list;
}

function activeChips(
  v: Record<string, string>,
  names: { type: (k: string) => string; company: (k: string) => string; kind: (k: string) => string; folder: (k: string) => string },
): { key: string; label: string; clear: Record<string, string> }[] {
  const out: { key: string; label: string; clear: Record<string, string> }[] = [];
  if (v.name) out.push({ key: "name", label: `Named “${v.name}”`, clear: { name: "" } });
  if (v.docType) out.push({ key: "type", label: names.type(v.docType), clear: { type: "" } });
  if (v.company) out.push({ key: "company", label: names.company(v.company), clear: { company: "" } });
  if (v.kind) out.push({ key: "kind", label: names.kind(v.kind), clear: { kind: "" } });
  if (v.scanned) out.push({ key: "scanned", label: v.scanned === "true" ? "Has scans" : "No scans", clear: { scanned: "" } });
  if (v.fy) out.push({ key: "fy", label: `FY ${v.fy}`, clear: { fy: "" } });
  if (v.year) out.push({ key: "year", label: `Year ${v.year}`, clear: { year: "" } });
  if (v.from || v.to) out.push({ key: "dates", label: v.from && v.to ? `Dated ${day(v.from)} to ${day(v.to)}` : v.from ? `Dated from ${day(v.from)}` : `Dated up to ${day(v.to)}`, clear: { from: "", to: "" } });
  if (v.folder) out.push({ key: "folder", label: `In ${names.folder(v.folder)}${v.within ? `/${v.within}` : ""}`, clear: { folder: "", within: "" } });
  if (v.tag) out.push({ key: "tag", label: `Tagged ${v.tag}`, clear: { tag: "" } });
  return out;
}

/** The rows in groups, for "group by": in the order of the sort for dates, alphabetically otherwise. */
function grouped(rows: DocumentRow[], group: Group, sort: string, types: Record<string, string>): { key: string; label: string; rows: DocumentRow[] }[] {
  if (group === "none") return [{ key: "all", label: "", rows }];
  const groups = new Map<string, { key: string; label: string; rows: DocumentRow[]; order: string }>();
  for (const r of rows) {
    const when = r.doc_date ?? r.ingested_at.slice(0, 10);
    const [k, label, order] =
      group === "client" ? [String(r.company_id ?? ""), r.client ?? "No client", r.client ? `0${r.client.toLowerCase()}` : "1"]
      : group === "type" ? [r.doc_type, types[r.doc_type] ?? titleCase(r.doc_type), (types[r.doc_type] ?? r.doc_type).toLowerCase()]
      : group === "fy" ? [r.fy ?? "", r.fy ? `FY ${r.fy}` : "No date", r.fy ?? "0000"]
      : group === "month" ? [when.slice(0, 7), month(when), when.slice(0, 7)]
      : [r.source_folder ?? (r.folder_id ? "" : "~"), r.source_folder || (r.folder_id ? "The top of the folder" : "Not from a folder"), r.source_folder ? `0${r.source_folder.toLowerCase()}` : r.folder_id ? "0" : "1"];
    if (!groups.has(k)) groups.set(k, { key: k || "-", label, rows: [], order });
    groups.get(k)!.rows.push(r);
  }
  const list = Array.from(groups.values());
  const byDate = group === "fy" || group === "month";
  list.sort((a, b) => (byDate ? (sort === "oldest" ? a.order.localeCompare(b.order) : b.order.localeCompare(a.order)) : a.order.localeCompare(b.order)));
  return list;
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
