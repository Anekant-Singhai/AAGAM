import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FolderOpen, FolderSearch, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { bytes, count, skippedHint } from "../lib/format";
import type { FolderPreview } from "../types";
import { Modal } from "./dialogs";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Bringing in a folder from her computer: every file in it and its subfolders, read in the background. */
export default function FolderDialog({ onClose, onStarted }: { onClose: () => void; onStarted?: (folderId: number) => void }) {
  const queryClient = useQueryClient();
  const [path, setPath] = useState("");
  const [company, setCompany] = useState("auto");
  const [docType, setDocType] = useState("");
  const [tags, setTags] = useState("");
  const [precedent, setPrecedent] = useState(false);
  const [watch, setWatch] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const typed = useDebounced(path.trim(), 500);
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies() });
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity });
  const preview = useQuery({
    queryKey: ["folder-preview", typed],
    queryFn: () => aagam.previewFolder(typed),
    enabled: typed.length >= 3,
    retry: false,
    staleTime: 15_000,
  });

  const browse = async () => {
    setBrowsing(true);
    try {
      const { path: chosen } = await aagam.browseFolder();
      if (chosen) setPath(chosen);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBrowsing(false);
    }
  };

  const start = useMutation({
    mutationFn: () =>
      aagam.addFolder({
        path: path.trim(),
        company: precedent ? "none" : company,
        doc_type: docType,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        precedent,
        watch,
      }),
    onSuccess: (folder) => {
      toast.success("Reading the folder in the background. You can keep working; the Library shows how far it has got.", { duration: 6000 });
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      onStarted?.(folder.id);
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const p = preview.data;
  const ready = Boolean(p?.exists && p.files > 0) && !start.isPending;
  return (
    <Modal
      title="Add a folder"
      onClose={onClose}
      width="max-w-2xl"
      footer={
        <>
          <span className="text-xs text-text-muted flex-1">Your files stay where they are. AAGAM keeps its own copy of each and reads it.</span>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!ready} onClick={() => start.mutate()}>
            {start.isPending ? <Loader2 size={14} className="animate-spin" /> : <FolderOpen size={14} />}
            {p?.files ? `Read ${count(p.files, "file")}` : "Read the folder"}
          </button>
        </>
      }
    >
      <p className="text-sm text-text-secondary leading-6 mb-3">
        Every file in the folder, and in the folders inside it, is read: its type, facts and resolutions, the client it belongs to and the date it is of.
        A big folder takes a while; it carries on in the background, and picks up where it stopped if AAGAM is closed.
      </p>
      <div className="flex gap-2">
        <label className="flex-1 min-w-0">
          <span className="text-xs text-text-muted">Folder</span>
          <input
            className="input w-full mt-0.5 font-mono text-[13px]"
            placeholder="For example D:\Clients or C:\Users\you\Documents\Clients"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            aria-label="Folder"
            autoFocus
          />
        </label>
        <button className="btn self-end" onClick={browse} disabled={browsing}>
          {browsing ? <Loader2 size={14} className="animate-spin" /> : <FolderSearch size={14} />} Browse…
        </button>
      </div>
      {browsing && (
        <p className="text-xs text-accent-brand mt-1.5" aria-live="polite">A window to choose the folder has opened on your screen. It may be behind this one.</p>
      )}

      <Preview typed={typed} loading={preview.isFetching} error={preview.error as Error | null} data={p} />

      <div className="grid sm:grid-cols-2 gap-3 mt-4 text-sm">
        <label className="block">
          <span className="text-xs text-text-muted">Client</span>
          <select className="input w-full mt-0.5" value={precedent ? "none" : company} onChange={(e) => setCompany(e.target.value)} disabled={precedent} aria-label="Client for these documents">
            <option value="auto">Work it out for each document</option>
            <option value="none">Not a client's documents</option>
            {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>All of them: {c.name}</option>)}
          </select>
          <span className="block text-[11px] text-text-muted mt-1 leading-4">
            {company === "auto" && !precedent ? "From each document's CIN or LLPIN, the name of the folder it is in, or the company it names." : ""}
          </span>
        </label>
        <label className="block">
          <span className="text-xs text-text-muted">Type</span>
          <select className="input w-full mt-0.5" value={docType} onChange={(e) => setDocType(e.target.value)} aria-label="Type of these documents">
            <option value="">Work it out for each document</option>
            {Object.entries(meta?.doc_types ?? {}).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </label>
        <label className="block sm:col-span-2">
          <span className="text-xs text-text-muted">Tags for every document from here (optional, separated by commas)</span>
          <input className="input w-full mt-0.5" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="e.g. old files, from the office" />
        </label>
      </div>
      <div className="mt-3 space-y-2 text-sm text-text-secondary">
        <label className="flex items-start gap-2">
          <input type="checkbox" className="mt-1" checked={precedent} onChange={(e) => setPrecedent(e.target.checked)} />
          <span>Another company's documents, for the precedent library <span className="text-text-muted">(they aren't filed under a client)</span></span>
        </label>
        <label className="flex items-start gap-2">
          <input type="checkbox" className="mt-1" checked={watch} onChange={(e) => setWatch(e.target.checked)} />
          <span>Keep watching this folder: files saved into it later are read too, while AAGAM is open</span>
        </label>
      </div>
    </Modal>
  );
}

function Preview({ typed, loading, error, data }: { typed: string; loading: boolean; error: Error | null; data?: FolderPreview }) {
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity });
  if (typed.length < 3) return null;
  if (loading && !data) {
    return <p className="text-sm text-text-muted mt-3 flex items-center gap-2"><Loader2 size={13} className="animate-spin" /> Looking in the folder…</p>;
  }
  if (error) {
    return <p className="text-sm text-accent-red mt-3 flex items-start gap-2"><AlertTriangle size={14} className="mt-0.5 shrink-0" /> {error.message}</p>;
  }
  if (!data) return null;
  if (!data.exists) {
    return <p className="text-sm text-accent-amber mt-3 flex items-start gap-2"><AlertTriangle size={14} className="mt-0.5 shrink-0" /> There is no folder at that place. Check the spelling, or use Browse….</p>;
  }
  const kinds = Object.entries(data.by_kind).sort((a, b) => b[1] - a[1]);
  const skipped = Object.entries(data.skipped).sort((a, b) => b[1] - a[1]);
  return (
    <div className={clsx("card p-3 mt-3 text-sm fade-in", loading && "opacity-70")}>
      {data.already_added && (
        <p className="text-xs text-accent-brand mb-2">This folder is already in AAGAM. Reading it again brings in only what is new or changed.</p>
      )}
      <p className="font-medium">
        {data.files ? `${data.truncated ? "At least " : ""}${count(data.files, "file")} AAGAM can read` : "No files AAGAM can read"}
        <span className="text-text-muted font-normal"> · {count(data.folders, "folder")} inside · {bytes(data.bytes)}</span>
      </p>
      {kinds.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {kinds.map(([k, n]) => <span key={k} className="chip tag-1">{meta?.file_kinds?.[k] ?? k.toUpperCase()} {n.toLocaleString("en-IN")}</span>)}
        </div>
      )}
      {(skipped.length > 0 || data.too_big > 0) && (
        <ul className="text-xs text-text-muted mt-2 space-y-0.5">
          {skipped.slice(0, 4).map(([ext, n]) => <li key={ext}>{skippedHint(ext, n)}.</li>)}
          {skipped.length > 4 && <li>…and {count(skipped.slice(4).reduce((s, [, n]) => s + n, 0), "other file")} AAGAM can't read yet.</li>}
          {data.too_big > 0 && <li>{count(data.too_big, "file")} over 60 MB: split them into parts to bring them in.</li>}
        </ul>
      )}
      {data.sample.length > 0 && (
        <ul className="text-xs text-text-muted mt-2 font-mono space-y-0.5 max-h-28 overflow-auto">
          {data.sample.map((s) => <li key={s} className="truncate">{s}</li>)}
          {data.files > data.sample.length && <li>…</li>}
        </ul>
      )}
    </div>
  );
}
