import { ReactNode, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { crore, day, titleCase } from "../lib/format";
import { consequences, Modal, useConfirm } from "./dialogs";
import RecordForm, { fieldLabel, type IdOptions } from "./RecordForm";
import type { RecordRow } from "../types";

export interface Column {
  key: string;
  label?: string;
  render?: (row: RecordRow) => ReactNode;
}

const MONEY = new Set(["amount", "fees", "authorised_capital", "paid_up_capital"]);
const DATEISH = /(^date$|_on$|^dob$|^date_of|kyc_next_due)/;
// Fields whose values are choices (stored as words like "whole_time_director"): shown as words.
const ENUMS = new Set(["role", "kind", "status", "mode", "audit_type", "category", "allotment_type", "cessation_reason", "appointment_kind",
  "entity_type", "company_class", "org_type", "gender", "professional_body"]);

export function show(key: string, value: unknown): ReactNode {
  if (value === null || value === undefined || value === "") return <span className="text-text-muted">—</span>;
  if (typeof value === "boolean" || (typeof value === "number" && /^(is_|mgt14)/.test(key))) return value ? "Yes" : "No";
  if (MONEY.has(key) && typeof value === "number") return crore(value);
  if (DATEISH.test(key) && typeof value === "string") return day(value);
  if (typeof value === "string" && ["agm", "egm"].includes(value)) return value.toUpperCase();
  if (typeof value === "string" && ENUMS.has(key) && /^[a-z][a-z_]*$/.test(value)) return titleCase(value);
  return String(value);
}

/** A list of one kind of record in a client's file, with add, change and delete. */
export default function RecordTable({ title, entity, rows, columns, companyId, idOptions, onChanged, empty, addLabel }: {
  title: string;
  entity: string;
  rows: RecordRow[];
  columns: Column[];
  companyId: number;
  idOptions?: IdOptions;
  onChanged: () => void;
  empty?: string;
  addLabel?: string;
}) {
  const confirm = useConfirm();
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const { data: record } = useQuery({
    queryKey: ["record", entity, editing],
    queryFn: () => aagam.record(entity, editing as number),
    enabled: typeof editing === "number",
  });

  const remove = async (row: RecordRow) => {
    const deps = await aagam.dependents(entity, row.id);
    const ok = await confirm({
      title: `Delete this ${fieldLabel(entity).toLowerCase()}?`,
      body: "It is removed from the company file, with its history. Due dates are worked out again.",
      items: consequences(deps),
      action: "Delete",
      danger: true,
    });
    if (!ok) return;
    try {
      await aagam.deleteRecord(entity, row.id);
      toast.success("Deleted.");
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <section className="card">
      <div className="flex items-center px-4 pt-3 pb-2">
        <p className="label flex-1">{title} {rows.length > 0 && <span className="normal-case tracking-normal font-normal">({rows.length})</span>}</p>
        <button className="btn btn-ghost py-1 text-xs" onClick={() => setEditing("new")}><Plus size={13} /> {addLabel ?? "Add"}</button>
      </div>
      {rows.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-text-muted">{empty ?? "None on file."}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-text-muted text-left border-y border-bg-border bg-bg-secondary/60">
                {columns.map((c) => <th key={c.key} className="font-medium px-4 py-1.5">{c.label ?? fieldLabel(c.key)}</th>)}
                <th className="w-20" />
              </tr>
            </thead>
            <tbody className="stagger">
              {rows.map((row) => (
                <tr key={row.id} className="group border-b border-bg-border/60 last:border-b-0 hover:bg-bg-hover/50">
                  {columns.map((c) => <td key={c.key} className="px-4 py-2 align-top">{c.render ? c.render(row) : show(c.key, row[c.key])}</td>)}
                  <td className="px-2 py-1.5 text-right whitespace-nowrap">
                    <span className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                      <button className="btn btn-ghost px-1.5 py-1" onClick={() => setEditing(row.id)} aria-label="Change" title="Change"><Pencil size={13} /></button>
                      <button className="btn btn-ghost px-1.5 py-1 hover:text-accent-red" onClick={() => remove(row)} aria-label="Delete" title="Delete"><Trash2 size={13} /></button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing !== null && (editing === "new" || record) && (
        <Modal title={editing === "new" ? `${addLabel ?? "Add"}` : `Change ${fieldLabel(entity).toLowerCase()}`} onClose={() => setEditing(null)} width="max-w-3xl">
          <RecordForm
            entity={entity}
            value={editing === "new" ? undefined : record}
            fixed={{ company_id: companyId }}
            idOptions={idOptions}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              toast.success("Saved.");
              onChanged();
            }}
          />
        </Modal>
      )}
    </section>
  );
}
