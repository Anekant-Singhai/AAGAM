import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, EyeOff, Fingerprint, Mail, RotateCcw, Search, ShieldCheck, Users } from "lucide-react";
import toast from "react-hot-toast";
import { day } from "../lib/format";
import { Modal } from "../components/dialogs";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { Empty, PageHeader } from "../components/ui";

export const KIND_LABELS: Record<string, string> = {
  person: "People",
  company: "Companies",
  din: "DINs",
  cin: "CINs",
  gstin: "GSTINs",
  frn: "Audit firms",
  membership_no: "Members",
  email: "Email",
};
const KIND_ONE: Record<string, string> = {
  person: "Person", company: "Company", din: "DIN", cin: "CIN", gstin: "GSTIN", frn: "Audit firm (FRN)", membership_no: "Institute member", email: "Email",
};
export const kindOne = (kind: string) => KIND_ONE[kind] ?? kind;

export function KindIcon({ kind, size = 15 }: { kind: string; size?: number }) {
  if (kind === "person") return <Users size={size} />;
  if (kind === "company" || kind === "cin") return <Building2 size={size} />;
  if (kind === "email") return <Mail size={size} />;
  if (kind === "frn" || kind === "membership_no") return <ShieldCheck size={size} />;
  return <Fingerprint size={size} />;
}

export default function EntitiesPage() {
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "person";
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({ queryKey: ["entities", kind, q], queryFn: () => aagam.entities(kind, q), placeholderData: (p) => p });
  const { data: all } = useQuery({ queryKey: ["entities", "counts"], queryFn: () => aagam.entities(undefined, ""), staleTime: 60_000 });
  const counts = all?.counts ?? {};
  const mono = ["din", "cin", "gstin", "frn", "membership_no"].includes(kind);
  const [showHidden, setShowHidden] = useState(false);
  const { data: hidden } = useQuery({ queryKey: ["entities", "hidden"], queryFn: aagam.hidden });

  return (
    <div className="px-8 py-6 max-w-6xl">
      <PageHeader
        icon={<Users size={18} />}
        title="People and companies"
        subtitle="Everyone and everything named in the library, however it was written, with a dossier on each: every document, page and context, their identifiers and who they appear with."
        actions={hidden && hidden.hidden.length > 0 ? <button className="btn btn-ghost" onClick={() => setShowHidden(true)}><EyeOff size={14} /> Hidden ({hidden.hidden.length})</button> : undefined}
      />
      {showHidden && hidden && <HiddenList rows={hidden.hidden} onClose={() => setShowHidden(false)} />}
      <div className="flex items-center gap-3 flex-wrap mb-4">
        <div className="flex flex-wrap rounded-lg border border-bg-border bg-bg-secondary p-0.5" role="tablist">
          {Object.entries(KIND_LABELS).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={kind === key}
              onClick={() => setParams({ kind: key })}
              className={clsx("px-2.5 py-1 rounded-md text-sm flex items-center gap-1.5", kind === key ? "bg-bg-surface shadow-sm font-medium" : "text-text-secondary hover:text-text-primary")}
            >
              {label}
              {counts[key] ? <span className="text-xs text-text-muted tabular">{counts[key]}</span> : null}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 input py-1 w-64 ml-auto">
          <Search size={13} className="text-text-muted" />
          <input className="bg-transparent outline-none flex-1" placeholder={`Find in ${KIND_LABELS[kind]?.toLowerCase()}`} value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>

      {!isLoading && data && data.entities.length === 0 ? (
        <Empty icon={<KindIcon kind={kind} size={18} />} title={q ? "Nothing matches." : `No ${KIND_LABELS[kind]?.toLowerCase()} found in the library yet.`} hint="They are picked out of every document as it comes in." />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 stagger" key={kind}>
          {data?.entities.map((e) => (
            <Link key={`${e.kind}-${e.key}`} to={`/entities/${e.kind}/${encodeURIComponent(e.key)}`} className="card card-hover p-3.5 flex gap-3 items-start">
              <span className="w-8 h-8 rounded-full bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0 text-xs font-semibold">
                {e.kind === "person" || e.kind === "company" ? initials(e.name) : <KindIcon kind={e.kind} size={14} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className={clsx("block truncate font-medium", mono && "font-mono text-[13px]")}>{e.name}</span>
                {e.detail && <span className="block truncate text-xs text-text-secondary">{e.detail}</span>}
                <span className="block text-xs text-text-muted mt-0.5">{e.documents} document{e.documents === 1 ? "" : "s"} · {e.mentions} mention{e.mentions === 1 ? "" : "s"}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
      {data && data.total > data.entities.length && <p className="text-xs text-text-muted mt-3">Showing {data.entities.length} of {data.total}. Narrow it with the search box.</p>}
    </div>
  );
}

export function initials(name: string): string {
  const words = name.replace(/^(mr|ms|mrs|shri|smt|dr|ca|cs)\.?\s+/i, "").split(/\s+/).filter((w) => /^[A-Za-z]/.test(w));
  return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase() || "·";
}

function HiddenList({ rows, onClose }: { rows: { id: number; kind: string; shown: string | null; key: string; document: string | null; document_id: number | null; created_at: string }[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<number | null>(null);
  const restore = async (id: number) => {
    setBusy(id);
    try {
      await aagam.unhide(id);
      queryClient.invalidateQueries();
      toast.success("Brought back; the documents it can be in were read again.");
    } finally {
      setBusy(null);
    }
  };
  return (
    <Modal title="Hidden facts" onClose={onClose} width="max-w-2xl">
      <p className="text-sm text-text-muted mb-3">Names and numbers you said aren't real facts. Bring one back and the documents it can be in are read again.</p>
      <ul className="divide-y divide-bg-border max-h-[60vh] overflow-auto">
        {rows.map((h) => (
          <li key={h.id} className="flex items-center gap-3 py-2 text-sm">
            <span className="chip tag-0 shrink-0">{kindOne(h.kind)}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate">{h.shown ?? h.key}</span>
              <span className="block text-xs text-text-muted truncate">{h.document_id ? `In ${h.document}` : "Everywhere"} · {day(h.created_at.slice(0, 10))}</span>
            </span>
            <button className="btn py-1 text-xs" disabled={busy === h.id} onClick={() => restore(h.id)}><RotateCcw size={12} /> Bring back</button>
          </li>
        ))}
        {rows.length === 0 && <li className="py-4 text-sm text-text-muted">Nothing hidden.</li>}
      </ul>
    </Modal>
  );
}
