import { ReactNode, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, HelpCircle, Inbox } from "lucide-react";

export function PageHeader({ title, subtitle, actions, icon }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start gap-3 flex-wrap mb-6">
      {icon && <div className="w-10 h-10 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0 pop-in">{icon}</div>}
      <div className="min-w-0 flex-1">
        <h1 className="text-[1.6rem] leading-tight font-semibold">{title}</h1>
        {subtitle && <p className="text-sm text-text-secondary mt-1 max-w-3xl leading-6">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}

export function Empty({ title, hint, icon, action }: { title: string; hint?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card p-10 text-center fade-in">
      <div className="mx-auto w-12 h-12 rounded-2xl bg-accent-brand/10 text-accent-brand flex items-center justify-center mb-3">{icon ?? <Inbox size={20} />}</div>
      <p className="display text-lg font-semibold">{title}</p>
      {hint && <p className="text-sm text-text-muted mt-1 max-w-md mx-auto leading-6">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Section({ title, children, actions, className }: { title: ReactNode; children: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <section className={clsx("card p-4", className)}>
      <div className="flex items-center gap-2 mb-3">
        <p className="label flex-1">{title}</p>
        {actions}
      </div>
      {children}
    </section>
  );
}

const STATUS = {
  ok: { icon: CheckCircle2, cls: "text-accent-green", label: "OK" },
  yes: { icon: CheckCircle2, cls: "text-accent-green", label: "Applies" },
  missing: { icon: AlertTriangle, cls: "text-accent-red", label: "Missing" },
  check: { icon: HelpCircle, cls: "text-accent-amber", label: "Check" },
  verify: { icon: AlertTriangle, cls: "text-accent-amber", label: "Verify" },
  no: { icon: CheckCircle2, cls: "text-text-muted", label: "Doesn't apply" },
  warn: { icon: AlertTriangle, cls: "text-accent-amber", label: "Note" },
  alert: { icon: AlertTriangle, cls: "text-accent-red", label: "Alert" },
  info: { icon: HelpCircle, cls: "text-accent-blue", label: "Note" },
} as const;

/** A status always carries an icon and a word, never colour alone. */
export function Status({ status, showLabel = true }: { status: string; showLabel?: boolean }) {
  const s = STATUS[status as keyof typeof STATUS] ?? STATUS.check;
  const Icon = s.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1 text-xs font-medium shrink-0", s.cls)}>
      <Icon size={14} />
      {showLabel && s.label}
    </span>
  );
}

export function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 min-w-[110px]" title={`${done} of ${total} steps done`}>
      <div className="h-1.5 flex-1 rounded-full bg-bg-hover overflow-hidden">
        <div className="h-full rounded-full bg-accent-brand transition-[width] duration-500 grow-x" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-text-muted tabular">{done}/{total}</span>
    </div>
  );
}

/** Tabs along the top of a page or panel. */
export function Tabs<K extends string>({ tabs, value, onChange, className }: {
  tabs: { key: K; label: ReactNode; count?: number }[]; value: K; onChange: (k: K) => void; className?: string;
}) {
  return (
    <div className={clsx("tabs", className)} role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} className="tab" onClick={() => onChange(t.key)}>
          {t.label}
          {t.count ? <span className="ml-1.5 text-[11px] tabular rounded-full bg-bg-hover px-1.5 text-text-muted">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

/** The loading state of a page: grey shapes where the content will be. */
export function PageSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="p-6 max-w-6xl space-y-4" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-8 w-72" />
      <Skeleton className="h-4 w-[28rem] max-w-full" />
      <div className="grid md:grid-cols-3 gap-3 pt-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24" />)}</div>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-14" />)}
    </div>
  );
}

/** A number that counts up to its value when it first appears. */
export function CountUp({ value, format = (n: number) => n.toLocaleString("en-IN") }: { value: number; format?: (n: number) => string }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const begin = from.current;
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 700);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(Math.round(begin + (value - begin) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
      else from.current = value;
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <>{format(shown)}</>;
}
