import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Landmark } from "lucide-react";
import { aagam } from "../api/aagam";
import { day, titleCase } from "../lib/format";
import { Empty, PageHeader } from "../components/ui";

export default function FinancialsPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({ queryKey: ["financials"], queryFn: () => aagam.financials() });
  const statements = data?.statements ?? [];

  // One card per company, its years newest first.
  const byCompany = new Map<string, typeof statements>();
  statements.forEach((s) => {
    const name = s.client || s.company_name || "Company not identified";
    byCompany.set(name, [...(byCompany.get(name) ?? []), s]);
  });

  return (
    <div className="px-8 py-6 max-w-6xl">
      <PageHeader
        icon={<Landmark size={18} />}
        title="Financial statements"
        subtitle="Balance sheets and statements of profit and loss read from the library: the Schedule III ratios, where the money comes from, and what the figures make apply."
      />
      {!isLoading && statements.length === 0 && (
        <Empty
          icon={<Landmark size={18} />}
          title="No statements read yet."
          hint="Add audited financial statements to the library: a PDF (scanned or not), Word or Excel file. AAGAM finds the balance sheet and statement of profit and loss and reads every line, with the page it came from."
        />
      )}
      <div className="grid md:grid-cols-2 gap-4 stagger">
        {[...byCompany.entries()].map(([name, rows]) => (
          <section key={name} className="card card-hover p-4">
            <p className="font-semibold">{name}</p>
            <ul className="mt-2 divide-y divide-bg-border">
              {rows.map((s) => (
                <li key={s.id}>
                  <button className="w-full flex items-center gap-3 py-2 text-left hover:bg-bg-hover rounded px-1 -mx-1" onClick={() => navigate(`/financials/${s.id}`)}>
                    <span className="flex-1 min-w-0">
                      <span className="block text-sm">{s.period_end ? `Year to ${day(s.period_end)}` : "Period not found"}</span>
                      <span className="block text-xs text-text-muted truncate">{titleCase(s.basis)}{s.unit ? ` · ${s.unit}` : ""}{s.original_name ? ` · ${s.original_name}` : ""}</span>
                    </span>
                    <ChevronRight size={15} className="text-text-muted" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
