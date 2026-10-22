import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Calculator, Landmark } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import type { LimitResult } from "../types";

type Field = { key: string; label: string; hint?: string };
const FIGURES: Field[] = [
  { key: "paid_up_capital", label: "Paid-up share capital" },
  { key: "free_reserves", label: "Free reserves", hint: "as in s.2(43)" },
  { key: "securities_premium", label: "Securities premium" },
];
const LOANS: Field[] = [
  { key: "outstanding_loans_investments", label: "Loans, guarantees, security and investments outstanding" },
  { key: "proposed_loans_investments", label: "Proposed now" },
];
const BORROWING: Field[] = [
  { key: "outstanding_borrowing", label: "Already borrowed", hint: "leave out temporary loans from bankers" },
  { key: "proposed_borrowing", label: "Proposed borrowing" },
];

const STATUS: Record<string, { text: string; cls: string }> = {
  special_resolution: { text: "Special resolution needed", cls: "text-accent-amber" },
  board_resolution: { text: "Board resolution is enough", cls: "text-accent-green" },
  check: { text: "Check: depends on an exemption", cls: "text-accent-blue" },
};

export default function CalculatorsPage() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [unit, setUnit] = useState<"crore" | "rupees">("crore");
  const [company, setCompany] = useState("");
  const [wos, setWos] = useState(false);
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies() });

  // Opened from a set of financial statements: start from their figures (in crore).
  const from = Number(useSearchParams()[0].get("from")) || null;
  const { data: prefill } = useQuery({ queryKey: ["s186", from], queryFn: () => aagam.s186Inputs(from!), enabled: from !== null });
  useEffect(() => {
    if (!prefill) return;
    setUnit("crore");
    const filled: Record<string, string> = {};
    Object.entries(prefill).forEach(([k, v]) => {
      if (v !== null && v !== undefined) filled[k] = String(Math.round((v / 10_000_000) * 10_000) / 10_000);
    });
    setValues((old) => ({ ...old, ...filled }));
  }, [prefill]);

  const toRupees = (v: string | undefined) => {
    const n = Number((v ?? "").replace(/,/g, ""));
    return Number.isFinite(n) ? Math.round(unit === "crore" ? n * 10_000_000 : n) : 0;
  };
  const check = useMutation({
    mutationFn: () => {
      const body: Record<string, number | string | boolean | undefined> = { to_wholly_owned_subsidiary: wos, company: company || undefined };
      [...FIGURES, ...LOANS, ...BORROWING].forEach((f) => (body[f.key] = toRupees(values[f.key])));
      return aagam.loanLimits(body);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const input = (f: Field) => (
    <label key={f.key} className="block">
      <span className="text-sm text-text-secondary">{f.label}{f.hint && <span className="text-text-muted"> ({f.hint})</span>}</span>
      <input className="input w-full mt-1" inputMode="decimal" placeholder={unit === "crore" ? "in crore" : "in rupees"}
        value={values[f.key] ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
    </label>
  );

  return (
    <div className="p-6 max-w-6xl space-y-4">
      <h1 className="text-[1.6rem] leading-tight font-semibold">Loans, investments and borrowing</h1>
      {from && prefill && (
        <p className="text-sm flex items-center gap-2 text-accent-brand">
          <Landmark size={14} /> Filled from <Link to={`/financials/${from}`} className="underline">the financial statements</Link>. All of other equity is put in free reserves: using the notes, take out what isn't free (capital or revaluation reserve, OCI) and move securities premium to its own box.
        </p>
      )}
      <p className="text-sm text-text-secondary">Works out the s.186 limit and whether a proposal needs a special resolution. It also gives the s.180(1)(c) limit if borrowing is entered, and the s.185 conditions. Take the figures from the latest audited balance sheet.</p>
      <div className="grid lg:grid-cols-2 gap-5">
        <form className="card p-4 space-y-4" onSubmit={(e) => { e.preventDefault(); check.mutate(); }}>
          <div className="flex gap-3 text-sm items-center flex-wrap">
            <span className="text-text-secondary">Figures in</span>
            {(["crore", "rupees"] as const).map((u) => (
              <label key={u} className="flex items-center gap-1"><input type="radio" checked={unit === u} onChange={() => setUnit(u)} /> {u}</label>
            ))}
            <select className="input py-1 ml-auto" value={company} onChange={(e) => setCompany(e.target.value)} aria-label="Company">
              <option value="">Company (for its class)</option>
              {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
            </select>
          </div>
          <fieldset className="space-y-2"><legend className="label mb-1">Balance sheet</legend>{FIGURES.map(input)}</fieldset>
          <fieldset className="space-y-2"><legend className="label mb-1">Loans, guarantees, security, investments (s.186)</legend>{LOANS.map(input)}
            <label className="flex items-center gap-2 text-sm text-text-secondary"><input type="checkbox" checked={wos} onChange={(e) => setWos(e.target.checked)} /> To a wholly owned subsidiary</label>
          </fieldset>
          <fieldset className="space-y-2"><legend className="label mb-1">Borrowing (s.180(1)(c))</legend>{BORROWING.map(input)}</fieldset>
          <button className="btn btn-primary"><Calculator size={14} /> Work it out</button>
        </form>
        <div className="space-y-4">
          {!check.data && <div className="card p-6 text-text-muted text-sm">The working appears here: each step, the section it rests on, and what it needs.</div>}
          {check.data && (
            <>
              <Result title="Section 186" result={check.data.s186} />
              {check.data.s180 && <Result title="Section 180(1)(c)" result={check.data.s180} />}
              {check.data.s185 && <Result title="Section 185" result={check.data.s185} />}
              <p className="text-xs text-text-muted">{check.data.caution}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Result({ title, result }: { title: string; result: LimitResult }) {
  const status = STATUS[result.status] ?? { text: result.status, cls: "" };
  return (
    <section className="card p-4 space-y-2">
      <div className="flex items-baseline gap-2">
        <p className="font-semibold flex-1">{title}</p>
        <span className={clsx("text-sm font-medium", status.cls)}>{status.text}</span>
      </div>
      {result.needs && <p className="text-sm">{result.needs}</p>}
      {result.steps && (
        <ol className="text-sm text-text-secondary list-decimal pl-5 space-y-0.5 font-mono text-[13px]">
          {result.steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      )}
      <ul className="text-xs text-text-muted list-disc pl-5 space-y-1">
        {result.notes.map((n, i) => <li key={i}>{n}</li>)}
      </ul>
      <p className="text-xs text-text-muted">Basis: {result.basis.join(", ")}</p>
    </section>
  );
}
