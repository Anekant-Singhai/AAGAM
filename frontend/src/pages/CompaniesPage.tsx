import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, ChevronRight, Plus, Search } from "lucide-react";
import { aagam } from "../api/aagam";
import { titleCase } from "../lib/format";
import { Empty, PageHeader, Skeleton } from "../components/ui";
import { Modal } from "../components/dialogs";
import RecordForm from "../components/RecordForm";

export default function CompaniesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const adding = params.get("new") === "1";
  const { data } = useQuery({ queryKey: ["companies", q], queryFn: () => aagam.companies(q), placeholderData: (p) => p });
  const companies = (data?.companies ?? []) as { id: number; name: string; cin: string | null; company_class?: string | null; status?: string | null; entity_type?: string }[];

  return (
    <div className="px-8 py-6 max-w-5xl">
      <PageHeader
        icon={<Building2 size={19} />}
        title="Clients"
        subtitle="The company file: each client's details, directors and KMP, meetings, charges, registrations and filings. Due dates are worked out from it."
        actions={<button className="btn btn-primary" onClick={() => setParams({ new: "1" })}><Plus size={14} /> New client</button>}
      />
      <label className="flex items-center gap-2 input py-1 w-80 mb-4">
        <Search size={13} className="text-text-muted" />
        <input className="bg-transparent outline-none flex-1" placeholder="Find by name or CIN" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {!data ? (
        <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>
      ) : companies.length === 0 ? (
        <Empty icon={<Building2 size={20} />} title={q ? "No client matches." : "No clients yet."} hint="Add a client company or LLP. Its due dates, documents and work then come together under it."
          action={<button className="btn btn-primary" onClick={() => setParams({ new: "1" })}><Plus size={14} /> New client</button>} />
      ) : (
        <div className="card overflow-hidden">
          <ul className="divide-y divide-bg-border stagger">
            {companies.map((c) => (
              <li key={c.id}>
                <button onClick={() => navigate(`/companies/${c.id}`)} className="w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-bg-hover/70 transition-colors">
                  <span className="w-9 h-9 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0"><Building2 size={16} /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium truncate">{c.name}</span>
                    <span className="block text-xs text-text-muted truncate">
                      <span className="font-mono">{c.cin ?? "No CIN on file"}</span>
                      {c.company_class && ` · ${titleCase(c.company_class)}`}
                      {c.status && ` · ${titleCase(c.status)}`}
                    </span>
                  </span>
                  <ChevronRight size={15} className="text-text-muted" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {adding && (
        <Modal title="New client" onClose={() => setParams({})} width="max-w-2xl">
          <p className="text-sm text-text-muted mb-4">The name is enough to start; with the CIN, AAGAM fills in the class, listing and state. Everything can be changed later.</p>
          <RecordForm
            entity="company"
            only={["name", "cin", "company_class", "date_of_incorporation", "paid_up_capital", "email"]}
            columns={2}
            submitLabel="Add client"
            onCancel={() => setParams({})}
            onSaved={(row) => {
              queryClient.invalidateQueries({ queryKey: ["companies"] });
              navigate(`/companies/${row.id}`);
            }}
          />
        </Modal>
      )}
    </div>
  );
}
