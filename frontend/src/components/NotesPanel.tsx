import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pin, PinOff, StickyNote, Trash2 } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { ago, byWhom } from "../lib/format";
import type { Note } from "../types";
import { useConfirm } from "./dialogs";

/** Her notes on one thing: a document, a work, a company, a person, a set of financial statements. */
export default function NotesPanel({ kind, target, initial, compact }: { kind: string; target: string; initial?: Note[]; compact?: boolean }) {
  const queryClient = useQueryClient();
  const key = ["notes", kind, target];
  const { data } = useQuery({ queryKey: key, queryFn: () => aagam.notes({ target_kind: kind, target }), initialData: initial ? { notes: initial } : undefined });
  const [text, setText] = useState("");
  const done = () => {
    queryClient.invalidateQueries({ queryKey: ["notes"] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
  };
  const add = useMutation({
    mutationFn: () => aagam.addNote({ text, target_kind: kind, target }),
    onSuccess: () => { setText(""); done(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const notes = data?.notes ?? [];

  return (
    <section className="card p-3 space-y-2">
      <p className="label flex items-center gap-1.5"><StickyNote size={12} /> Notes {notes.length > 0 && <span className="normal-case tracking-normal font-normal">({notes.length})</span>}</p>
      <ul className="space-y-2">
        {notes.map((n) => <NoteItem key={n.id} note={n} onChange={done} />)}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) add.mutate();
        }}
        className="space-y-1.5"
      >
        <textarea
          className={clsx("input w-full text-sm resize-y", compact ? "h-14" : "h-20")}
          placeholder="Write a note: what the client said, what to check, where you left off…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim()) add.mutate();
          }}
          aria-label="New note"
        />
        {text.trim() && (
          <div className="flex items-center gap-2">
            <button className="btn btn-primary py-1" disabled={add.isPending}>Save note</button>
            <span className="text-xs text-text-muted">Ctrl+Enter saves</span>
          </div>
        )}
      </form>
    </section>
  );
}

export function NoteItem({ note, onChange, showTarget }: { note: Note; onChange: () => void; showTarget?: React.ReactNode }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(note.text);
  const change = useMutation({
    mutationFn: (body: { text?: string; pinned?: boolean }) => aagam.changeNote(note.id, body),
    onSuccess: () => { setEditing(false); onChange(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const remove = useMutation({ mutationFn: () => aagam.deleteNote(note.id), onSuccess: () => { toast.success("Note deleted."); onChange(); } });
  const confirm = useConfirm();

  return (
    <li className={clsx("group rounded-lg border px-3 py-2 text-sm", note.pinned ? "border-accent-amber/50 bg-accent-amber/5" : "border-bg-border")}>
      {editing ? (
        <div className="space-y-1.5">
          <textarea className="input w-full h-24 text-sm" value={text} onChange={(e) => setText(e.target.value)} aria-label="Edit note" />
          <div className="flex gap-2">
            <button className="btn btn-primary py-0.5" onClick={() => change.mutate({ text })}>Save</button>
            <button className="btn py-0.5" onClick={() => { setEditing(false); setText(note.text); }}>Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <p className="whitespace-pre-wrap leading-6 cursor-text" onDoubleClick={() => setEditing(true)} title="Double-click to edit">{note.text}</p>
          <div className="flex items-center gap-2 mt-1 text-xs text-text-muted">
            {showTarget}
            <span>{byWhom(note.by)} · {ago(note.updated_at)}</span>
            <span className="ml-auto flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
              <button className="hover:text-text-primary" onClick={() => setEditing(true)}>Edit</button>
              <button className="hover:text-text-primary p-0.5" onClick={() => change.mutate({ pinned: !note.pinned })} aria-label={note.pinned ? "Unpin" : "Pin"} title={note.pinned ? "Unpin" : "Pin to Home"}>
                {note.pinned ? <PinOff size={12} /> : <Pin size={12} />}
              </button>
              <button
                className="hover:text-accent-red p-0.5"
                onClick={async () => { if (await confirm({ title: "Delete this note?", body: note.text.slice(0, 160), action: "Delete note", danger: true })) remove.mutate(); }}
                aria-label="Delete note"
              >
                <Trash2 size={12} />
              </button>
            </span>
          </div>
        </>
      )}
    </li>
  );
}
