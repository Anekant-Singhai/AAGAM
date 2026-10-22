import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Eye, EyeOff, FolderOpen, Loader2, PauseCircle, RefreshCw, Square, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { missing } from "../api/client";
import { ago, count, skippedHint } from "../lib/format";
import type { Folder } from "../types";
import { Modal, MoreMenu, useConfirm } from "./dialogs";

const busy = (f: Folder) => f.status === "queued" || f.status === "running";

/** The folders on her computer that AAGAM reads, with how far each has got. Hidden when this AAGAM has no folders. */
export function useFolders() {
  return useQuery({
    queryKey: ["folders"],
    queryFn: aagam.folders,
    retry: (n, e) => !missing(e) && n < 2,
    // Watch progress closely only while something is being read.
    refetchInterval: (q) => (q.state.data?.folders.some(busy) ? 2_000 : 30_000),
  });
}

export default function FoldersPanel({ onShow, shown }: { onShow: (folderId: number | null) => void; shown: number | null }) {
  const { data } = useFolders();
  const folders = data?.folders ?? [];
  if (!folders.length) return null;
  const running = folders.filter(busy).length;
  return (
    <section className="card mb-3" aria-label="Folders">
      <div className="flex items-center gap-2 px-4 pt-3 pb-1.5">
        <p className="label flex-1">Folders on your computer</p>
        {running > 0 && <span className="text-xs text-accent-brand flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Reading {count(running, "folder")}</span>}
      </div>
      <ul className="divide-y divide-bg-border">
        {folders.map((f) => <FolderRow key={f.id} folder={f} onShow={onShow} shown={shown === f.id} />)}
      </ul>
    </section>
  );
}

function FolderRow({ folder: f, onShow, shown }: { folder: Folder; onShow: (id: number | null) => void; shown: boolean }) {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [failures, setFailures] = useState(false);
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["folders"] });
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["facets"] });
  };
  const act = async (what: () => Promise<unknown>, done?: string) => {
    try {
      await what();
      if (done) toast.success(done);
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const forget = async () => {
    const choice = await confirm({
      title: `Stop reading “${f.path}”?`,
      body: "AAGAM forgets this folder. Your files in it are not touched.",
      items: [`${count(f.documents, "document")} from it ${f.documents === 1 ? "is" : "are"} in the library`],
      choices: [
        { key: "keep", label: "Keep its documents" },
        ...(f.documents ? [{ key: "trash", label: "Move them to the Trash", danger: true }] : []),
      ],
    });
    if (!choice) return;
    act(async () => {
      const r = await aagam.forgetFolder(f.id, choice as "keep" | "trash");
      toast.success(r.documents_trashed ? `Forgotten. ${count(r.documents_trashed, "document")} moved to the Trash.` : "Forgotten. Its documents stay in the library.");
      if (shown) onShow(null);
    });
  };
  const pct = f.found ? Math.round((f.done / f.found) * 100) : 0;
  const skipped = Object.entries(f.skipped ?? {}).sort((a, b) => b[1] - a[1]);
  const clientText = f.precedent ? "Other companies' documents (precedents)" : f.client_mode === "one" ? `All ${f.client ?? "one client"}'s` : f.client_mode === "none" ? "Not a client's" : "Client worked out for each";

  return (
    <li className={clsx("px-4 py-3", shown && "bg-accent-brand/[0.05]")}>
      <div className="flex items-start gap-3">
        <span className="w-9 h-9 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0"><FolderOpen size={16} /></span>
        <div className="min-w-0 flex-1">
          <p className="font-medium truncate font-mono text-[13px]" title={f.path}>{f.path}</p>
          <p className="text-xs text-text-muted truncate">
            {clientText} · {count(f.documents, "document")} in the library
            {f.watch && <> · <Eye size={11} className="inline -mt-0.5" /> watching for new files</>}
          </p>
          <FolderStatus f={f} pct={pct} />
          {skipped.length > 0 && f.status !== "running" && (
            <p className="text-xs text-text-muted mt-1">{skippedHint(skipped[0][0], skipped[0][1])}.{skipped.length > 1 ? ` And ${count(skipped.slice(1).reduce((s, [, n]) => s + n, 0), "other file")} AAGAM can't read yet.` : ""}</p>
          )}
          {f.failed > 0 && f.status !== "running" && (
            <button className="text-xs text-accent-amber underline mt-1" onClick={() => setFailures(true)}>See the {count(f.failed, "file")} that couldn't be read</button>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button className={clsx("btn py-1 text-xs", shown && "bg-accent-brand/10 text-accent-brand")} onClick={() => onShow(shown ? null : f.id)} aria-pressed={shown}>
            {shown ? "Show all" : "Show its documents"}
          </button>
          {busy(f) ? (
            <button className="btn py-1 text-xs" onClick={() => act(() => aagam.stopFolder(f.id), "Stopped. Look again carries on from here.")}><Square size={12} /> Stop</button>
          ) : (
            <button className="btn py-1 text-xs" onClick={() => act(() => aagam.scanFolder(f.id), "Looking for new and changed files.")} disabled={!f.exists}><RefreshCw size={12} /> Look again</button>
          )}
          <MoreMenu
            label={`More about ${f.path}`}
            items={[
              f.watch
                ? { label: "Stop watching for new files", icon: <EyeOff size={14} />, onClick: () => act(() => aagam.changeFolder(f.id, { watch: false }), "No longer watching this folder.") }
                : { label: "Watch for new files", icon: <Eye size={14} />, onClick: () => act(() => aagam.changeFolder(f.id, { watch: true }), "Files saved into this folder will be read while AAGAM is open.") },
              { label: "Forget this folder", icon: <Trash2 size={14} />, danger: true, onClick: forget },
            ]}
          />
        </div>
      </div>
      {failures && <Failures folder={f} onClose={() => setFailures(false)} />}
    </li>
  );
}

function FolderStatus({ f, pct }: { f: Folder; pct: number }) {
  if (!f.exists) {
    return <p className="text-xs text-accent-amber mt-1 flex items-center gap-1"><AlertTriangle size={12} /> The folder isn't there now: it was moved or renamed, or its drive isn't connected.</p>;
  }
  if (f.status === "running" || f.status === "queued") {
    return (
      <div className="mt-1.5" aria-live="polite">
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <Loader2 size={12} className="animate-spin shrink-0" />
          <span className="truncate">
            {f.status === "queued" ? "Waiting to start…" : f.found ? `Reading ${f.done.toLocaleString("en-IN")} of ${f.found.toLocaleString("en-IN")}` : "Looking through the folder…"}
            {f.current && f.status === "running" ? ` · ${f.current}` : ""}
          </span>
        </div>
        {f.found > 0 && (
          <div className="h-1.5 rounded-full bg-bg-hover overflow-hidden mt-1">
            <div className="h-full rounded-full bg-accent-brand transition-[width] duration-500" style={{ width: `${pct}%` }} />
          </div>
        )}
      </div>
    );
  }
  const counts = [
    f.added ? `${f.added.toLocaleString("en-IN")} added` : null,
    f.already ? `${f.already.toLocaleString("en-IN")} already in the library` : null,
    f.failed ? `${f.failed.toLocaleString("en-IN")} couldn't be read` : null,
  ].filter(Boolean).join(" · ");
  if (f.status === "failed") {
    return <p className="text-xs text-accent-red mt-1 flex items-center gap-1"><AlertTriangle size={12} /> Stopped by a problem: {f.error ?? "unknown"}. Look again to try once more.</p>;
  }
  if (f.status === "stopped") {
    return <p className="text-xs text-text-muted mt-1 flex items-center gap-1"><PauseCircle size={12} /> Stopped after {f.done.toLocaleString("en-IN")} of {f.found.toLocaleString("en-IN")}{counts ? ` · ${counts}` : ""}. Look again carries on.</p>;
  }
  return (
    <p className="text-xs text-text-muted mt-1 flex items-center gap-1">
      <CheckCircle2 size={12} className="text-accent-green" /> Read {f.finished_at ? ago(f.finished_at) : ""}{counts ? ` · ${counts}` : " · nothing new"}
    </p>
  );
}

function Failures({ folder, onClose }: { folder: Folder; onClose: () => void }) {
  const { data, error } = useQuery({ queryKey: ["folder", folder.id], queryFn: () => aagam.folder(folder.id) });
  return (
    <Modal title="Files that couldn't be read" onClose={onClose} width="max-w-2xl">
      <p className="text-sm text-text-secondary mb-3">From {folder.path}. Fix the file (for example, remove its password or save it in another format), then Look again.</p>
      {error ? (
        <p className="text-sm text-accent-red">{(error as Error).message}</p>
      ) : !data ? (
        <p className="text-sm text-text-muted flex items-center gap-2"><Loader2 size={13} className="animate-spin" /> Loading…</p>
      ) : (
        <ul className="divide-y divide-bg-border max-h-[55vh] overflow-auto text-sm">
          {data.failures.map((f) => (
            <li key={f.rel_path} className="py-1.5">
              <p className="font-mono text-[12.5px] break-all">{f.rel_path}</p>
              <p className="text-xs text-text-muted">{f.error}</p>
            </li>
          ))}
          {!data.failures.length && <li className="py-2 text-text-muted">None now.</li>}
        </ul>
      )}
    </Modal>
  );
}
