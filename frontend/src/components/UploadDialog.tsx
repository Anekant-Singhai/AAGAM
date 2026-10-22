import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Loader2, Upload, X } from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam } from "../api/aagam";

/** Adding documents: files dropped anywhere in the window land here, with the few choices that matter. */
export default function UploadDialog({ open, initial, onClose }: { open: boolean; initial: File[]; onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [company, setCompany] = useState("");
  const [precedent, setPrecedent] = useState(false);
  const [docType, setDocType] = useState("");
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies(), enabled: open });
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity, enabled: open });
  useEffect(() => {
    if (open) setFiles(initial);
  }, [open, initial]);

  const upload = useMutation({
    mutationFn: () => aagam.upload(files, { company: company || undefined, doc_type: docType || undefined, tags: precedent ? ["precedent"] : [] }),
    onSuccess: ({ results }) => {
      const added = results.filter((r) => r.document_id && !r.error);
      const failed = results.filter((r) => r.error);
      if (added.length) toast.success(`${added.length} document${added.length > 1 ? "s" : ""} added and read.`);
      failed.forEach((r) => toast.error(`${r.file}: ${r.error}`, { duration: 8000 }));
      queryClient.invalidateQueries();
      onClose();
      if (added.length === 1) navigate(`/documents/${added[0].document_id}`);
      else if (added.length > 1) navigate("/library");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (more) => setFiles((now) => [...now, ...more.filter((f) => !now.some((n) => n.name === f.name && n.size === f.size))]),
    disabled: upload.isPending,
    noKeyboard: true,
  });

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !upload.isPending && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose, upload.isPending]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] px-4" onMouseDown={() => !upload.isPending && onClose()}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px] fade-in" />
      <div role="dialog" aria-label="Add documents" className="relative w-full max-w-xl card p-5 pop-in" style={{ boxShadow: "0 24px 60px rgb(var(--shadow) / 0.3)" }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center mb-3">
          <p className="display text-lg font-semibold flex-1">Add documents</p>
          <button className="btn btn-ghost px-1.5" onClick={onClose} aria-label="Close" disabled={upload.isPending}><X size={16} /></button>
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
          <p className="text-sm text-text-secondary">Drop more here, or click to choose</p>
          <p className="text-xs text-text-muted mt-0.5">PDF (scanned too), Word, Excel, PowerPoint, Outlook, RTF, HTML, text</p>
        </div>
        {files.length > 0 && (
          <ul className="mt-3 max-h-40 overflow-auto space-y-1 stagger">
            {files.map((f) => (
              <li key={`${f.name}-${f.size}`} className="flex items-center gap-2 text-sm rounded-lg px-2 py-1 bg-bg-hover/60">
                <FileText size={13} className="text-text-muted shrink-0" />
                <span className="truncate flex-1">{f.name}</span>
                <span className="text-xs text-text-muted tabular">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                <button className="text-text-muted hover:text-accent-red" onClick={() => setFiles(files.filter((x) => x !== f))} aria-label={`Remove ${f.name}`}><X size={12} /></button>
              </li>
            ))}
          </ul>
        )}
        <div className="grid sm:grid-cols-2 gap-3 mt-4 text-sm">
          <label className="block">
            <span className="text-xs text-text-muted">Client</span>
            <select className="input w-full mt-0.5" value={company} onChange={(e) => setCompany(e.target.value)} aria-label="Client company">
              <option value="">None / not a client</option>
              {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-text-muted">Type</span>
            <select className="input w-full mt-0.5" value={docType} onChange={(e) => setDocType(e.target.value)} aria-label="Document type">
              <option value="">Work it out</option>
              {Object.entries(meta?.doc_types ?? {}).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm text-text-secondary mt-3">
          <input type="checkbox" checked={precedent} onChange={(e) => setPrecedent(e.target.checked)} />
          Another company's document, for the precedent library
        </label>
        <div className="flex items-center gap-2 mt-5">
          <span className="text-xs text-text-muted flex-1">Each is read for its type, facts, resolutions and tags.</span>
          <button className="btn" onClick={onClose} disabled={upload.isPending}>Cancel</button>
          <button className="btn btn-primary" onClick={() => upload.mutate()} disabled={!files.length || upload.isPending}>
            {upload.isPending ? <><Loader2 size={14} className="animate-spin" /> Reading…</> : <>Add {files.length || ""} document{files.length === 1 ? "" : "s"}</>}
          </button>
        </div>
      </div>
    </div>
  );
}
