import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ArchiveRestore, FileText, Loader2, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import { useState } from "react";
import { aagam } from "../api/aagam";
import { missing } from "../api/client";
import { ago, bytes, count } from "../lib/format";
import { Empty, PageHeader, PageSkeleton } from "../components/ui";
import { useConfirm } from "../components/dialogs";

/** The Trash: deleted documents wait here, with what it takes to put them back as they were. */
export default function TrashPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [working, setWorking] = useState<string | null>(null);
  const { data, error } = useQuery({ queryKey: ["trash"], queryFn: aagam.trash, retry: (n, e) => !missing(e) && n < 2 });

  const changed = () => {
    queryClient.invalidateQueries({ queryKey: ["trash"] });
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    queryClient.invalidateQueries({ queryKey: ["facets"] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
  };
  const run = async (key: string, what: () => Promise<void>) => {
    setWorking(key);
    try {
      await what();
      changed();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setWorking(null);
    }
  };

  if (error) {
    return (
      <div className="px-8 py-6 max-w-5xl">
        <PageHeader icon={<Trash2 size={19} />} title="Trash" />
        <p className="text-sm text-text-muted">{missing(error) ? "This copy of AAGAM has no Trash yet. Update AAGAM to get it." : (error as Error).message}</p>
      </div>
    );
  }
  if (!data) return <PageSkeleton rows={3} />;

  const restore = (id: number, name: string) =>
    run(`r${id}`, async () => {
      const r = await aagam.restore(id);
      toast.success(
        (t) => (
          <span>
            “{name}” is back in the library.{" "}
            <button className="underline font-medium" onClick={() => { toast.dismiss(t.id); navigate(`/documents/${r.document_id}`); }}>Open it</button>
          </span>
        ),
        { duration: 7000 }
      );
    });
  const forget = async (id: number, name: string) => {
    const ok = await confirm({
      title: `Delete “${name}” forever?`,
      body: "Its file is removed from your computer, and it can't be put back.",
      action: "Delete forever",
      danger: true,
    });
    if (ok) run(`d${id}`, async () => { await aagam.deleteForever(id); toast.success("Deleted forever."); });
  };
  const empty = async () => {
    const files = data.loose.length;
    const ok = await confirm({
      title: "Empty the Trash?",
      body: "Everything in it is deleted for good. This can't be undone.",
      items: [
        ...(data.count ? [`${count(data.count, "document")}`] : []),
        ...(files ? [`${count(files, "file")} deleted before the Trash existed`] : []),
        `${bytes(data.bytes)} freed on this computer`,
      ],
      action: "Empty the Trash",
      danger: true,
    });
    if (ok) run("empty", async () => {
      const r = await aagam.emptyTrash();
      toast.success(`Emptied: ${count(r.deleted, "document")}${r.files ? ` and ${count(r.files, "file")}` : ""} deleted for good.`);
    });
  };
  const addBack = (name: string) =>
    run(`la${name}`, async () => {
      const r = await aagam.restoreLoose(name);
      toast.success((t) => (
        <span>Added back and read. <button className="underline font-medium" onClick={() => { toast.dismiss(t.id); navigate(`/documents/${r.document_id}`); }}>Open it</button></span>
      ), { duration: 7000 });
    });
  const forgetLoose = async (name: string) => {
    const ok = await confirm({ title: `Delete “${name}” forever?`, body: "The file is removed from your computer.", action: "Delete forever", danger: true });
    if (ok) run(`ld${name}`, async () => { await aagam.deleteLoose(name); toast.success("Deleted forever."); });
  };

  const nothing = !data.items.length && !data.loose.length;
  return (
    <div className="px-8 py-6 max-w-5xl">
      <PageHeader
        icon={<Trash2 size={19} />}
        title="Trash"
        subtitle="Deleted documents wait here. Restore one and it comes back as it was: its pages, your corrections, tags and notes, and the work it was on."
        actions={!nothing && (
          <button className="btn text-accent-red" onClick={empty} disabled={working !== null}>
            {working === "empty" ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} Empty the Trash
          </button>
        )}
      />
      {nothing ? (
        <Empty icon={<Trash2 size={20} />} title="The Trash is empty." hint="When you delete a document it waits here, so you can change your mind." />
      ) : (
        <div className="space-y-5">
          {data.items.length > 0 && (
            <section className="card overflow-hidden">
              <div className="px-4 pt-3 pb-2 flex items-center gap-2">
                <p className="label flex-1">{count(data.count, "document")} · {bytes(data.bytes)}</p>
              </div>
              <ul className="divide-y divide-bg-border stagger">
                {data.items.map((item) => (
                  <li key={item.id} className="px-4 py-3 flex items-center gap-3">
                    <span className="w-9 h-9 rounded-xl bg-bg-hover text-text-muted flex items-center justify-center shrink-0"><FileText size={16} /></span>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{item.name}</p>
                      <p className="text-xs text-text-muted truncate">
                        {item.detail ? `${item.detail} · ` : ""}deleted {ago(item.deleted_at)}{item.size ? ` · ${bytes(item.size)}` : ""}
                      </p>
                      {item.file_missing && (
                        <p className="text-xs text-accent-amber flex items-center gap-1 mt-0.5"><AlertTriangle size={12} /> Its file is no longer in the bin folder, so it can't be restored.</p>
                      )}
                    </div>
                    <button className="btn py-1 text-xs" onClick={() => restore(item.id, item.name)} disabled={item.file_missing || working !== null}>
                      {working === `r${item.id}` ? <Loader2 size={12} className="animate-spin" /> : <ArchiveRestore size={13} />} Restore
                    </button>
                    <button className="btn btn-ghost py-1 text-xs hover:text-accent-red" onClick={() => forget(item.id, item.name)} disabled={working !== null}>
                      {working === `d${item.id}` ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={13} />} Delete forever
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {data.loose.length > 0 && (
            <section className="card overflow-hidden">
              <div className="px-4 pt-3 pb-1">
                <p className="label">Deleted before the Trash existed</p>
                <p className="text-xs text-text-muted mt-1">Only the files were kept for these. Adding one back reads it again as a new document.</p>
              </div>
              <ul className="divide-y divide-bg-border">
                {data.loose.map((f) => (
                  <li key={f.name} className="px-4 py-2.5 flex items-center gap-3">
                    <FileText size={15} className="text-text-muted shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm truncate">{f.name}</p>
                      <p className="text-xs text-text-muted">{bytes(f.size)}{f.modified ? ` · ${ago(f.modified)}` : ""}</p>
                    </div>
                    <button className="btn py-1 text-xs" onClick={() => addBack(f.name)} disabled={working !== null}>
                      {working === `la${f.name}` ? <Loader2 size={12} className="animate-spin" /> : <ArchiveRestore size={13} />} Add back
                    </button>
                    <button className="btn btn-ghost py-1 text-xs hover:text-accent-red" onClick={() => forgetLoose(f.name)} disabled={working !== null}>
                      <Trash2 size={13} /> Delete forever
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
