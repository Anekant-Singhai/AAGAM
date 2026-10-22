import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pin, Search, StickyNote } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { Marked } from "../lib/format";
import { Empty, PageHeader } from "../components/ui";
import { NoteItem } from "../components/NotesPanel";
import { noteHref } from "../components/CommandPalette";
import type { Note } from "../types";

const ON: Record<string, string> = {
  general: "General",
  document: "Document",
  company: "Company",
  entity: "Person or company",
  work: "Work",
  resolution: "Resolution",
  financials: "Financial statements",
};

export default function NotesPage() {
  const [params] = useSearchParams();
  const [q, setQ] = useState("");
  const [only, setOnly] = useState("");
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["notes", "all", q], queryFn: () => aagam.notes({ q }), placeholderData: (p) => p });
  const changed = () => {
    queryClient.invalidateQueries({ queryKey: ["notes"] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
  };
  const notes = (data?.notes ?? []).filter((n) => !only || n.target_kind === only);
  const pinned = notes.filter((n) => n.pinned);
  const rest = notes.filter((n) => !n.pinned);

  return (
    <div className="px-8 py-6 max-w-5xl">
      <PageHeader icon={<StickyNote size={18} />} title="Notes" subtitle="Everything you've written down, on documents, work, companies, people and statements. All of it is searchable." />
      <NewNote autoFocus={params.get("new") === "1"} onSaved={changed} />

      <div className="flex items-center gap-3 my-4 flex-wrap">
        <label className="flex items-center gap-2 input py-1 w-80">
          <Search size={13} className="text-text-muted" />
          <input className="bg-transparent outline-none flex-1" placeholder="Search notes" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search notes" />
        </label>
        <select className="input py-1" value={only} onChange={(e) => setOnly(e.target.value)} aria-label="Notes on">
          <option value="">On anything</option>
          {Object.entries(ON).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <span className="ml-auto text-sm text-text-muted">{data ? `${notes.length} note${notes.length === 1 ? "" : "s"}` : ""}</span>
      </div>

      {!isLoading && notes.length === 0 && <Empty icon={<StickyNote size={18} />} title={q ? "No note matches." : "No notes yet."} hint="Write one above, or on any document, piece of work, dossier or set of statements." />}
      {pinned.length > 0 && (
        <>
          <p className="label mb-2 flex items-center gap-1.5"><Pin size={11} /> Pinned</p>
          <ul className="grid md:grid-cols-2 gap-3 mb-5 stagger">{pinned.map((n) => <Card key={n.id} note={n} onChange={changed} />)}</ul>
        </>
      )}
      {rest.length > 0 && <ul className="grid md:grid-cols-2 gap-3 stagger">{rest.map((n) => <Card key={n.id} note={n} onChange={changed} />)}</ul>}
    </div>
  );
}

function Card({ note, onChange }: { note: Note; onChange: () => void }) {
  const target = note.target_kind === "general" ? null : (
    <Link to={noteHref(note.target_kind, note.target)} className="chip tag-0 hover:opacity-80">
      {ON[note.target_kind] ?? note.target_kind}{note.target_kind === "entity" ? `: ${note.target.split(":").slice(1).join(":")}` : ` ${note.target}`}
    </Link>
  );
  return (
    <div className={clsx("card p-1", note.pinned && "ring-1 ring-accent-amber/40")}>
      {note.snippet && <p className="text-xs text-text-secondary px-3 pt-2"><Marked text={note.snippet} /></p>}
      <ul><NoteItem note={note} onChange={onChange} showTarget={target} /></ul>
    </div>
  );
}

function NewNote({ autoFocus, onSaved }: { autoFocus: boolean; onSaved: () => void }) {
  const [text, setText] = useState("");
  const [pinned, setPinned] = useState(false);
  const add = useMutation({
    mutationFn: () => aagam.addNote({ text, pinned }),
    onSuccess: () => { setText(""); setPinned(false); onSaved(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <form className="card p-3" onSubmit={(e) => { e.preventDefault(); if (text.trim()) add.mutate(); }}>
      <textarea
        className="w-full bg-transparent outline-none resize-y min-h-[64px] text-sm leading-6 placeholder-text-muted"
        placeholder="A general note: a call with a client, a reminder, something to look up…"
        autoFocus={autoFocus}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim() && add.mutate()}
        aria-label="New note"
      />
      <div className="flex items-center gap-3">
        <label className="text-xs text-text-secondary flex items-center gap-1.5"><input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} /> Pin to Home</label>
        <span className="text-xs text-text-muted ml-auto">Ctrl+Enter saves</span>
        <button className="btn btn-primary py-1" disabled={!text.trim() || add.isPending}>Save note</button>
      </div>
    </form>
  );
}
