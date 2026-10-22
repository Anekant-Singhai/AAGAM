import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ReactNode } from "react";
import { BookMarked, Briefcase, Building2, Fingerprint, Landmark, Loader2, StickyNote, Users } from "lucide-react";
import { aagam } from "../api/aagam";
import { Marked, crore, day, titleCase } from "../lib/format";
import TagBadge from "../components/tags/TagBadge";
import { noteHref, personKey } from "../components/CommandPalette";
import type { Everything } from "../types";

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const docType = params.get("type") ?? "";
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity });
  const { data, isFetching, error } = useQuery({
    queryKey: ["search", q, docType],
    queryFn: () => aagam.search(q, { doc_type: docType || undefined }),
    enabled: q.trim().length > 0,
  });
  const { data: more } = useQuery({ queryKey: ["everything", q.trim()], queryFn: () => aagam.everything(q.trim()), enabled: q.trim().length >= 2 });

  return (
    <div className="px-8 py-6 max-w-7xl grid xl:grid-cols-[1fr_320px] gap-6 items-start">
    <div className="space-y-4 min-w-0">
      <div className="flex items-center gap-3">
        <h1 className="text-[1.6rem] leading-tight font-semibold mr-auto">{q ? <>Results for “{q.replace(/"/g, "")}”</> : "Search"}</h1>
        <select
          className="input py-1"
          value={docType}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            if (e.target.value) next.set("type", e.target.value);
            else next.delete("type");
            setParams(next);
          }}
          aria-label="Only this type"
        >
          <option value="">All types</option>
          {Object.entries(meta?.doc_types ?? {}).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      </div>
      {!q && (
        <div className="card p-4 text-sm text-text-secondary space-y-1">
          <p>Type in the bar above. Every word must appear on the page; words of three letters or more also match longer words (“guarant” finds guarantee and guarantees).</p>
          <p>Put words in quotes to find them together: <code>"principal business activities"</code>. CINs, DINs and section numbers work too.</p>
        </div>
      )}
      {isFetching && <p className="text-text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Searching…</p>}
      {error && <p className="text-accent-red">{(error as Error).message}</p>}
      {data && (
        <p className="text-sm text-text-muted">
          {data.matching_documents} document{data.matching_documents === 1 ? "" : "s"} match.
        </p>
      )}
      <div className="space-y-3 stagger" key={q}>
        {data?.documents.map((hit) => (
          <div key={hit.document_id} className="card p-4">
            <div className="flex items-baseline gap-2">
              <Link to={`/documents/${hit.document_id}?page=${hit.pages[0]}&q=${encodeURIComponent(q.replace(/"/g, ""))}`} className="font-medium hover:text-accent-brand">
                {hit.title || hit.original_name}
              </Link>
              <span className="text-xs text-text-muted">{titleCase(hit.doc_type)}{hit.company_name ? ` · ${hit.company_name}` : ""}</span>
              <span className="text-xs text-text-muted ml-auto">pages {hit.pages.slice(0, 12).join(", ")}{hit.pages.length > 12 ? "…" : ""}</span>
            </div>
            <div className="mt-2 space-y-1.5">
              {hit.passages.map((p, i) => (
                <Link key={i} to={`/documents/${hit.document_id}?page=${p.page}&q=${encodeURIComponent(q.replace(/"/g, ""))}`} className="block text-sm text-text-secondary hover:bg-bg-hover rounded px-2 py-1 -mx-2">
                  <span className="text-xs text-text-muted mr-2">p.{p.page}</span>
                  <Marked text={p.text} />
                </Link>
              ))}
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {hit.tags.slice(0, 8).map((t) => <TagBadge key={t.name} tag={t.name} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
    {more && <AlsoFound data={more} />}
    </div>
  );
}

function AlsoFound({ data }: { data: Everything }) {
  const groups: { title: string; icon: ReactNode; rows: { key: string; to: string; label: ReactNode; hint?: ReactNode }[] }[] = [
    { title: "Work", icon: <Briefcase size={13} />, rows: data.works.map((w) => ({ key: `w${w.id}`, to: `/work/${w.id}`, label: w.title, hint: `${w.kind_label} · ${w.status}` })) },
    { title: "Notes", icon: <StickyNote size={13} />, rows: data.notes.map((n) => ({ key: `n${n.id}`, to: noteHref(n.target_kind, n.target), label: n.snippet ? <Marked text={n.snippet} /> : n.text.slice(0, 100) })) },
    {
      title: "People and companies", icon: <Users size={13} />,
      rows: data.entities.slice(0, 8).map((e) => ({ key: `e${e.kind}${e.key}`, to: `/entities/${e.kind}/${encodeURIComponent(e.key)}`, label: e.name, hint: `${titleCase(e.kind)} · ${e.documents} document${e.documents === 1 ? "" : "s"}` })),
    },
    {
      title: "Company file", icon: <Building2 size={13} />,
      rows: [
        ...data.companies.map((c) => ({ key: `c${c.id}`, to: `/companies/${c.id}`, label: c.name, hint: c.cin ?? undefined })),
        ...data.people.map((p) => ({ key: `p${p.id}`, to: `/entities/person/${encodeURIComponent(personKey(p.name))}`, label: p.name, hint: p.din ? `DIN ${p.din}` : undefined })),
      ],
    },
    { title: "Financial statements", icon: <Landmark size={13} />, rows: data.financials.map((f) => ({ key: `f${f.id}`, to: `/financials/${f.id}`, label: f.company_name || f.client || "Statements", hint: f.period_end ? `Year to ${day(f.period_end)}` : undefined })) },
    {
      title: "Resolutions", icon: <BookMarked size={13} />,
      rows: data.resolutions.map((r) => ({ key: `r${r.id}`, to: `/precedents?open=${r.id}`, label: r.title, hint: [r.company_name, r.max_amount ? crore(r.max_amount) : null].filter(Boolean).join(" · ") })),
    },
  ].filter((g) => g.rows.length);
  if (!groups.length && !data.looks_like) return null;
  return (
    <aside className="space-y-3 xl:sticky xl:top-0">
      <p className="label">Also in AAGAM</p>
      {data.looks_like && ["cin", "llpin", "gstin", "din"].includes(data.looks_like) && (
        <Link to={`/entities/${data.looks_like}/${encodeURIComponent(data.looks_like === "din" ? data.query.replace(/\s/g, "") : data.query.replace(/\s/g, "").toUpperCase())}`} className="card card-hover p-3 flex items-center gap-2 text-sm">
          <Fingerprint size={14} className="text-accent-brand" /> That's {data.looks_like === "llpin" ? "an" : "a"} {data.looks_like.toUpperCase()}: open its dossier
        </Link>
      )}
      {groups.map((g) => (
        <section key={g.title} className="card p-3">
          <p className="text-xs font-medium text-text-secondary flex items-center gap-1.5 mb-1.5">{g.icon} {g.title}</p>
          <ul className="space-y-1">
            {g.rows.map((r) => (
              <li key={r.key}>
                <Link to={r.to} className="block rounded px-1.5 py-1 -mx-1.5 hover:bg-bg-hover">
                  <span className="block text-sm truncate">{r.label}</span>
                  {r.hint && <span className="block text-xs text-text-muted truncate">{r.hint}</span>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
