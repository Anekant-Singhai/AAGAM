import { Fragment, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Download, FileText, ScanSearch, Search, X } from "lucide-react";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { titleCase } from "../lib/format";
import type { InsightPurpose, InsightRegister, RegisterItem } from "../types";
import { Empty, PageHeader, Skeleton, Tabs } from "../components/ui";
import { Cell, Confidence, KindIcon, markItem } from "../components/insights";

const SUBTITLE = "Every document is read for what it says about investments, legal matters, the law it cites, amendments, obligations and agreement terms, and each finding is brought together here with its page.";

export default function InsightsPage() {
  const { kind } = useParams();
  const navigate = useNavigate();
  const { data } = useQuery({ queryKey: ["insights"], queryFn: aagam.insights, staleTime: 15_000 });
  const purposes = data?.purposes ?? [];

  return (
    <div className="px-8 py-6 max-w-6xl">
      <PageHeader icon={<ScanSearch size={19} />} title="Insights" subtitle={SUBTITLE} />
      {purposes.length > 0 && (
        <Tabs<string>
          className="mb-4"
          value={kind ?? ""}
          onChange={(k) => navigate(k ? `/insights/${k}` : "/insights")}
          tabs={[{ key: "", label: "All purposes" }, ...purposes.map((p) => ({ key: p.kind, label: p.title, count: p.items }))]}
        />
      )}
      {!data ? (
        <div className="grid md:grid-cols-3 gap-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-32" />)}</div>
      ) : kind ? (
        <Register kind={kind} purpose={purposes.find((p) => p.kind === kind)} />
      ) : (
        <Overview purposes={purposes} />
      )}
    </div>
  );
}

function Overview({ purposes }: { purposes: InsightPurpose[] }) {
  const total = purposes.reduce((n, p) => n + p.items, 0);
  return (
    <>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3 stagger">
        {purposes.map((p) => (
          <Link key={p.kind} to={`/insights/${p.kind}`} className="card card-hover p-4 flex flex-col gap-2">
            <div className="flex items-center gap-2.5">
              <span className="w-9 h-9 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0"><KindIcon kind={p.kind} /></span>
              <p className="font-semibold flex-1">{p.title}</p>
            </div>
            <p className="text-sm text-text-secondary leading-6 flex-1">{p.about}</p>
            <p className="text-xs text-text-muted tabular">
              {p.items ? <><span className="text-text-primary font-medium">{p.items.toLocaleString("en-IN")}</span> found in {p.documents} document{p.documents === 1 ? "" : "s"}</> : "Nothing found yet"}
            </p>
          </Link>
        ))}
      </div>
      {total === 0 && (
        <p className="text-sm text-text-muted mt-4 leading-6">
          Documents are analysed as they come into the library, and again whenever one is read again. Open a document and use Insights in its side panel to analyse it now.
        </p>
      )}
    </>
  );
}

function Register({ kind, purpose }: { kind: string; purpose?: InsightPurpose }) {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const company = params.get("company") ?? "";
  const [input, setInput] = useState(q);
  const [open, setOpen] = useState<number | null>(null);
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies() });
  const { data, error } = useQuery<InsightRegister>({
    queryKey: ["insights", kind, q, company],
    queryFn: () => aagam.insightRegister(kind, q, company),
    placeholderData: (prev) => (prev?.kind === kind ? prev : undefined),
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  useEffect(() => {
    const t = setTimeout(() => input.trim() !== q && set("q", input.trim()), 250);
    return () => clearTimeout(t);
  }, [input]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setOpen(null), [kind, q, company]);

  const columns = data?.columns ?? purpose?.columns ?? [];
  const filtered = Boolean(q || company);
  const span = columns.length + 2;

  return (
    <>
      {purpose?.about && <p className="text-sm text-text-secondary mb-3 leading-6">{purpose.about}</p>}
      <div className="card p-3 mb-3 flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-2 input py-1 flex-1 min-w-[220px]">
          <Search size={13} className="text-text-muted" />
          <input className="bg-transparent outline-none flex-1" placeholder={`Search ${purpose?.title.toLowerCase() ?? "these"}: a name, section, forum…`} value={input} onChange={(e) => setInput(e.target.value)} aria-label="Search the findings" />
        </label>
        <select className="input py-1" value={company} onChange={(e) => set("company", e.target.value)} aria-label="Filter by client">
          <option value="">All clients</option>
          {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
        </select>
        {filtered && <button className="btn btn-ghost py-1 text-xs" onClick={() => { setInput(""); setParams({}, { replace: true }); }}><X size={12} /> Clear</button>}
        <a className="btn py-1 text-xs" href={aagam.insightCsvUrl(kind, q, company)} download title="The findings shown, as a spreadsheet"><Download size={13} /> Download CSV</a>
      </div>

      <p className="text-xs text-text-muted mb-2 min-h-[16px]">{data ? `${data.count} found${filtered ? " that match" : ""}` : ""}</p>
      {error ? (
        <Empty title="These findings could not be loaded." hint={(error as Error).message} />
      ) : !data ? (
        <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : data.items.length === 0 ? (
        <Empty
          icon={<KindIcon kind={kind} size={20} />}
          title={filtered ? "Nothing matches." : `No ${data.title.toLowerCase()} found yet.`}
          hint={filtered ? "Try other words, or all clients." : "Documents are analysed as they come into the library. When one says something about this, it appears here with its page."}
        />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-text-muted text-left border-b border-bg-border bg-bg-secondary/60">
                {columns.map((c) => (
                  <th key={c.key} className={clsx("font-medium px-3 py-2 whitespace-nowrap", (c.type === "money" || c.type === "number") && "text-right")}>{c.label}</th>
                ))}
                <th className="font-medium px-3 py-2">Document</th>
                <th className="font-medium px-3 py-2">Reading</th>
              </tr>
            </thead>
            <tbody key={`${kind}-${q}-${company}`} className="stagger">
              {data.items.map((item, i) => (
                <Row key={i} item={item} index={i} open={open === i} onToggle={() => setOpen(open === i ? null : i)} data={data} query={q} span={span} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function Row({ item, index, open, onToggle, data, query, span }: {
  item: RegisterItem; index: number; open: boolean; onToggle: () => void; data: InsightRegister; query: string; span: number;
}) {
  const href = `/documents/${item.document_id}${item.page ? `?page=${item.page}` : ""}`;
  return (
    <Fragment>
      <tr
        className={clsx("border-t border-bg-border align-top cursor-pointer transition-colors", open ? "bg-accent-brand/[0.05]" : "hover:bg-bg-hover/70")}
        onClick={onToggle}
        aria-expanded={open}
      >
        {data.columns.map((c, ci) => (
          <td key={c.key} className={clsx("px-3 py-2", (c.type === "money" || c.type === "number") && "text-right")}>
            <span className="inline-flex gap-1.5 items-start">
              {ci === 0 && (
                <button
                  className="text-text-muted mt-0.5 shrink-0"
                  onClick={(e) => { e.stopPropagation(); onToggle(); }}
                  aria-label={open ? `Hide the words of finding ${index + 1}` : `Show the words of finding ${index + 1}`}
                >
                  {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </button>
              )}
              <Cell value={item[c.key]} type={c.type} />
            </span>
          </td>
        ))}
        <td className="px-3 py-2 max-w-[240px]">
          <Link to={href} onClick={(e) => e.stopPropagation()} className="text-accent-brand hover:underline line-clamp-2" title={item.document ?? undefined}>
            {item.document || "Document"}
          </Link>
          <p className="text-xs text-text-muted truncate mt-0.5">
            {item.page ? `p.${item.page}` : ""}{item.company ? `${item.page ? " · " : ""}${item.company}` : ""}{!item.company && item.doc_type ? `${item.page ? " · " : ""}${titleCase(item.doc_type)}` : ""}
          </p>
        </td>
        <td className="px-3 py-2"><Confidence value={item.confidence} /></td>
      </tr>
      {open && (
        <tr className="bg-accent-brand/[0.05]">
          <td colSpan={span} className="px-4 pb-3 pt-0">
            <div className="fade-in border-l-2 border-accent-brand/40 pl-3 py-1">
              <p className="label mb-1">The words it came from</p>
              {item.context ? (
                <p className="legal text-[14.5px] leading-7">{markItem(item.context, item, data.columns, query)}</p>
              ) : (
                <p className="text-sm text-text-muted">No sentence was kept for this one.</p>
              )}
              <Link to={href} className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent-brand hover:underline">
                <FileText size={12} /> Open {item.page ? `page ${item.page}` : "the document"}
              </Link>
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
}
