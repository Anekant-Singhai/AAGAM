import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, Lock, User } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { crore, day, titleCase } from "../lib/format";
import type { FieldSource, FieldSpec, RecordRow } from "../types";

export const useSchema = () => useQuery({ queryKey: ["record-schema"], queryFn: aagam.schema, staleTime: Infinity });

const DATES = new Set(["date", "dob", "date_of_incorporation", "date_of_appointment", "date_of_cessation", "kyc_next_due", "created_on",
  "modified_on", "satisfied_on", "appointed_on", "ended_on", "due_on", "filed_on", "passed_on"]);
const MONEY = new Set(["authorised_capital", "paid_up_capital", "amount", "fees"]);
const LONG = new Set(["notes", "text", "property", "details"]);
const WIDE = new Set(["name", "notes", "text", "property", "details", "ro_line1", "ro_line2", "address_line1", "address_line2", "subject"]);

const LABELS: Record<string, string> = {
  cin: "CIN / LLPIN", entity_type: "Company or LLP", company_class: "Class", roc: "RoC", nic_code: "NIC code", fy_end: "Year ends (MM-DD)",
  ro_line1: "Address line 1", ro_line2: "Address line 2", ro_city: "City", ro_district: "District", ro_state: "State", ro_pin: "PIN",
  pan: "PAN", tan: "TAN", din: "DIN", dob: "Date of birth", frn: "Firm registration no.", cop_no: "Certificate of practice no.",
  kyc_next_due: "Next DIR-3 KYC", org_cin: "Organisation's CIN", is_listed: "Listed", is_small_company: "Small company (s.2(85))",
  is_section8: "Section 8 company", is_nbfc: "NBFC", msme_return_applicable: "MSME-1 applies", dpt3_applicable: "DPT-3 applies",
  date_of_incorporation: "Incorporated on", authorised_capital: "Authorised capital", paid_up_capital: "Paid-up capital",
  aadhaar: "Aadhaar", passport_no: "Passport no.", membership_no: "Membership no.", address_line1: "Address line 1",
  address_line2: "Address line 2", pin: "PIN", serial_no: "Serial no.", fy: "Financial year (e.g. 2025-26)", srn: "SRN",
  charge_id: "Charge ID", mgt14_required: "MGT-14 to be filed", section_ref: "Section", from_fy: "From year", to_fy: "To year",
  date_of_appointment: "Appointed on", date_of_cessation: "Ceased on", passed_on: "Passed on", allotment_type: "Kind of allotment",
  party_id: "Person", auditor_id: "Auditor", holder_id: "Charge holder", meeting_id: "Approved at meeting",
};
export const fieldLabel = (name: string) => LABELS[name] ?? titleCase(name.replace(/_id$/, ""));

export const FORM_GROUPS: Record<string, [string, string[]][]> = {
  company: [
    ["Identity", ["name", "cin", "entity_type", "company_class", "category", "subcategory", "status", "date_of_incorporation", "roc", "nic_code"]],
    ["For compliance", ["is_listed", "is_small_company", "is_section8", "is_nbfc", "msme_return_applicable", "dpt3_applicable"]],
    ["Capital and year", ["authorised_capital", "paid_up_capital", "fy_end"]],
    ["Registered office", ["ro_line1", "ro_line2", "ro_city", "ro_district", "ro_state", "ro_pin"]],
    ["Contact and tax", ["email", "phone", "website", "pan", "tan"]],
    ["Notes", ["notes"]],
  ],
  party: [
    ["Who", ["kind", "name", "father_name", "dob", "gender", "nationality", "occupation"]],
    ["Numbers", ["din", "pan", "aadhaar", "passport_no"]],
    ["Contact", ["email", "mobile", "address_line1", "address_line2", "city", "district", "state", "pin", "country"]],
    ["Professional", ["org_type", "org_cin", "frn", "membership_no", "professional_body", "cop_no", "kyc_next_due"]],
    ["Notes", ["notes"]],
  ],
};

type Draft = Record<string, string>;

function toDraft(fields: FieldSpec[], value?: RecordRow): Draft {
  const out: Draft = {};
  for (const f of fields) {
    const v = value?.[f.name];
    if (f.sensitive) out[f.name] = "";
    else if (v === null || v === undefined) out[f.name] = "";
    else if (f.type === "boolean") out[f.name] = v ? "true" : "false";
    else out[f.name] = String(v);
  }
  return out;
}

function fromDraft(f: FieldSpec, text: string): unknown {
  if (text === "") return "";
  if (f.type === "boolean") return text === "true";
  if (f.type === "integer") return MONEY.has(f.name) ? text.replace(/[,\s₹]/g, "") : Number(text);
  return text;
}

/**
 * A form for any record in the company file, built from the record's own definition: each field with its
 * kind (a choice, yes/no, a date, rupees), sensitive numbers write-only, and where each value came from.
 */
export type IdOptions = Record<string, { value: number; label: string }[]>;

export default function RecordForm({ entity, value, fixed, hide = [], onSaved, onCancel, submitLabel, columns = 3, only, idOptions, defaults }: {
  entity: string;
  idOptions?: IdOptions;
  defaults?: Record<string, unknown>;
  value?: RecordRow;
  fixed?: Record<string, unknown>;
  hide?: string[];
  onSaved: (row: RecordRow) => void;
  onCancel?: () => void;
  submitLabel?: string;
  columns?: 2 | 3;
  only?: string[];
}) {
  const { data: schema } = useSchema();
  const fields = useMemo(
    () => (schema?.entities[entity] ?? []).filter(
      (f) => (!f.name.endsWith("_id") || (idOptions?.[f.name] && !(fixed && f.name in fixed))) && !hide.includes(f.name) && (!only || only.includes(f.name))
    ),
    [schema, entity, hide, only, idOptions, fixed]
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const start = useMemo(() => toDraft(fields, value ?? (defaults as RecordRow | undefined)), [fields, value, defaults]);
  const current = draft ?? start;
  const initial = useMemo(() => toDraft(fields, value), [fields, value]);
  const changed = fields.filter((f) => current[f.name] !== initial[f.name]);

  const save = useMutation({
    mutationFn: () => {
      const data: Record<string, unknown> = { ...(value ? {} : fixed) };
      for (const f of value ? changed : fields) {
        if (!value && current[f.name] === "") continue;
        data[f.name] = fromDraft(f, current[f.name]);
      }
      return value ? aagam.changeRecord(entity, value.id, data) : aagam.createRecord(entity, data);
    },
    onSuccess: (row) => {
      setDraft(null);
      onSaved(row);
    },
    onError: (e: Error) => toast.error(e.message, { duration: 7000 }),
  });

  if (!schema) return <p className="text-sm text-text-muted">Loading…</p>;
  const groups = (FORM_GROUPS[entity] ?? [["", fields.map((f) => f.name)]])
    .map(([title, names]) => [title, names.map((n) => fields.find((f) => f.name === n)).filter(Boolean) as FieldSpec[]] as const)
    .filter(([, fs]) => fs.length);
  const grouped = new Set(groups.flatMap(([, fs]) => fs.map((f) => f.name)));
  const rest = fields.filter((f) => !grouped.has(f.name));
  const all = rest.length ? [...groups, ["Other", rest] as const] : groups;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value && !changed.length) return onCancel?.();
    save.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      {all.map(([title, fs]) => (
        <fieldset key={title || "fields"}>
          {title && <legend className="label mb-2">{title}</legend>}
          <div className={clsx("grid gap-x-4 gap-y-3", columns === 3 ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2")}>
            {fs.map((f) => (
              <Field
                key={f.name}
                spec={f}
                text={current[f.name] ?? ""}
                masked={f.sensitive ? (value?.[f.name] as string | null) : null}
                source={value?.sources?.[f.name]}
                dirty={current[f.name] !== initial[f.name]}
                options={idOptions?.[f.name]}
                wide={WIDE.has(f.name) && columns === 3}
                onChange={(t) => setDraft({ ...current, [f.name]: t })}
              />
            ))}
          </div>
        </fieldset>
      ))}
      <div className="flex items-center gap-2 pt-1">
        <button className="btn btn-primary" disabled={save.isPending || (!!value && !changed.length)}>
          {submitLabel ?? (value ? `Save ${changed.length ? `${changed.length} change${changed.length === 1 ? "" : "s"}` : ""}` : "Add")}
        </button>
        {onCancel && <button type="button" className="btn" onClick={() => { setDraft(null); onCancel(); }}>Cancel</button>}
        {value && changed.length > 0 && (
          <button type="button" className="btn btn-ghost text-xs" onClick={() => setDraft(null)}>Undo changes</button>
        )}
        <span className="ml-auto text-xs text-text-muted">Each change is recorded as yours, with the date.</span>
      </div>
    </form>
  );
}

function Field({ spec, text, masked, source, dirty, wide, onChange, options }: {
  spec: FieldSpec; text: string; masked: string | null; source?: FieldSource; dirty: boolean; wide: boolean; onChange: (t: string) => void;
  options?: { value: number; label: string }[];
}) {
  const id = `f-${spec.name}`;
  const base = clsx("input w-full mt-1", dirty && "border-accent-amber");
  let input;
  if (options) {
    input = (
      <select id={id} className={base} value={text} onChange={(e) => onChange(e.target.value)}>
        <option value="">{spec.required ? "Choose…" : "None"}</option>
        {options.map((o) => <option key={o.value} value={String(o.value)}>{o.label}</option>)}
      </select>
    );
  } else if (spec.enum) {
    input = (
      <select id={id} className={base} value={text} onChange={(e) => onChange(e.target.value)}>
        <option value="">{spec.required ? "Choose…" : "Not set"}</option>
        {spec.enum.map((o) => <option key={o} value={o}>{titleCase(o)}</option>)}
      </select>
    );
  } else if (spec.type === "boolean") {
    input = (
      <select id={id} className={base} value={text} onChange={(e) => onChange(e.target.value)}>
        <option value="">Not known</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  } else if (LONG.has(spec.name)) {
    input = <textarea id={id} className={clsx(base, "h-20 resize-y")} value={text} onChange={(e) => onChange(e.target.value)} />;
  } else if (DATES.has(spec.name)) {
    input = <input id={id} type="date" className={base} value={text} onChange={(e) => onChange(e.target.value)} />;
  } else if (MONEY.has(spec.name)) {
    const n = Number(text.replace(/[,\s₹]/g, ""));
    input = (
      <>
        <input id={id} inputMode="numeric" className={clsx(base, "tabular")} value={text} placeholder="whole rupees" onChange={(e) => onChange(e.target.value)} />
        {text && Number.isFinite(n) && <span className="text-[11px] text-text-muted">{crore(n)}</span>}
      </>
    );
  } else if (spec.sensitive) {
    input = (
      <div className="relative">
        <input id={id} className={clsx(base, "pl-7 font-mono")} value={text} autoComplete="off" placeholder={masked ? `${masked} · type to change` : "type to add"} onChange={(e) => onChange(e.target.value)} />
        <Lock size={12} className="absolute left-2.5 top-1/2 mt-0.5 -translate-y-1/2 text-text-muted" />
      </div>
    );
  } else {
    input = <input id={id} className={clsx(base, ["cin", "din", "pan", "tan", "org_cin", "srn", "charge_id", "frn"].includes(spec.name) && "font-mono")} value={text} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <div className={clsx(wide && "lg:col-span-2", LONG.has(spec.name) && "sm:col-span-full")}>
      <label htmlFor={id} className="text-xs text-text-secondary flex items-center gap-1.5" title={spec.description ?? undefined}>
        {fieldLabel(spec.name)}
        {spec.required && <span className="text-accent-red">*</span>}
        {source && <SourceDot source={source} />}
      </label>
      {input}
    </div>
  );
}

/** Where a value came from: a document and its words, her, or Claude. */
export function SourceDot({ source }: { source: FieldSource }) {
  const fromDoc = source.source_kind === "document";
  const who = source.recorded_by === "her" ? "you" : source.recorded_by;
  const text = fromDoc
    ? `From ${source.document_id ? `document ${source.document_id}` : "a document since deleted"}, page ${source.page}${source.quote ? `: “${source.quote}”` : ""}`
    : `${titleCase(source.source_kind)}: recorded by ${who}, ${day(source.recorded_at.slice(0, 10))}${source.note ? ` (${source.note})` : ""}`;
  return (
    <span className={clsx("inline-flex", fromDoc ? "text-accent-blue" : "text-text-muted")} title={text} aria-label={text}>
      {fromDoc ? <FileText size={11} /> : <User size={11} />}
    </span>
  );
}
