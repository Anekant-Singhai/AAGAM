import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { day } from "../lib/format";

export default function DueDatesPage() {
  const [days, setDays] = useState(60);
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
      <p className="text-sm text-text-secondary">Worked out from the company file (meetings, appointments, allotments, charges…). Each date gives its legal basis; items marked “check” rest on a reading to confirm.</p>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-bg-secondary text-left">
            <tr className="text-xs text-text-muted">
              <th className="px-3 py-2">Due</th><th className="px-3 py-2">Form</th><th className="px-3 py-2">Company</th>
              <th className="px-3 py-2">What</th><th className="px-3 py-2">Basis</th>
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
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <p className="p-6 text-center text-text-muted">Nothing due in this window for the companies on file.</p>}
      </div>
    </div>
  );
}
