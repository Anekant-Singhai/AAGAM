import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookMarked, Building2, EyeOff, ExternalLink, FileText, Landmark, Link2, Pencil, RotateCcw } from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { crore, day, highlightWords, titleCase } from "../lib/format";
import { Section } from "../components/ui";
import NotesPanel from "../components/NotesPanel";
import { MoreMenu, useConfirm } from "../components/dialogs";
import { KindIcon, initials, kindOne } from "./EntitiesPage";
import type { Dossier } from "../types";

export default function DossierPage() {
  const { kind = "", key = "" } = useParams();
  const navigate = useNavigate();
  const { data: d, error } = useQuery({ queryKey: ["dossier", kind, key], queryFn: () => aagam.dossier(kind, key) });
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [naming, setNaming] = useState<string | null>(null);
  const changed = () => {
    queryClient.invalidateQueries({ queryKey: ["dossier", kind, key] });
    queryClient.invalidateQueries({ queryKey: ["entities"] });
  };
  const saveName = async (name: string | null) => {
    await aagam.renameEntity(kind, key, name);
    setNaming(null);
    changed();
    toast.success(name ? `Shown as “${name}” from now on.` : "Shown under the name found in the documents.");
  };
  const hide = async () => {
    const ok = await confirm({
      title: `Hide “${d?.name}” everywhere?`,
      body: "For a name that isn't a real person or company (a heading, a misreading). Its mentions are taken out of every document, and stay out when documents are read again. It can be brought back from People and companies → Hidden.",
      action: "Hide everywhere",
      danger: true,
    });
    if (!ok) return;
    await aagam.hideEntity(kind, key);
    changed();
    toast.success("Hidden.");
    navigate("/entities");
  };

  if (error) return <p className="p-6 text-accent-red">{(error as Error).message}</p>;
  if (!d) return <p className="p-6 text-text-muted">Putting the dossier together…</p>;

  const mono = ["din", "cin", "llpin", "gstin", "frn", "membership_no"].includes(d.kind);
  const others = d.spellings.filter((s) => s !== d.name);
  const pages = d.documents.reduce((n, doc) => n + doc.pages.length, 0);

  return (
    <div className="px-8 py-6 max-w-6xl">
      <div className="flex items-start gap-4 mb-6">
        <button onClick={() => navigate(-1)} className="text-text-muted hover:text-text-primary mt-3" aria-label="Back"><ArrowLeft size={16} /></button>
        <div className="w-14 h-14 rounded-2xl bg-accent-brand text-on-accent flex items-center justify-center text-lg font-semibold shrink-0 shadow-sm pop-in">
          {d.kind === "person" || d.kind === "company" ? initials(d.name) : <KindIcon kind={d.kind} size={22} />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="label">{kindOne(d.kind)} · dossier</p>
          {naming !== null ? (
            <form className="flex items-center gap-2 mt-1" onSubmit={(e) => { e.preventDefault(); saveName(naming.trim() || null); }}>
              <input className="input text-xl font-semibold display flex-1 max-w-xl" autoFocus value={naming} onChange={(e) => setNaming(e.target.value)} aria-label="Name to show" />
              <button className="btn btn-primary">Save</button>
              <button type="button" className="btn" onClick={() => setNaming(null)}>Cancel</button>
            </form>
          ) : (
            <h1 className={clsx("text-[1.75rem] leading-tight font-semibold mt-0.5 group", mono && "font-mono")}>
              {d.name}
              <button className="ml-2 align-middle text-text-muted hover:text-accent-brand opacity-0 group-hover:opacity-100 transition-opacity" onClick={() => setNaming(d.name)} aria-label="Change the name shown" title="Change the name shown"><Pencil size={15} /></button>
            </h1>
          )}
          <p className="text-sm text-text-secondary mt-1">
            In {d.documents.length} document{d.documents.length === 1 ? "" : "s"}, on {pages} page{pages === 1 ? "" : "s"}
            {others.length > 0 && <span className="text-text-muted"> · also written {others.slice(0, 4).map((s) => `“${s}”`).join(", ")}</span>}
            {d.chosen_name && <span className="text-accent-green"> · name chosen by you</span>}
          </p>
        </div>
        <MoreMenu items={[
          { label: "Change the name shown", icon: <Pencil size={14} />, onClick: () => setNaming(d.name) },
          { label: "Use the name found in the documents", icon: <RotateCcw size={14} />, onClick: () => saveName(null), hidden: !d.chosen_name },
          { label: "Not real: hide everywhere", icon: <EyeOff size={14} />, danger: true, onClick: hide },
        ]} />
      </div>

      <div className="grid lg:grid-cols-[1fr_340px] gap-5 items-start">
        <div className="space-y-5">
          <Timeline d={d} />
          {d.resolutions && d.resolutions.length > 0 && (
            <Section title={`Resolutions (${d.resolutions.length})`}>
              <ul className="divide-y divide-bg-border">
                {d.resolutions.slice(0, 30).map((r) => (
                  <li key={r.id} className="py-2 flex items-baseline gap-3 text-sm">
                    <BookMarked size={13} className="text-text-muted shrink-0 translate-y-0.5" />
                    <Link to={`/precedents?open=${r.id}`} className="flex-1 hover:text-accent-brand">{r.title}</Link>
                    <span className="text-xs text-text-muted shrink-0">
                      {[r.resolution_kind && titleCase(r.resolution_kind), r.max_amount ? crore(r.max_amount) : null, r.meeting_date && day(r.meeting_date)].filter(Boolean).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>

        <div className="space-y-4">
          {d.gstin && (
            <Section title="What the GSTIN says">
              <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-sm">
                <dt className="text-text-muted">State</dt><dd>{d.gstin.state} <span className="text-text-muted">({d.gstin.state_code})</span></dd>
                <dt className="text-text-muted">PAN inside</dt><dd className="font-mono">{d.gstin.pan}</dd>
                <dt className="text-text-muted">PAN holder</dt><dd>{d.gstin.pan_holder}</dd>
                <dt className="text-text-muted">Registration</dt><dd>No. {d.gstin.registration_no} on this PAN in the state</dd>
              </dl>
              <p className="text-xs text-text-muted mt-2">{d.gstin.note}</p>
              <a className="btn mt-2 text-xs" href={d.gstin.verify_url} target="_blank" rel="noreferrer"><ExternalLink size={12} /> GST portal search</a>
            </Section>
          )}
          {d.cin && (
            <Section title="What the CIN says">
              <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-sm">
                <dt className="text-text-muted">Listed</dt><dd>{d.cin.listed ? "Yes" : "No"}</dd>
                <dt className="text-text-muted">Kind</dt><dd>{d.cin.ownership ? titleCase(d.cin.ownership) : "—"}</dd>
                <dt className="text-text-muted">State (ROC)</dt><dd>{d.cin.state}</dd>
                <dt className="text-text-muted">Incorporated</dt><dd>{d.cin.year}</dd>
                <dt className="text-text-muted">Industry (NIC)</dt><dd className="font-mono">{d.cin.nic_code}</dd>
              </dl>
            </Section>
          )}
          {Object.keys(d.identifiers).length > 0 && (
            <Section title="Identifiers">
              <dl className="space-y-2 text-sm">
                {Object.entries(d.identifiers).map(([label, values]) => (
                  <div key={label}>
                    <dt className="text-xs text-text-muted">{label}</dt>
                    <dd className="flex flex-wrap gap-1.5 mt-0.5">
                      {values.map((v) => {
                        const k = label.startsWith("DIN") ? "din" : label.includes("LLPIN") ? "llpin" : label.includes("CIN") ? "cin" : label === "Named as" ? "person" : null;
                        const target = k === "person" ? v.toLowerCase().replace(/^(mr|ms|mrs|shri|smt|dr)\.?\s+/, "").replace(/[^a-z]+/g, " ").trim() : k === "din" ? v.toLowerCase() : v;
                        return k ? (
                          <Link key={v} to={`/entities/${k}/${encodeURIComponent(target)}`} className={clsx("chip tag-0", k !== "person" && "font-mono")}>{v}</Link>
                        ) : <span key={v} className="chip tag-0 font-mono">{v}</span>;
                      })}
                    </dd>
                  </div>
                ))}
              </dl>
            </Section>
          )}
          <CompanyFile d={d} />
          {d.financials && d.financials.length > 0 && (
            <Section title="Financial statements">
              <ul className="space-y-1">
                {d.financials.map((f) => (
                  <li key={f.id}>
                    <Link to={`/financials/${f.id}`} className="flex items-center gap-2 text-sm hover:text-accent-brand">
                      <Landmark size={13} className="text-text-muted" /> {titleCase(f.basis)}{f.period_end ? `, year to ${day(f.period_end)}` : ""}
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {d.appears_with.length > 0 && (
            <Section title="Appears with">
              <ul className="space-y-1">
                {d.appears_with.slice(0, 14).map((a) => (
                  <li key={`${a.kind}-${a.key}`}>
                    <Link to={`/entities/${a.kind}/${encodeURIComponent(a.key)}`} className="flex items-center gap-2 text-sm hover:text-accent-brand">
                      <span className="text-text-muted"><KindIcon kind={a.kind} size={13} /></span>
                      <span className={clsx("truncate flex-1", ["din", "frn"].includes(a.kind) && "font-mono text-[13px]")}>{a.name}</span>
                      <span className="text-xs text-text-muted tabular shrink-0" title="Documents in common">{a.documents}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          <NotesPanel kind="entity" target={`${d.kind}:${d.key}`} compact />
        </div>
      </div>
    </div>
  );
}

/** The words to mark in the contexts: a person's names without the title, a company's first two words (its distinctive part). */
function markWords(d: Dossier): string {
  if (d.kind === "person") return d.name.replace(/^(mr|ms|mrs|shri|smt|sri|dr)\.?\s+/i, "");
  if (d.kind === "company") return d.name.replace(/^the\s+/i, "").split(/\s+/).slice(0, 2).join(" ");
  return d.name;
}

function Timeline({ d }: { d: Dossier }) {
  return (
    <Section title="Where they appear">
      <ol className="relative stagger">
        {d.documents.map((doc, i) => (
          <li key={doc.document_id} className="relative pl-6 pb-5 last:pb-0">
            {i < d.documents.length - 1 && <span className="absolute left-[7px] top-4 bottom-0 w-px bg-bg-border" aria-hidden />}
            <span className="absolute left-0 top-1.5 w-[15px] h-[15px] rounded-full border-2 border-accent-brand bg-bg-surface" aria-hidden />
            <div className="flex items-baseline gap-2 flex-wrap">
              <Link to={`/documents/${doc.document_id}?page=${doc.pages[0] ?? 1}`} className="font-medium hover:text-accent-brand">{doc.title}</Link>
              <span className="text-xs text-text-muted">{titleCase(doc.doc_type)} · {doc.meeting_date ? `meeting ${day(doc.meeting_date)}` : `added ${day(doc.added)}`}</span>
            </div>
            <div className="mt-1.5 space-y-1.5">
              {doc.contexts.map((c, j) => (
                <Link
                  key={j}
                  to={`/documents/${doc.document_id}?page=${c.page}`}
                  className="block text-sm text-text-secondary leading-6 rounded-md px-2.5 py-1.5 bg-bg-secondary hover:bg-bg-hover border border-bg-border/70"
                >
                  <span className="text-xs text-text-muted mr-2">p.{c.page}</span>
                  {highlightWords(c.text, markWords(d))}
                </Link>
              ))}
            </div>
            {doc.pages.length > doc.contexts.length && (
              <p className="text-xs text-text-muted mt-1 flex flex-wrap gap-1.5 items-center">
                Also on page
                {doc.pages.filter((p) => !doc.contexts.some((c) => c.page === p)).slice(0, 12).map((p) => (
                  <Link key={p} to={`/documents/${doc.document_id}?page=${p}`} className="text-accent-brand hover:underline">{p}</Link>
                ))}
              </p>
            )}
          </li>
        ))}
      </ol>
    </Section>
  );
}

function CompanyFile({ d }: { d: Dossier }) {
  if (!d.company_file.length) {
    return (
      <Section title="Company file">
        <p className="text-sm text-text-muted">Not in the company file. {d.kind === "company" ? "Add the company to keep its due dates and filings." : d.kind === "person" ? "Add them as a director or KMP to track appointments." : ""}</p>
      </Section>
    );
  }
  return (
    <Section title="Company file">
      <div className="space-y-3">
        {d.company_file.map((r) => (
          <div key={`${r.type}-${r.id}`} className="text-sm">
            <p className="font-medium flex items-center gap-1.5">
              {r.type === "company" ? <Building2 size={13} className="text-text-muted" /> : <Link2 size={13} className="text-text-muted" />}
              {r.type === "company" ? <Link to={`/companies/${r.id}`} className="hover:text-accent-brand">{r.name}</Link> : r.name}
            </p>
            <p className="text-xs text-text-muted font-mono">{r.cin ?? (r.din ? `DIN ${r.din}` : "")}{r.matched_by ? <span className="font-sans"> · matched by {r.matched_by}</span> : null}</p>
            {r.appointments && r.appointments.length > 0 && (
              <ul className="mt-1.5 space-y-1">
                {r.appointments.map((a, i) => (
                  <li key={i} className="flex items-baseline gap-2 text-xs">
                    <FileText size={11} className="text-text-muted shrink-0" />
                    <span className="flex-1"><span className="text-text-primary">{titleCase(a.role)}</span>, {a.company}</span>
                    <span className="text-text-muted shrink-0">{day(a.date_of_appointment)}{a.date_of_cessation ? ` – ${day(a.date_of_cessation)}` : " –"}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}
