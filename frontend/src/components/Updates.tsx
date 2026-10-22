import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2, RefreshCw, Sparkles, X } from "lucide-react";
import { aagam } from "../api/aagam";
import { health, missing } from "../api/client";

/** This copy of AAGAM and its updates. Asked for at most every ten minutes; an older AAGAM without it simply shows nothing. */
export function useSystem(fresh = false) {
  return useQuery({
    queryKey: ["system"],
    queryFn: aagam.system,
    staleTime: fresh ? 0 : 10 * 60_000,
    refetchInterval: (q) => (["checking", "downloading", "applying"].includes(q.state.data?.updates.status ?? "") ? 3_000 : 10 * 60_000),
    retry: (n, e) => !missing(e) && n < 1,
  });
}

/** The quiet note on Home when a new version is ready. Hidden for the rest of the visit once she closes it. */
export function UpdateBanner() {
  const { data } = useSystem();
  const [closedFor, setClosedFor] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem("aagam.update.hidden");
    } catch {
      return null;
    }
  });
  const latest = data?.updates.latest;
  if (!data?.updates.available || !latest || closedFor === latest.commit) return null;
  const changes = data.updates.changes.length;
  const close = () => {
    setClosedFor(latest.commit);
    try {
      sessionStorage.setItem("aagam.update.hidden", latest.commit);
    } catch {
      /* ignore */
    }
  };
  return (
    <div className="card p-4 mb-5 flex items-center gap-4 pop-in border-accent-brand/30" role="status">
      <span className="w-10 h-10 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0"><Sparkles size={19} /></span>
      <div className="flex-1 min-w-0">
        <p className="font-medium">A new version of AAGAM is ready</p>
        <p className="text-sm text-text-muted truncate">
          {changes ? `${changes} change${changes === 1 ? "" : "s"}` : "Improvements"}
          {data.updates.changes[0] ? `, the latest: ${data.updates.changes[0].message.split("\n")[0]}` : ""}. Your documents and records are not touched.
        </p>
      </div>
      <Link to="/system" className="btn">What's new</Link>
      <Link to="/system?update=now" className="btn btn-primary"><RefreshCw size={14} /> Update now</Link>
      <button className="btn btn-ghost px-1.5" onClick={close} aria-label="Not now"><X size={15} /></button>
    </div>
  );
}

/** A small mark in the top bar when an update is ready. */
export function UpdatePill() {
  const { data } = useSystem();
  if (!data?.updates.available) return null;
  return (
    <Link to="/system" className="btn btn-ghost py-1 text-accent-brand" title="A new version of AAGAM is ready">
      <Sparkles size={15} /> <span className="hidden lg:inline text-xs">Update ready</span>
    </Link>
  );
}

/**
 * Over the whole window while AAGAM updates: the server stops, puts the new version in place and starts again.
 * It asks every two seconds, and opens the new AAGAM as soon as it answers.
 */
export function UpdatingOverlay({ from, onFailed, title = "Updating AAGAM…" }: {
  from: { version: string; commit: string | null }; onFailed?: (error: string) => void; title?: string;
}) {
  const [slow, setSlow] = useState(false);
  const down = useRef(false);
  useEffect(() => {
    const started = Date.now();
    let stopped = false;
    const tick = async () => {
      if (stopped) return;
      const h = await health();
      if (!h) {
        down.current = true;
      } else if ((h.commit ?? null) !== from.commit || h.version !== from.version || down.current) {
        window.location.reload();
        return;
      } else if (Date.now() - started > 30_000) {
        // Still the old AAGAM and it never went away: the update may have stopped before it began.
        try {
          const system = await aagam.system();
          if (system.updates.status === "failed") {
            onFailed?.(system.updates.error ?? "The update didn't go through.");
            return;
          }
        } catch {
          /* ask again next time */
        }
      }
      if (Date.now() - started > 8 * 60_000) setSlow(true);
      window.setTimeout(tick, 2_000);
    };
    const first = window.setTimeout(tick, 2_000);
    return () => {
      stopped = true;
      window.clearTimeout(first);
    };
  }, [from.commit, from.version, onFailed]);
  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-bg-primary/90 backdrop-blur-sm fade-in" role="alertdialog" aria-live="assertive" aria-label={title}>
      <div className="card p-8 max-w-md text-center pop-in">
        <Loader2 size={30} className="mx-auto text-accent-brand animate-spin mb-3" />
        <p className="display text-xl font-semibold">{title}</p>
        <p className="text-sm text-text-secondary mt-2 leading-6">
          AAGAM closes for a minute while the new version is put in place, then opens again here by itself. Your documents and records are not touched.
        </p>
        {slow && (
          <div className="mt-4 text-sm text-text-secondary">
            <p>It is taking longer than it should. If AAGAM doesn't come back, open it again from the AAGAM shortcut on the desktop.</p>
            <button className="btn mt-3" onClick={() => window.location.reload()}>Try again</button>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
