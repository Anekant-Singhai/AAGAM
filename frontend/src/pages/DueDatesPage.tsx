import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { day } from "../lib/format";
import { Modal } from "../components/dialogs";
import type { DueItem } from "../types";

export default function DueDatesPage() {
  const [days, setDays] = useState(60);
  const [filing, setFiling] = useState<DueItem | null>(null);
  const { data } = useQuery({ queryKey: ["due", days], queryFn: () => aagam.due(days) });

  return (
    <div className="p-6 space-y-4 max-w-6xl">
      <div className="flex items-center gap-3">
        <h1 className="text-[1.6rem] leading-tight font-semibold mr-auto">Due dates</h1>
        <label className="text-sm text-text-secondary flex items-center gap-2">
          Next
          <select className="input py-1" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[30, 60, 90, 180, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </label>
      </div>
      <p className="text-sm text-text-secondary">
        Worked out from the company file (meetings, appointments, allotments, charges…). Each date gives its legal basis; items marked “check” rest on a reading to confirm.
        Once a form is filed, press <b>Mark as filed</b> and it leaves the list.
      </p>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-bg-secondary text-left">
            <tr className="text-xs text-text-muted">
              <th className="px-3 py-2">Due</th><th className="px-3 py-2">Form</th><th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">What</th><th className="px-3 py-2">Basis</th><th className="px-3 py-2"><span className="sr-only">Filed</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-bg-border stagger">
            {data?.items.map((d) => (
              <tr key={`${d.company_id}-${d.trigger}-${d.form}`} className={clsx(d.state === "overdue" && "bg-accent-red/5")}>
                <td className={clsx("px-3 py-2 whitespace-nowrap", d.state === "overdue" ? "text-accent-red font-medium" : "")}>
                  {day(d.due)}<div className="text-xs text-text-muted">{d.state === "overdue" ? "overdue" : `in ${d.days_left} days`}</div>
                </td>
                <td className="px-3 py-2 font-medium whitespace-nowrap">{d.form}</td>
                <td className="px-3 py-2">{d.company}</td>
                <td className="px-3 py-2">{d.title}<div className="text-xs text-text-muted">{d.basis}</div></td>
                <td className="px-3 py-2 whitespace-nowrap">{d.law}{d.certainty === "check" && <span className="ml-1 chip tag-2">check</span>}</td>
                <td className="px-3 py-2 text-right">
                  <button className="btn btn-ghost py-1 text-xs whitespace-nowrap" onClick={() => setFiling(d)} aria-label={`Mark ${d.form} for ${d.company} as filed`}>
                    <CheckCircle2 size={13} /> Mark as filed
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <p className="p-6 text-center text-text-muted">Nothing due in this window for the companies on file.</p>}
      </div>
      {filing && <MarkFiled item={filing} onClose={() => setFiling(null)} />}
    </div>
  );
}

/** Records the filing in the company file (form, SRN, date), which closes this due date. */
function MarkFiled({ item, onClose }: { item: DueItem; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [srn, setSrn] = useState("");
  const [filedOn, setFiledOn] = useState(new Date().toISOString().slice(0, 10));
  const [fees, setFees] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try {
      await aagam.createRecord("filing", {
        company_id: item.company_id, form: item.form, trigger: item.trigger, due_on: item.due, status: "submitted",
        srn: srn.trim() || undefined, filed_on: filedOn || undefined, fees: fees.trim() ? Number(fees.replace(/[,₹\s]/g, "")) : undefined,
      });
      toast.success(`${item.form} for ${item.company} is recorded as filed.`);
      queryClient.invalidateQueries({ queryKey: ["due"] });
      queryClient.invalidateQueries({ queryKey: ["overview"] });
      queryClient.invalidateQueries({ queryKey: ["company"] });
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal title={`Mark ${item.form} as filed`} onClose={onClose} width="max-w-md">
      <p className="text-sm text-text-secondary mb-3">{item.title} · {item.company}. The filing is kept in the client's Filings, and this due date leaves the list.</p>
      <div className="space-y-3 text-sm">
        <label className="block">
          <span className="text-xs text-text-muted">SRN (from the MCA receipt; optional)</span>
          <input className="input w-full mt-0.5" value={srn} onChange={(e) => setSrn(e.target.value)} placeholder="e.g. AB1234567" autoFocus />
        </label>
        <label className="block">
          <span className="text-xs text-text-muted">Date filed</span>
          <input className="input w-full mt-0.5" type="date" value={filedOn} onChange={(e) => setFiledOn(e.target.value)} />
        </label>
        <label className="block">
          <span className="text-xs text-text-muted">Fees paid, in rupees (optional)</span>
          <input className="input w-full mt-0.5" inputMode="numeric" value={fees} onChange={(e) => setFees(e.target.value)} placeholder="e.g. 600" />
        </label>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <button className="btn" onClick={onClose} disabled={saving}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={saving}>Mark as filed</button>
      </div>
    </Modal>
  );
}
