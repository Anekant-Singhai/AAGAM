import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, MoreHorizontal, X } from "lucide-react";
import clsx from "clsx";

/** A box over the page: the frame every dialog in AAGAM uses. */
export function Modal({ title, children, onClose, width = "max-w-lg", footer }: {
  title: ReactNode; children: ReactNode; onClose: () => void; width?: string; footer?: ReactNode;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  // Drawn at the top of the page: a card's blur would otherwise hold a dialog opened inside it.
  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-start justify-center pt-[8vh] px-4 overflow-auto pb-10" onMouseDown={onClose}>
      <div className="fixed inset-0 bg-black/30 backdrop-blur-[2px] fade-in" />
      <div
        role="dialog"
        aria-label={typeof title === "string" ? title : undefined}
        className={clsx("relative w-full card p-5 pop-in", width)}
        style={{ boxShadow: "0 24px 60px rgb(var(--shadow) / 0.3)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center mb-4 gap-2">
          <p className="display text-lg font-semibold flex-1">{title}</p>
          <button className="btn btn-ghost px-1.5" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        {children}
        {footer && <div className="flex items-center justify-end gap-2 mt-5">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

interface Choice {
  key: string;
  label: string;
  danger?: boolean;
}
interface Ask {
  title: string;
  body?: ReactNode;
  items?: string[];
  action?: string;
  danger?: boolean;
  choices?: Choice[];
}
type ConfirmFn = (ask: Ask) => Promise<string | false>;
const ConfirmContext = createContext<ConfirmFn>(async () => false);

/** `const confirm = useConfirm(); if (await confirm({...})) …` — resolves to the chosen key ("ok" by default), or false. */
export const useConfirm = () => useContext(ConfirmContext);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [ask, setAsk] = useState<(Ask & { resolve: (v: string | false) => void }) | null>(null);
  const confirm = useCallback<ConfirmFn>((a) => new Promise((resolve) => setAsk({ ...a, resolve })), []);
  const done = (value: string | false) => {
    ask?.resolve(value);
    setAsk(null);
  };
  const choices = ask?.choices ?? [{ key: "ok", label: ask?.action ?? "OK", danger: ask?.danger }];
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {ask && (
        <Modal
          title={ask.title}
          onClose={() => done(false)}
          width="max-w-md"
          footer={
            <>
              <button className="btn" onClick={() => done(false)}>Cancel</button>
              {choices.map((c, i) => (
                <button
                  key={c.key}
                  autoFocus={i === choices.length - 1}
                  className={clsx("btn", c.danger ? "bg-accent-red text-white border-accent-red hover:bg-accent-red" : "btn-primary")}
                  onClick={() => done(c.key)}
                >
                  {c.label}
                </button>
              ))}
            </>
          }
        >
          <div className="flex gap-3">
            {ask.danger && <span className="w-9 h-9 rounded-xl bg-accent-red/10 text-accent-red flex items-center justify-center shrink-0"><AlertTriangle size={18} /></span>}
            <div className="text-sm text-text-secondary leading-6 space-y-2 min-w-0">
              {ask.body && <div>{ask.body}</div>}
              {ask.items && ask.items.length > 0 && (
                <ul className="list-disc pl-5 space-y-0.5">{ask.items.map((it, i) => <li key={i}>{it}</li>)}</ul>
              )}
            </div>
          </div>
        </Modal>
      )}
    </ConfirmContext.Provider>
  );
}

export interface MenuItem {
  label: string;
  icon?: ReactNode;
  onClick: () => void;
  danger?: boolean;
  hidden?: boolean;
}

/** The "⋯" menu: the less frequent actions on a thing, out of the way until wanted. */
export function MoreMenu({ items, label = "More", className }: { items: MenuItem[]; label?: string; className?: string }) {
  const [at, setAt] = useState<{ top: number; right: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const open = at !== null;
  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e.type === "mousedown" && (menu.current?.contains(e.target as Node) || button.current?.contains(e.target as Node))) return;
      setAt(null);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAt(null);
    window.addEventListener("mousedown", close);
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);
  const toggle = () => {
    if (open) return setAt(null);
    const r = button.current!.getBoundingClientRect();
    setAt({ top: r.bottom + 4, right: window.innerWidth - r.right });
  };
  const shown = items.filter((i) => !i.hidden);
  return (
    <div className={clsx("relative", className)}>
      <button ref={button} className="btn btn-ghost px-1.5" onClick={toggle} aria-label={label} aria-expanded={open} title={label}>
        <MoreHorizontal size={16} />
      </button>
      {/* Drawn over everything, so no panel or card can cover it. */}
      {at && createPortal(
        <div ref={menu} role="menu" className="fixed min-w-[220px] card p-1 z-[80] pop-in" style={{ top: at.top, right: at.right, boxShadow: "0 16px 40px rgb(var(--shadow) / 0.2)" }}>
          {shown.map((item, i) => (
            <button
              key={item.label}
              role="menuitem"
              onClick={() => { setAt(null); item.onClick(); }}
              className={clsx(
                "w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-bg-hover",
                item.danger ? "text-accent-red" : "text-text-primary",
                item.danger && i > 0 && "mt-1 border-t border-bg-border rounded-t-none pt-2.5"
              )}
            >
              <span className="w-4 flex justify-center opacity-80">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}

/** Says what a delete takes with it, from the server's count of what depends on the record. */
export function consequences(deps: { deletes: Record<string, number>; unlinks: Record<string, number> }): string[] {
  const words: Record<string, [string, string]> = {
    appointment: ["position (director, KMP)", "positions (directors, KMP)"], meeting: ["meeting", "meetings"], resolution: ["resolution", "resolutions"],
    auditor_appointment: ["auditor appointment", "auditor appointments"], charge: ["charge", "charges"], event: ["event", "events"],
    registration: ["registration", "registrations"], filing: ["filing", "filings"],
  };
  const linked: Record<string, string> = {
    "documents.company_id": "documents stay in the library, no longer tied to it", "works.company_id": "pieces of work stay, without the company",
    "financials.company_id": "sets of accounts stay, without the company", "appointments.meeting_id": "positions stay, without the meeting that approved them",
    "resolutions.meeting_id": "resolutions stay, without the meeting", "auditor_appointments.meeting_id": "auditor appointments stay, without the meeting",
    "charges.holder_id": "charges stay, without the charge holder",
  };
  return [
    ...Object.entries(deps.deletes).map(([k, n]) => `Also deletes ${n} ${(words[k] ?? [k, k])[n === 1 ? 0 : 1]}`),
    ...Object.entries(deps.unlinks).map(([k, n]) => `${n} ${linked[k] ?? `${k} lose the link`}`),
  ];
}
