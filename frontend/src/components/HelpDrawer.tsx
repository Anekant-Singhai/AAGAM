import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Lightbulb, X } from "lucide-react";
import { PAGE_HELP, SHORTCUTS } from "../lib/help";

/** The "?" panel: a few lines about the page she is on, the keys, and the way to the full guide. */
export default function HelpDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { pathname } = useLocation();
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose]);
  useEffect(onClose, [pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;
  const page = PAGE_HELP.find(([pattern]) => pattern.test(pathname));

  return (
    <div className="fixed inset-0 z-50" onMouseDown={onClose}>
      <div className="absolute inset-0 bg-black/20 fade-in" />
      <aside
        role="dialog"
        aria-label="Help"
        className="absolute right-0 top-0 bottom-0 w-[380px] max-w-full card rounded-none rounded-l-2xl border-y-0 border-r-0 p-5 overflow-auto slide-in-right"
        style={{ boxShadow: "-20px 0 50px rgb(var(--shadow) / 0.18)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-4">
          <p className="display text-lg font-semibold flex-1">Help</p>
          <button className="btn btn-ghost px-1.5" onClick={onClose} aria-label="Close help"><X size={16} /></button>
        </div>
        {page && (
          <section className="mb-5">
            <p className="label mb-2 flex items-center gap-1.5"><Lightbulb size={12} /> {page[1]}</p>
            <ul className="space-y-2.5 stagger">
              {page[2].map((tip, i) => (
                <li key={i} className="text-sm leading-6 text-text-secondary rounded-lg bg-bg-hover/60 px-3 py-2">{tip}</li>
              ))}
            </ul>
          </section>
        )}
        <section className="mb-5">
          <p className="label mb-2">Keys</p>
          <dl className="space-y-2 text-sm">
            {SHORTCUTS.map(([keys, what]) => (
              <div key={keys} className="flex items-center gap-3">
                <dt className="w-24 shrink-0 flex gap-1">{keys.split(" ").map((k) => <kbd key={k} className="kbd">{k}</kbd>)}</dt>
                <dd className="text-text-secondary">{what}</dd>
              </div>
            ))}
          </dl>
        </section>
        <Link to="/help" className="btn btn-primary w-full justify-center">Everything AAGAM does <ArrowRight size={14} /></Link>
      </aside>
    </div>
  );
}
