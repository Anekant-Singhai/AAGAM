import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Briefcase, Building2, CalendarClock, Files, Landmark, Pencil, Plus, Trash2, UserPlus } from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import { aagam } from "../api/aagam";
import { day, titleCase } from "../lib/format";
import { PageSkeleton, Section, Tabs } from "../components/ui";
import { consequences, Modal, MoreMenu, useConfirm } from "../components/dialogs";
import RecordForm from "../components/RecordForm";
import RecordTable, { show } from "../components/RecordTable";
import NotesPanel from "../components/NotesPanel";
import type { CompanyFile, RecordRow } from "../types";

type Tab = "details" | "people" | "meetings" | "filings" | "records";

export default function CompanyPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "details";
  const { data, error } = useQuery({ queryKey: ["company-file", id], queryFn: () => aagam.companyFile(id) });
  const { data: parties } = useQuery({ queryKey: ["parties"], queryFn: () => aagam.parties() });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["company-file", id] });
    queryClient.invalidateQueries({ queryKey: ["parties"] });
    queryClient.invalidateQueries({ queryKey: ["companies"] });
    queryClient.invalidateQueries({ queryKey: ["overview"] });
    queryClient.invalidateQueries({ queryKey: ["due"] });
  };

  if (error) return <p className="p-6 text-accent-red">{(error as Error).message}</p>;
  if (!data) return <PageSkeleton />;
  const c = data.company;
  const partyOptions = (parties?.parties ?? []).map((p) => ({ value: p.id, label: `${p.name}${p.din ? ` (DIN ${p.din})` : p.frn ? ` (FRN ${p.frn})` : ""}` }));
  const meetingOptions = data.meetings.map((m) => ({ value: m.id, label: `${String(m.kind).toUpperCase()} · ${day(m.date as string)}` }));
  const ids = { party_id: partyOptions, auditor_id: partyOptions, holder_id: partyOptions, meeting_id: meetingOptions };

  const removeCompany = async () => {
    const deps = await aagam.dependents("company", id);
    const ok = await confirm({
      title: `Delete ${c.name as string} from the company file?`,
      body: "Its record goes, with its history. Your notes on it are kept as general notes. This can't be undone.",
      items: consequences(deps),
      action: "Delete client",
      danger: true,
    });
    if (!ok) return;
    try {
      await aagam.deleteRecord("company", id);
      toast.success(`${c.name as string} deleted from the company file.`);
      refresh();
      navigate("/companies");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="px-8 py-6 max-w-6xl">
      <div className="flex items-start gap-3 mb-4">
        <button onClick={() => navigate("/companies")} className="btn btn-ghost px-1.5 mt-1" aria-label="Back"><ArrowLeft size={16} /></button>
        <div className="w-10 h-10 rounded-xl bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0 pop-in"><Building2 size={19} /></div>
        <div className="flex-1 min-w-0">
          <h1 className="text-[1.6rem] leading-tight font-semibold">{c.name as string}</h1>
          <p className="text-sm text-text-secondary mt-0.5 flex flex-wrap gap-x-2">
            <span className="font-mono">{(c.cin as string) ?? "No CIN on file"}</span>
            {c.company_class ? <span>· {titleCase(c.company_class as string)}</span> : null}
            {c.is_listed ? <span>· Listed</span> : null}
            {c.status ? <span>· {titleCase(c.status as string)}</span> : null}
          </p>
        </div>
        <Link className="btn" to={`/library?company=${id}`}><Files size={13} /> {data.library.documents} documents</Link>
        <Link className="btn" to={`/work?q=${encodeURIComponent(c.name as string)}`}><Briefcase size={13} /> {data.library.works} in hand</Link>
        <MoreMenu items={[{ label: "Delete this client", icon: <Trash2 size={14} />, danger: true, onClick: removeCompany }]} />
      </div>

      <Tabs<Tab>
        value={tab}
        onChange={(t) => setParams(t === "details" ? {} : { tab: t }, { replace: true })}
        className="mb-5"
        tabs={[
          { key: "details", label: "Details" },
          { key: "people", label: "Directors and KMP", count: data.people.filter((p) => !p.date_of_cessation).length },
          { key: "meetings", label: "Meetings", count: data.meetings.length },
          { key: "filings", label: "Filings", count: data.filings.length },
          { key: "records", label: "Other records", count: data.charges.length + data.registrations.length + data.events.length + data.auditors.length + data.resolutions.length },
        ]}
      />

      <div key={tab} className="fade-in">
        {tab === "details" && (
          <div className="grid lg:grid-cols-[1fr_300px] gap-5 items-start">
            <section className="card p-5">
              <RecordForm key={String(c.updated_at)} entity="company" value={{ ...c, sources: data.sources }} onSaved={() => { toast.success("Saved."); refresh(); }} />
            </section>
            <div className="space-y-4">
              <DueSoon data={data} />
              {data.library.financials.length > 0 && (
                <Section title="Accounts read">
                  <ul className="space-y-1">
                    {data.library.financials.map((f) => (
                      <li key={f.id}><Link to={`/financials/${f.id}`} className="flex items-center gap-2 text-sm hover:text-accent-brand"><Landmark size={13} className="text-text-muted" /> {titleCase(f.basis)}{f.period_end ? `, ${day(f.period_end)}` : ""}</Link></li>
                    ))}
                  </ul>
                </Section>
              )}
              <NotesPanel kind="company" target={String(id)} compact />
            </div>
          </div>
        )}
        {tab === "people" && <People data={data} companyId={id} ids={ids} onChanged={refresh} />}
        {tab === "meetings" && (
          <div className="space-y-5">
            <RecordTable title="Meetings" entity="meeting" rows={data.meetings} companyId={id} onChanged={refresh} addLabel="Add a meeting"
              columns={[{ key: "date" }, { key: "kind" }, { key: "fy", label: "Year" }, { key: "mode" }, { key: "venue" }]}
              empty="No meetings on file. Add the last AGM and board meetings: the due dates for AOC-4, MGT-7 and MGT-14 run from them." />
            <RecordTable title="Resolutions passed" entity="resolution" rows={data.resolutions} companyId={id} onChanged={refresh} idOptions={{ meeting_id: meetingOptions }} addLabel="Add a resolution"
              columns={[{ key: "passed_on" }, { key: "kind" }, { key: "subject" }, { key: "section_ref" }]} />
          </div>
        )}
        {tab === "filings" && (
          <RecordTable title="Filings" entity="filing" rows={data.filings} companyId={id} onChanged={refresh} addLabel="Add a filing"
            columns={[{ key: "form" }, { key: "due_on" }, { key: "status" }, { key: "srn", label: "SRN" }, { key: "filed_on" }]} />
        )}
        {tab === "records" && (
          <div className="space-y-5">
            <RecordTable title="Charges" entity="charge" rows={data.charges} companyId={id} onChanged={refresh} idOptions={{ holder_id: partyOptions }} addLabel="Add a charge"
              columns={[{ key: "charge_id", label: "Charge ID" }, { key: "holder_name", label: "Holder" }, { key: "amount" }, { key: "created_on" }, { key: "satisfied_on" }]} />
            <RecordTable title="Registrations" entity="registration" rows={data.registrations} companyId={id} onChanged={refresh} addLabel="Add a registration"
              columns={[{ key: "kind" }, { key: "number", render: (r) => <span className="font-mono">{r.number as string}</span> }, { key: "state" }, { key: "status" }]} />
            <RecordTable title="Auditors" entity="auditor_appointment" rows={data.auditors} companyId={id} onChanged={refresh} idOptions={{ auditor_id: partyOptions, meeting_id: meetingOptions }} addLabel="Add an auditor"
              columns={[{ key: "auditor_name", label: "Auditor" }, { key: "audit_type" }, { key: "appointed_on" }, { key: "from_fy" }, { key: "to_fy" }]} />
            <RecordTable title="Events (allotments, changes)" entity="event" rows={data.events} companyId={id} onChanged={refresh} addLabel="Add an event"
              columns={[{ key: "date" }, { key: "kind" }, { key: "allotment_type" }, { key: "details" }]} />
          </div>
        )}
      </div>
    </div>
  );
}

function DueSoon({ data }: { data: CompanyFile }) {
  return (
    <Section title="Due in 90 days">
      {data.due.length === 0 && <p className="text-sm text-text-muted">Nothing due from what is on file.</p>}
      <ul className="space-y-2">
        {data.due.slice(0, 8).map((d) => (
          <li key={`${d.form}-${d.trigger}`} className="flex gap-2 text-sm">
            {d.state === "overdue" ? <AlertTriangle size={13} className="text-accent-red mt-0.5 shrink-0" /> : <CalendarClock size={13} className="text-text-muted mt-0.5 shrink-0" />}
            <span>
              <span className="font-medium">{d.form}</span> <span className={clsx("text-xs", d.state === "overdue" ? "text-accent-red" : "text-text-muted")}>{day(d.due)}</span>
              <span className="block text-xs text-text-muted">{d.law}</span>
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function People({ data, companyId, ids, onChanged }: {
  data: CompanyFile; companyId: number; ids: Record<string, { value: number; label: string }[]>; onChanged: () => void;
}) {
  const confirm = useConfirm();
  const [adding, setAdding] = useState<"position" | "person" | null>(null);
  const [newParty, setNewParty] = useState<number | null>(null);
  const [editPosition, setEditPosition] = useState<number | null>(null);
  const [editPerson, setEditPerson] = useState<number | null>(null);
  const { data: position } = useQuery({ queryKey: ["record", "appointment", editPosition], queryFn: () => aagam.record("appointment", editPosition!), enabled: editPosition !== null });
  const { data: person } = useQuery({ queryKey: ["record", "party", editPerson], queryFn: () => aagam.record("party", editPerson!), enabled: editPerson !== null });

  const endPosition = async (appointmentId: number, name: string) => {
    if (!(await confirm({ title: `Delete ${name}'s position?`, body: "Only the position in this company goes; the person stays in the company file. To record a resignation, change the position and give the date it ceased instead.", action: "Delete position", danger: true }))) return;
    await aagam.deleteRecord("appointment", appointmentId);
    toast.success("Position deleted.");
    onChanged();
  };
  const removePerson = async (partyId: number, name: string) => {
    const deps = await aagam.dependents("party", partyId);
    if (!(await confirm({ title: `Delete ${name} from the company file?`, body: "The person goes from every company, with all their positions.", items: consequences(deps), action: "Delete person", danger: true }))) return;
    await aagam.deleteRecord("party", partyId);
    toast.success(`${name} deleted.`);
    onChanged();
  };

  const current = data.people.filter((p) => !p.date_of_cessation);
  const past = data.people.filter((p) => p.date_of_cessation);
  const rows = (list: typeof data.people) => list.map((p) => (
    <tr key={p.appointment_id} className="group border-b border-bg-border/60 last:border-b-0 hover:bg-bg-hover/50">
      <td className="px-4 py-2">
        <button className="font-medium hover:text-accent-brand text-left" onClick={() => setEditPerson(p.party_id)}>{p.name}</button>
        {p.din && <span className="block text-xs text-text-muted font-mono">DIN {p.din}</span>}
      </td>
      <td className="px-4 py-2">{show("role", p.role)}{p.category ? <span className="block text-xs text-text-muted">{titleCase(p.category as string)}</span> : null}</td>
      <td className="px-4 py-2">{show("date_of_appointment", p.date_of_appointment)}</td>
      <td className="px-4 py-2">{show("date_of_cessation", p.date_of_cessation)}{p.cessation_reason ? <span className="block text-xs text-text-muted">{titleCase(p.cessation_reason as string)}</span> : null}</td>
      <td className="px-4 py-2 text-xs">{p.kyc_next_due ? `KYC by ${day(p.kyc_next_due as string)}` : ""}</td>
      <td className="px-2 py-1.5 text-right whitespace-nowrap">
        <span className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
          <button className="btn btn-ghost px-1.5 py-1" onClick={() => setEditPosition(p.appointment_id)} title="Change the position" aria-label="Change the position"><Pencil size={13} /></button>
          <MoreMenu className="inline-block" items={[
            { label: "Change the person's details", icon: <UserPlus size={14} />, onClick: () => setEditPerson(p.party_id) },
            { label: "Delete this position", icon: <Trash2 size={14} />, danger: true, onClick: () => endPosition(p.appointment_id, p.name) },
            { label: "Delete the person everywhere", icon: <Trash2 size={14} />, danger: true, onClick: () => removePerson(p.party_id, p.name) },
          ]} />
        </span>
      </td>
    </tr>
  ));

  return (
    <section className="card">
      <div className="flex items-center px-4 pt-3 pb-2 gap-2">
        <p className="label flex-1">Directors, KMP and partners</p>
        <button className="btn btn-ghost py-1 text-xs" onClick={() => setAdding("person")}><UserPlus size={13} /> New person</button>
        <button className="btn btn-primary py-1 text-xs" onClick={() => setAdding("position")}><Plus size={13} /> Add a position</button>
      </div>
      {data.people.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-text-muted">No one on file. Add the directors and KMP: their DIN KYC dates and DIR-12 due dates follow.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-text-muted text-left border-y border-bg-border bg-bg-secondary/60">
              <th className="font-medium px-4 py-1.5">Name</th><th className="font-medium px-4 py-1.5">Position</th>
              <th className="font-medium px-4 py-1.5">Appointed</th><th className="font-medium px-4 py-1.5">Ceased</th><th className="px-4" /><th className="w-24" />
            </tr>
          </thead>
          <tbody className="stagger">{rows(current)}</tbody>
          {past.length > 0 && (
            <tbody>
              <tr><td colSpan={6} className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">No longer in office</td></tr>
              {rows(past)}
            </tbody>
          )}
        </table>
      )}

      {adding === "position" && (
        <Modal title="Add a position" onClose={() => { setAdding(null); setNewParty(null); }} width="max-w-3xl">
          <p className="text-sm text-text-muted mb-3">Pick the person, or <button className="text-accent-brand underline" onClick={() => setAdding("person")}>add someone new</button> first.</p>
          <RecordForm
            key={newParty ?? "pick"}
            entity="appointment"
            fixed={{ company_id: companyId }}
            defaults={newParty ? { party_id: newParty } : undefined}
            idOptions={{ party_id: ids.party_id, meeting_id: ids.meeting_id }}
            submitLabel="Add position"
            onCancel={() => setAdding(null)}
            onSaved={() => { setAdding(null); setNewParty(null); toast.success("Position added."); onChanged(); }}
          />
        </Modal>
      )}
      {adding === "person" && (
        <Modal title="New person or organisation" onClose={() => setAdding(null)} width="max-w-3xl">
          <RecordForm
            entity="party"
            submitLabel="Add, then give their position"
            onCancel={() => setAdding(null)}
            onSaved={(row) => { setNewParty(row.id); onChanged(); setAdding("position"); toast.success(`${row.name as string} added. Now choose them for the position.`); }}
          />
        </Modal>
      )}
      {editPosition !== null && position && (
        <Modal title="Change the position" onClose={() => setEditPosition(null)} width="max-w-3xl">
          <RecordForm entity="appointment" value={position} fixed={{ company_id: companyId, party_id: position.party_id }} idOptions={{ meeting_id: ids.meeting_id }}
            onCancel={() => setEditPosition(null)} onSaved={() => { setEditPosition(null); toast.success("Saved."); onChanged(); }} />
        </Modal>
      )}
      {editPerson !== null && person && (
        <Modal title={person.name as string} onClose={() => setEditPerson(null)} width="max-w-4xl">
          <RecordForm entity="party" value={person as RecordRow} onCancel={() => setEditPerson(null)} onSaved={() => { setEditPerson(null); toast.success("Saved."); onChanged(); }} />
        </Modal>
      )}
    </section>
  );
}
