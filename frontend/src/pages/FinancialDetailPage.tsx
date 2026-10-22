import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownRight, ArrowLeft, ArrowUpRight, Briefcase, Calculator, Eraser, FileText, Flag, Landmark, Pencil, Scale, Sparkles, Trash2 } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { day, inUnit, titleCase } from "../lib/format";
import { CountUp, PageSkeleton, Section, Status, Tabs } from "../components/ui";
import LiabilityBar from "../components/LiabilityBar";
import NotesPanel from "../components/NotesPanel";
import { Modal, MoreMenu, useConfirm } from "../components/dialogs";
import type { Analysis, Applies, FinancialItem, Ratio } from "../types";

// Which work to start when a test says something applies.
const WORK_FOR: Record<string, string> = { secretarial_audit: "secretarial_audit", xbrl: "annual_filing", small_company: "annual_filing" };
type Tab = "overview" | "ratios" | "applies" | "figures" | "notes";

export default function FinancialDetailPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "overview";
  const { data, error } = useQuery({ queryKey: ["analysis", id], queryFn: () => aagam.analysis(id) });
  const refresh = (a: Analysis) => queryClient.setQueryData(["analysis", id], a);
  const confirm = useConfirm();
  const [editingHeader, setEditingHeader] = useState(false);
  const remove = async () => {
    const ok = await confirm({
      title: "Delete these statements?",
      body: "The figures, your corrections and the analysis go. The document stays in the library, and these statements won't be read from it again.",
      items: ["Your notes on them are kept, as general notes"],
      action: "Delete statements",
      danger: true,
    });
    if (!ok) return;
    await aagam.deleteStatement(id);
    queryClient.invalidateQueries({ queryKey: ["financials"] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
    toast.success("Statements deleted.");
    navigate("/financials");
  };

  if (error) return <p className="p-6 text-accent-red">{(error as Error).message}</p>;
  if (!data) return <PageSkeleton />;

  const st = data.statement;
  const factor = st.unit_factor || 1;
  const unit = st.unit ?? "₹";
  const name = st.client || st.company_name || st.original_name || "Financial statements";
  const now = data.derived.current;
  const before = data.derived.previous;
  const flagged = data.ratios.filter((r) => r.explain).length;
  const applies = data.applicability.filter((a) => a.status === "yes").length;

  return (
    <div className="px-8 py-6 max-w-7xl">
      <div className="flex items-start gap-3 flex-wrap mb-4">
        <button onClick={() => navigate("/financials")} className="btn btn-ghost px-1.5 mt-1" aria-label="Back"><ArrowLeft size={16} /></button>
        <div className="w-10 h-10 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0 pop-in"><Landmark size={19} /></div>
        <div className="flex-1 min-w-0">
          <h1 className="text-[1.6rem] leading-tight font-semibold">{name}</h1>
          <p className="text-sm text-text-secondary mt-0.5">
            {titleCase(st.basis)} financial statements
            {st.period_end && <> · year to {day(st.period_end)}</>}
            {st.prior_period_end && <span className="text-text-muted"> (compared with {day(st.prior_period_end)})</span>}
            {" · "}<span className="font-medium">{unit}</span>
          </p>
        </div>
        {st.document_id && <Link className="btn" to={`/documents/${st.document_id}`}><FileText size={13} /> The document</Link>}
        <Link className="btn" to={`/calculators?from=${st.id}`} title="Fill the s.186 / s.180 calculator from these figures"><Calculator size={13} /> Loan limits</Link>
        <MoreMenu items={[
          { label: "Correct whose, which years, which unit", icon: <Pencil size={14} />, onClick: () => setEditingHeader(true) },
          { label: "Delete these statements", icon: <Trash2 size={14} />, danger: true, onClick: remove },
        ]} />
      </div>
      {editingHeader && <HeaderEditor data={data} onClose={() => setEditingHeader(false)} onSaved={(a) => { refresh(a); setEditingHeader(false); }} />}

      <Tabs<Tab>
        value={tab}
        onChange={(t) => setParams(t === "overview" ? {} : { tab: t }, { replace: true })}
        className="mb-5"
        tabs={[
          { key: "overview", label: "Overview" },
          { key: "ratios", label: "Ratios", count: flagged },
          { key: "applies", label: "What applies", count: applies },
          { key: "figures", label: "Figures" },
          { key: "notes", label: "Notes and facts" },
        ]}
      />

      <div key={tab} className="fade-in">
        {tab === "overview" && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 stagger">
              <Tile label="Revenue from operations" now={now.revenue} before={before.revenue} factor={factor} />
              <Tile label="EBITDA" now={now.ebitda} before={before.ebitda} factor={factor} />
              <Tile label="Profit for the year" now={now.pat} before={before.pat} factor={factor} />
              <Tile label="Net worth" now={now.equity} before={before.equity} factor={factor} />
              <Tile label="Borrowings and leases" now={now.debt} before={before.debt} factor={factor} upIsBad />
            </div>
            <div className="grid lg:grid-cols-[1.2fr_1fr] gap-5 items-start">
              <Section title="Where the money comes from">
                {data.liabilities.parts ? (
                  <>
                    <LiabilityBar parts={data.liabilities.parts} total={data.liabilities.total ?? 0} factor={factor} unit={st.unit} />
                    {data.liabilities.msme_share_of_payables != null && (
                      <p className="text-xs text-text-muted mt-3">{data.liabilities.msme_share_of_payables}% of trade payables are owed to micro and small enterprises.</p>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-text-muted">Total assets weren't found, so the split can't be worked out. Add the line under Figures.</p>
                )}
              </Section>
              <div className="space-y-5">
                <Section title={`Things to look at (${data.checks.length})`}>
                  {data.checks.length === 0 && <p className="text-sm text-text-muted">The statements add up and nothing stands out.</p>}
                  <ul className="space-y-2.5">
                    {data.checks.map((c, i) => (
                      <li key={i} className="flex gap-2.5 text-sm leading-6">
                        <Status status={c.level} showLabel={false} />
                        <span>{c.text}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
                <Section title="At a glance">
                  <ul className="text-sm space-y-2">
                    <li className="flex items-center gap-2">
                      <Flag size={13} className={flagged ? "text-accent-amber" : "text-text-muted"} />
                      <span className="flex-1">{flagged ? `${flagged} ratio${flagged === 1 ? "" : "s"} moved more than 25%: the notes must explain why.` : "No ratio moved more than 25%."}</span>
                      <button className="text-xs text-accent-brand hover:underline" onClick={() => setParams({ tab: "ratios" })}>Ratios</button>
                    </li>
                    <li className="flex items-center gap-2">
                      <Sparkles size={13} className="text-accent-brand" />
                      <span className="flex-1">{applies ? `${applies} requirement${applies === 1 ? "" : "s"} apply from these figures.` : "None of the threshold tests is met."}</span>
                      <button className="text-xs text-accent-brand hover:underline" onClick={() => setParams({ tab: "applies" })}>What applies</button>
                    </li>
                  </ul>
                </Section>
              </div>
            </div>
          </div>
        )}
        {tab === "ratios" && <Ratios ratios={data.ratios} />}
        {tab === "applies" && <Applicability data={data} name={name} />}
        {tab === "figures" && <Figures data={data} onChange={refresh} />}
        {tab === "notes" && (
          <div className="grid lg:grid-cols-2 gap-5 items-start">
            <Facts data={data} onChange={refresh} />
            <NotesPanel kind="financials" target={String(st.id)} />
          </div>
        )}
      </div>
    </div>
  );
}

function change(now: number | null | undefined, before: number | null | undefined): number | null {
  if (now == null || before == null || before === 0) return null;
  return ((now - before) / Math.abs(before)) * 100;
}

function Tile({ label, now, before, factor, upIsBad }: { label: string; now: number | null | undefined; before: number | null | undefined; factor: number; upIsBad?: boolean }) {
  const pct = change(now, before);
  const good = pct === null ? null : upIsBad ? pct <= 0 : pct >= 0;
  return (
    <div className="card p-4">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className={clsx("text-2xl font-semibold tabular mt-1 tracking-tight", now != null && now < 0 && "text-accent-red")}>{now == null ? "—" : <CountUp value={now} format={(n) => inUnit(n, factor)} />}</p>
      <p className="text-xs text-text-muted mt-1 tabular flex items-center gap-1.5">
        {pct !== null && (
          <span className={clsx("inline-flex items-center font-medium", good ? "text-accent-green" : "text-accent-red")}>
            {pct >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {Math.abs(pct).toFixed(1)}%
          </span>
        )}
        {before != null && <span>last year {inUnit(before, factor)}</span>}
      </p>
    </div>
  );
}

function fmt(value: number | null, unit: string): string {
  if (value === null) return "—";
  return unit === "%" ? `${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}%` : `${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}×`;
}

function Ratios({ ratios }: { ratios: Ratio[] }) {
  const flagged = ratios.filter((r) => r.explain).length;
  return (
    <Section
      title="Ratios (Schedule III)"
      actions={flagged > 0 ? <span className="text-xs text-accent-amber inline-flex items-center gap-1 font-medium"><Flag size={12} /> {flagged} moved more than 25%</span> : undefined}
    >
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-text-muted text-left">
            <th className="font-medium pb-2">Ratio</th>
            <th className="font-medium pb-2 pl-3 text-right">This year</th>
            <th className="font-medium pb-2 pl-3 text-right">Last year</th>
            <th className="font-medium pb-2 pl-3 text-right">Change</th>
          </tr>
        </thead>
        <tbody className="stagger">
          {ratios.map((r) => (
            <tr key={r.key} className="border-t border-bg-border align-top">
              <td className="py-2 pr-3">
                <p className="font-medium">{r.name}</p>
                <p className="text-xs text-text-muted leading-5">{r.current === null && r.missing ? r.missing : r.formula}</p>
              </td>
              <td className="py-2 pl-3 text-right tabular font-medium whitespace-nowrap">{fmt(r.current, r.unit)}</td>
              <td className="py-2 pl-3 text-right tabular text-text-secondary whitespace-nowrap">{fmt(r.previous, r.unit)}</td>
              <td className="py-2 pl-3 text-right tabular whitespace-nowrap">
                {r.change_pct === null ? <span className="text-text-muted">—</span> : (
                  <span className={clsx(r.explain ? "text-accent-amber font-medium" : "text-text-secondary")}>
                    {r.change_pct > 0 ? "+" : ""}{r.change_pct}%
                    {r.explain && <span className="flex items-center justify-end gap-1 text-[11px] mt-0.5"><Flag size={11} /> explain in notes</span>}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-text-muted mt-3">Schedule III (Division I and II) asks for these ratios with reasons for any change of more than 25% from last year. Last year's ratios use last year's closing figures.</p>
    </Section>
  );
}

function Applicability({ data, name }: { data: Analysis; name: string }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const start = useMutation({
    mutationFn: (a: Applies) =>
      aagam.createWork({ title: `${a.title} · ${name}`, kind: WORK_FOR[a.key] ?? "other", company: data.statement.company_id ? String(data.statement.company_id) : undefined }),
    onSuccess: (w) => {
      queryClient.invalidateQueries({ queryKey: ["works"] });
      navigate(`/work/${w.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const order: Record<string, number> = { yes: 0, check: 1, no: 2 };
  const tests = [...data.applicability].sort((a, b) => (order[a.status] ?? 1) - (order[b.status] ?? 1));
  return (
    <section className="card p-4">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={14} className="text-accent-brand" />
        <p className="label flex-1">What these figures make apply</p>
      </div>
      <p className="text-xs text-text-muted mb-3">
        Tested against the thresholds in the Act and rules.
        {data.class_from_cin && <> The company isn't in the company file, so its class was taken from the CIN in the document ({data.class_from_cin}).</>}
        {" "}Thresholds usually look at the previous year's audited figures, or any time in the year; check the date each one runs from.
      </p>
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3 stagger">
        {tests.map((a, i) => (
          <div key={`${a.key}-${i}`} className={clsx("rounded-lg border p-3 flex flex-col", a.status === "yes" ? "border-accent-green/40 bg-accent-green/[0.04]" : a.status === "check" ? "border-accent-amber/40" : "border-bg-border")}>
            <div className="flex items-start gap-2">
              <p className={clsx("font-medium text-sm flex-1", a.status === "no" && "text-text-secondary")}>{a.title}</p>
              <Status status={a.status} />
            </div>
            <p className="text-sm text-text-secondary mt-1.5 leading-6">{a.why}</p>
            {a.missing && <p className="text-sm text-accent-amber mt-1.5">To settle it: {a.missing}</p>}
            {a.work && <p className="text-xs text-text-secondary mt-1.5 leading-5"><span className="font-medium">The work: </span>{a.work}</p>}
            <div className="mt-auto pt-2 flex items-end gap-2">
              <p className="text-[11.5px] font-mono text-text-muted flex items-start gap-1 flex-1"><Scale size={11} className="mt-0.5 shrink-0" />{a.basis}</p>
              {a.status !== "no" && a.work && (
                <button className="btn btn-ghost text-xs py-0.5 px-1.5 shrink-0" onClick={() => start.mutate(a)} title="Open a piece of work for this">
                  <Briefcase size={12} /> Start work
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Figures({ data, onChange }: { data: Analysis; onChange: (a: Analysis) => void }) {
  const [all, setAll] = useState(false);
  const [tab, setTab] = useState<"bs" | "pl">("bs");
  const factor = data.statement.unit_factor || 1;
  const rows = data.items.filter((i) => i.statement === tab && (all || i.found));
  const missing = data.items.filter((i) => i.statement === tab && !i.found).length;
  let group = "";

  return (
    <section className="card">
      <div className="flex items-center gap-3 px-4 pt-3 pb-2 flex-wrap">
        <p className="label">The figures</p>
        <div className="flex rounded-lg border border-bg-border bg-bg-secondary p-0.5 text-sm" role="tablist">
          {([["bs", "Balance sheet"], ["pl", "Profit and loss"]] as const).map(([key, label]) => (
            <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
              className={clsx("px-2.5 py-0.5 rounded-md", tab === key ? "bg-bg-surface shadow-sm font-medium" : "text-text-secondary")}>{label}</button>
          ))}
        </div>
        <label className="ml-auto text-xs text-text-secondary flex items-center gap-1.5">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show the {missing} line{missing === 1 ? "" : "s"} not found
        </label>
      </div>
      <p className="px-4 pb-2 text-xs text-text-muted">{data.statement.unit ?? "In rupees"}. Click a figure to correct it; your figures are kept when the document is read again.</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-text-muted border-y border-bg-border bg-bg-secondary/60">
            <th className="text-left font-medium px-4 py-1.5">Line</th>
            <th className="text-right font-medium px-3 py-1.5 w-36">{data.statement.period_end ? day(data.statement.period_end) : "This year"}</th>
            <th className="text-right font-medium px-3 py-1.5 w-36">{data.statement.prior_period_end ? day(data.statement.prior_period_end) : "Last year"}</th>
            <th className="w-16 px-3 py-1.5 font-medium text-right">Page</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => {
            const header = item.group !== group ? item.group : null;
            group = item.group;
            return [
              header && (
                <tr key={`h-${header}`}><td colSpan={4} className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">{header}</td></tr>
              ),
              <FigureRow key={item.key} item={item} factor={factor} documentId={data.statement.document_id} financialId={data.statement.id} onChange={onChange} />,
            ];
          })}
        </tbody>
      </table>
    </section>
  );
}

function FigureRow({ item, factor, documentId, financialId, onChange }: {
  item: FinancialItem; factor: number; documentId: number | null; financialId: number; onChange: (a: Analysis) => void;
}) {
  const [editing, setEditing] = useState(false);
  const toText = (v: number | null) => (v === null ? "" : String(Math.round((v / factor) * 100) / 100));
  const [cur, setCur] = useState(toText(item.current));
  const [prev, setPrev] = useState(toText(item.previous));
  const toRupees = (s: string) => {
    const t = s.replace(/,/g, "").trim();
    if (!t) return null;
    const neg = /^\(.*\)$/.test(t);
    const n = Number(t.replace(/[()]/g, ""));
    return Number.isFinite(n) ? Math.round((neg ? -n : n) * factor) : null;
  };
  const save = useMutation({
    mutationFn: () => aagam.correctLine(financialId, item.key, toRupees(cur), toRupees(prev)),
    onSuccess: (a) => { onChange(a); setEditing(false); toast.success(`${item.label} saved.`); },
    onError: (e: Error) => toast.error(e.message),
  });
  const clear = useMutation({
    mutationFn: () => aagam.correctLine(financialId, item.key, null, null),
    onSuccess: (a) => { onChange(a); setEditing(false); toast.success(`${item.label} cleared.`); },
    onError: (e: Error) => toast.error(e.message),
  });
  const total = item.key.startsWith("total_") || item.key === "profit_before_tax" || item.key === "profit_after_tax";

  if (editing) {
    return (
      <tr className="bg-accent-brand/[0.05]">
        <td className="px-4 py-1.5">{item.label}</td>
        <td className="px-3 py-1"><input className="input w-full text-right tabular py-0.5" autoFocus value={cur} onChange={(e) => setCur(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save.mutate()} aria-label="This year" /></td>
        <td className="px-3 py-1"><input className="input w-full text-right tabular py-0.5" value={prev} onChange={(e) => setPrev(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save.mutate()} aria-label="Last year" /></td>
        <td className="px-3 py-1 text-right whitespace-nowrap">
          <button className="text-xs text-accent-brand font-medium" onClick={() => save.mutate()}>Save</button>{" "}
          <button className="text-xs text-text-muted hover:text-accent-red ml-1" title="Clear this line: it isn't in these statements" aria-label="Clear the line" onClick={() => { setCur(""); setPrev(""); clear.mutate(); }}><Eraser size={12} className="inline" /></button>{" "}
          <button className="text-xs text-text-muted ml-1" onClick={() => setEditing(false)}>×</button>
        </td>
      </tr>
    );
  }
  return (
    <tr className={clsx("group border-b border-bg-border/60 hover:bg-bg-hover/60", total && "font-semibold", !item.found && "text-text-muted")} onClick={() => setEditing(true)}>
      <td className="px-4 py-1.5 cursor-pointer">
        <span className="inline-flex items-center gap-1.5">
          {item.label}
          {item.by === "her" && <span className="chip tag-1 font-normal" title="You entered this figure">yours</span>}
          {item.repaired && <span className="chip tag-2 font-normal" title={`Read as ${Object.values(item.repaired).join(", ")}; worked out from the totals instead`}>worked out</span>}
          <Pencil size={11} className="opacity-0 group-hover:opacity-60" />
        </span>
      </td>
      <td className="px-3 py-1.5 text-right tabular cursor-pointer" title={item.as_written}>{inUnit(item.current, factor)}</td>
      <td className="px-3 py-1.5 text-right tabular cursor-pointer text-text-secondary">{inUnit(item.previous, factor)}</td>
      <td className="px-3 py-1.5 text-right text-xs">
        {item.page && documentId ? (
          <Link to={`/documents/${documentId}?page=${item.page}`} onClick={(e) => e.stopPropagation()} className="text-accent-brand hover:underline">p.{item.page}</Link>
        ) : null}
      </td>
    </tr>
  );
}

function Facts({ data, onChange }: { data: Analysis; onChange: (a: Analysis) => void }) {
  const f = data.facts as Record<string, string | number | boolean | undefined>;
  const factor = data.statement.unit_factor || 1;
  const save = useMutation({
    mutationFn: (facts: Record<string, unknown>) => aagam.statementFacts(data.statement.id, facts),
    onSuccess: (a) => { onChange(a); toast.success("Saved; the tests are worked out again."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const money = (key: string, label: string, hint: string) => (
    <label className="block">
      <span className="text-xs text-text-secondary">{label} <span className="text-text-muted">({hint})</span></span>
      <input
        className="input w-full mt-0.5 text-right tabular"
        inputMode="decimal"
        defaultValue={typeof f[key] === "number" ? String(Math.round(((f[key] as number) / factor) * 100) / 100) : ""}
        placeholder={data.statement.unit ?? "rupees"}
        onBlur={(e) => {
          const t = e.target.value.replace(/,/g, "").trim();
          const value = t ? Math.round(Number(t) * factor) : null;
          if (value !== (f[key] ?? null) && (value === null || Number.isFinite(value))) save.mutate({ [key]: value });
        }}
      />
    </label>
  );
  const yesNo = (key: string, label: string) => (
    <label className="flex items-center justify-between gap-2 text-sm">
      <span className="text-text-secondary">{label}</span>
      <select className="input py-0.5" value={f[key] === undefined ? "" : f[key] ? "yes" : "no"} onChange={(e) => save.mutate({ [key]: e.target.value === "" ? null : e.target.value === "yes" })}>
        <option value="">Not known</option>
        <option value="yes">Yes</option>
        <option value="no">No</option>
      </select>
    </label>
  );
  return (
    <Section title="What the statements don't say">
      <p className="text-xs text-text-muted mb-3">Some tests need facts that aren't in the figures. Tell AAGAM and they are worked out again.</p>
      <div className="space-y-2.5">
        <label className="flex items-center justify-between gap-2 text-sm">
          <span className="text-text-secondary">Class of company</span>
          <select className="input py-0.5" value={(f.company_class as string) ?? ""} onChange={(e) => save.mutate({ company_class: e.target.value || null })}>
            <option value="">{data.class_from_cin ? "From the CIN" : "Not known"}</option>
            <option value="private">Private</option>
            <option value="public">Public</option>
            <option value="opc">One person company</option>
          </select>
        </label>
        {yesNo("listed", "Listed")}
        {yesNo("holding_or_subsidiary", "A holding or subsidiary company")}
        {money("bank_borrowings", "Borrowings from banks and public financial institutions", "for the secretarial audit test")}
        {money("deposits", "Deposits accepted", "for DPT-3")}
        {money("principal_repaid", "Principal of loans repaid in the year", "for the debt service coverage ratio")}
      </div>
    </Section>
  );
}

const UNIT_OF: Record<number, string> = { 1: "rupees", 1000: "thousands", 100000: "lakhs", 1000000: "millions", 10000000: "crore" };

/** She corrects what the statements are: whose, standalone or consolidated, the years, the unit. */
function HeaderEditor({ data, onClose, onSaved }: { data: Analysis; onClose: () => void; onSaved: (a: Analysis) => void }) {
  const st = data.statement;
  const [form, setForm] = useState({
    company_name: st.company_name ?? "",
    basis: st.basis,
    period_end: st.period_end ?? "",
    prior_period_end: st.prior_period_end ?? "",
    unit: UNIT_OF[st.unit_factor] ?? "rupees",
  });
  const save = useMutation({
    mutationFn: () => {
      const changes: Record<string, unknown> = {};
      if (form.company_name !== (st.company_name ?? "")) changes.company_name = form.company_name;
      if (form.basis !== st.basis) changes.basis = form.basis;
      if (form.period_end !== (st.period_end ?? "")) changes.period_end = form.period_end || null;
      if (form.prior_period_end !== (st.prior_period_end ?? "")) changes.prior_period_end = form.prior_period_end || null;
      if (form.unit !== (UNIT_OF[st.unit_factor] ?? "rupees")) changes.unit = form.unit;
      return aagam.editStatement(st.id, changes);
    },
    onSuccess: (a) => { toast.success("Saved. Kept even when the document is read again."); onSaved(a); },
    onError: (e: Error) => toast.error(e.message),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const unitChanged = form.unit !== (UNIT_OF[st.unit_factor] ?? "rupees");
  return (
    <Modal title="Correct these statements" onClose={onClose} width="max-w-xl"
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>Save</button></>}>
      <div className="grid sm:grid-cols-2 gap-3 text-sm">
        <label className="block sm:col-span-2"><span className="text-xs text-text-muted">Company</span><input className="input w-full mt-0.5" value={form.company_name} onChange={set("company_name")} /></label>
        <label className="block"><span className="text-xs text-text-muted">Basis</span>
          <select className="input w-full mt-0.5" value={form.basis} onChange={set("basis")}><option value="standalone">Standalone</option><option value="consolidated">Consolidated</option></select>
        </label>
        <label className="block"><span className="text-xs text-text-muted">Figures are in</span>
          <select className="input w-full mt-0.5" value={form.unit} onChange={set("unit")}>
            <option value="rupees">Rupees</option><option value="thousands">Thousands</option><option value="lakhs">Lakhs</option><option value="millions">Millions</option><option value="crore">Crore</option>
          </select>
        </label>
        <label className="block"><span className="text-xs text-text-muted">Year ended</span><input type="date" className="input w-full mt-0.5" value={form.period_end} onChange={set("period_end")} /></label>
        <label className="block"><span className="text-xs text-text-muted">Compared with the year ended</span><input type="date" className="input w-full mt-0.5" value={form.prior_period_end} onChange={set("prior_period_end")} /></label>
      </div>
      {unitChanged && <p className="text-xs text-accent-amber mt-3">Every figure is scaled to the new unit: a line read as 100 in lakhs becomes 100 in crore (₹100 crore), and the ratios and tests are worked out again.</p>}
    </Modal>
  );
}
