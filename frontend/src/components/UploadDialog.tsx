import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, FolderOpen, Loader2, Upload, X } from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam, type UploadItem, type UploadResult } from "../api/aagam";
import { asItem, isJunk } from "../lib/drop";
import { bytes, count } from "../lib/format";

const BATCH = 8; // files per request: small enough to show progress, large enough not to crawl
const LISTED = 200; // a big folder lists its first files, then says how many more

const key = (i: UploadItem) => `${i.path || i.file.name}|${i.file.size}`;
const folderOf = (i: UploadItem) => (i.path.includes("/") ? i.path.slice(0, i.path.lastIndexOf("/")) : "");

/** Adding documents: files (and folders) dropped anywhere in the window land here, with the few choices that matter. */
export default function UploadDialog({ open, initial, onClose }: { open: boolean; initial: UploadItem[]; onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [company, setCompany] = useState("auto");
  const [precedent, setPrecedent] = useState(false);
  const [docType, setDocType] = useState("");
  const [sending, setSending] = useState<{ done: number; total: number } | null>(null);
  const stop = useRef(false);
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies(), enabled: open });
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity, enabled: open });
  useEffect(() => {
    if (open) setItems(initial.filter((i) => !isJunk(i.file.name)));
  }, [open, initial]);
  const busy = sending !== null;

  const add = (more: UploadItem[]) =>
    setItems((now) => {
      const seen = new Set(now.map(key));
      return [...now, ...more.filter((m) => !isJunk(m.file.name) && !seen.has(key(m)))];
    });
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (dropped) => add(dropped.map(asItem)),
    disabled: busy,
    noKeyboard: true,
  });

  const folders = useMemo(() => new Set(items.map(folderOf).filter(Boolean)), [items]);
  const size = items.reduce((n, i) => n + i.file.size, 0);

  const upload = async () => {
    stop.current = false;
    const results: UploadResult[] = [];
    setSending({ done: 0, total: items.length });
    try {
      for (let start = 0; start < items.length && !stop.current; start += BATCH) {
        const batch = items.slice(start, start + BATCH);
        try {
          const { results: got } = await aagam.upload(batch, {
            // "auto": each document is filed under the client its CIN, folder or name points to.
            company: precedent ? "" : company,
            doc_type: docType || undefined,
            tags: precedent ? ["precedent"] : [],
          });
          results.push(...got);
        } catch (e) {
          results.push(...batch.map((b) => ({ file: b.path || b.file.name, error: (e as Error).message })));
        }
        setSending({ done: Math.min(start + BATCH, items.length), total: items.length });
      }
    } finally {
      setSending(null);
    }
    const added = results.filter((r) => r.document_id && !r.error && !r.already_on_file);
    const already = results.filter((r) => r.already_on_file);
    const failed = results.filter((r) => r.error);
    const parts = [
      added.length ? `${count(added.length, "document")} added and read` : null,
      already.length ? `${already.length} already in the library` : null,
      failed.length ? `${failed.length} couldn't be read` : null,
    ].filter(Boolean);
    if (added.length || already.length) toast.success(`${parts.join(", ")}.${stop.current ? " Stopped before the rest." : ""}`, { duration: 6000 });
    failed.slice(0, 5).forEach((r) => toast.error(`${r.file}: ${r.error}`, { duration: 8000 }));
    if (failed.length > 5) toast.error(`${failed.length - 5} more couldn't be read.`, { duration: 8000 });
    queryClient.invalidateQueries();
    onClose();
    const opened = [...added, ...already];
    if (opened.length === 1 && results.length === 1) navigate(`/documents/${opened[0].document_id}`);
    else if (opened.length) navigate("/library");
  };

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose, busy]);

  if (!open) return null;
  const pct = sending ? Math.round((sending.done / Math.max(1, sending.total)) * 100) : 0;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] px-4" onMouseDown={() => !busy && onClose()}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px] fade-in" />
      <div role="dialog" aria-label="Add documents" className="relative w-full max-w-xl card p-5 pop-in" style={{ boxShadow: "0 24px 60px rgb(var(--shadow) / 0.3)" }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center mb-3">
          <p className="display text-lg font-semibold flex-1">Add documents</p>
          <button className="btn btn-ghost px-1.5" onClick={onClose} aria-label="Close" disabled={busy}><X size={16} /></button>
        </div>
        <div
          {...getRootProps()}
          className={clsx(
            "border-2 border-dashed rounded-xl px-4 py-5 text-center cursor-pointer transition-colors",
            isDragActive ? "border-accent-brand bg-accent-brand/5" : "border-bg-border hover:border-text-muted"
          )}
        >
          <input {...getInputProps()} aria-label="Choose files to add" />
          <Upload size={20} className="mx-auto text-text-muted mb-1.5" />
          <p className="text-sm text-text-secondary">Drop more files or folders here, or click to choose</p>
          <p className="text-xs text-text-muted mt-0.5">PDF (scanned too), Word, Excel, PowerPoint, Outlook, RTF, HTML, text</p>
        </div>
        {items.length > 0 && (
          <>
            <p className="text-xs text-text-muted mt-3">
              {count(items.length, "file")}{folders.size ? ` from ${count(folders.size, "folder")}` : ""} · {bytes(size)}
              {items.length > 60 && " · For a big folder, Library → Add a folder reads it straight from your computer, and can watch it for new files."}
            </p>
            <ul className="mt-1.5 max-h-44 overflow-auto space-y-1">
              {items.slice(0, LISTED).map((it) => (
                <li key={key(it)} className="flex items-center gap-2 text-sm rounded-lg px-2 py-1 bg-bg-hover/60">
                  <FileText size={13} className="text-text-muted shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{it.file.name}</span>
                    {folderOf(it) && <span className="flex items-center gap-1 text-[11px] text-text-muted truncate"><FolderOpen size={10} /> {folderOf(it)}</span>}
                  </span>
                  <span className="text-xs text-text-muted tabular">{bytes(it.file.size)}</span>
                  <button className="text-text-muted hover:text-accent-red" disabled={busy} onClick={() => setItems(items.filter((x) => x !== it))} aria-label={`Remove ${it.file.name}`}><X size={12} /></button>
                </li>
              ))}
              {items.length > LISTED && <li className="text-xs text-text-muted px-2 py-1">and {count(items.length - LISTED, "more file")}</li>}
            </ul>
          </>
        )}
        <div className="grid sm:grid-cols-2 gap-3 mt-4 text-sm">
          <label className="block">
            <span className="text-xs text-text-muted">Client</span>
            <select className="input w-full mt-0.5" value={precedent ? "" : company} onChange={(e) => setCompany(e.target.value)} aria-label="Client company" disabled={precedent || busy}>
              <option value="auto">Work it out</option>
              <option value="">Not a client's document</option>
              {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
            </select>
            {company === "auto" && !precedent && <span className="block text-[11px] text-text-muted mt-1">From each one's CIN or LLPIN, folder or company name.</span>}
          </label>
          <label className="block">
            <span className="text-xs text-text-muted">Type</span>
            <select className="input w-full mt-0.5" value={docType} onChange={(e) => setDocType(e.target.value)} aria-label="Document type" disabled={busy}>
              <option value="">Work it out</option>
              {Object.entries(meta?.doc_types ?? {}).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm text-text-secondary mt-3">
          <input type="checkbox" checked={precedent} onChange={(e) => setPrecedent(e.target.checked)} disabled={busy} />
          Another company's document, for the precedent library
        </label>
        {sending && (
          <div className="mt-4" aria-live="polite">
            <div className="flex items-center gap-2 text-xs text-text-secondary mb-1">
              <Loader2 size={12} className="animate-spin" />
              <span className="flex-1">Reading {sending.done} of {sending.total}…</span>
              <button className="text-text-muted hover:text-text-primary underline" onClick={() => { stop.current = true; }}>Stop after these</button>
            </div>
            <div className="h-1.5 rounded-full bg-bg-hover overflow-hidden">
              <div className="h-full rounded-full bg-accent-brand transition-[width] duration-300" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
        <div className="flex items-center gap-2 mt-5">
          <span className="text-xs text-text-muted flex-1">Each is read for its type, facts, resolutions and tags.</span>
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-primary" onClick={upload} disabled={!items.length || busy}>
            {busy ? <><Loader2 size={14} className="animate-spin" /> Reading…</> : <>Add {items.length || ""} document{items.length === 1 ? "" : "s"}</>}
          </button>
        </div>
      </div>
    </div>
  );
}
