import { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { aagam } from "../../api/aagam";
import { tagClass } from "../../types";

interface TagPickerProps {
  onAdd: (tag: string) => void;
  existingTags?: string[];
  placeholder?: string;
}

export default function TagPicker({ onAdd, existingTags = [], placeholder = "Add tag" }: TagPickerProps) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const { data } = useQuery({ queryKey: ["tags"], queryFn: aagam.allTags, staleTime: 30_000 });

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const typed = input.trim().toLowerCase();
  const suggestions = (data?.tags ?? [])
    .filter(({ name }) => !existingTags.includes(name) && name.includes(typed))
    .slice(0, 8);

  const commit = (tag: string) => {
    const t = tag.trim().toLowerCase();
    if (!t) return;
    onAdd(t);
    setInput("");
    setOpen(false);
  };

  return (
    <div ref={ref} className="relative inline-block">
      <button
        onClick={() => setOpen(!open)}
        className="chip border border-dashed border-bg-border text-text-muted hover:text-text-secondary"
      >
        <Plus size={10} /> {placeholder}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 w-56 card shadow-lg z-50 animate-fade-in">
          <div className="p-2">
            <input
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commit(input);
                if (e.key === "Escape") setOpen(false);
              }}
              placeholder="Type a tag…"
              className="input w-full text-xs"
            />
          </div>
          {suggestions.length > 0 && (
            <div className="border-t border-bg-border py-1 max-h-48 overflow-auto">
              {suggestions.map(({ name }) => (
                <button key={name} onClick={() => commit(name)} className="flex w-full px-3 py-1.5 hover:bg-bg-hover">
                  <span className={clsx("chip", tagClass(name))}>{name}</span>
                </button>
              ))}
            </div>
          )}
          {typed && !suggestions.find((s) => s.name === typed) && (
            <button onClick={() => commit(input)} className="w-full border-t border-bg-border px-3 py-2 text-xs text-accent-brand hover:bg-bg-hover text-left">
              Create “{typed}”
            </button>
          )}
        </div>
      )}
    </div>
  );
}
