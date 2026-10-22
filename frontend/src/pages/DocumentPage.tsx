import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Bot, Briefcase, ChevronLeft, ChevronRight, ClipboardCheck, Download, ExternalLink, EyeOff, FilePen, Image, Landmark, Loader2,
  PanelRightClose, PanelRightOpen, Pencil, Plus, RefreshCw, ScanText, Search, Trash2, X,
} from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { byWhom, crore, day, highlightWords, rupees, titleCase } from "../lib/format";
import { FACT_LABELS, FACT_ORDER, type DocInsight, type DocumentFull, type Fact } from "../types";
import TagBadge from "../components/tags/TagBadge";
import TagPicker from "../components/tags/TagPicker";
import NotesPanel from "../components/NotesPanel";
import { Cell, Confidence, KindIcon, ScoreBar } from "../components/insights";
import { PageSkeleton, Status, Tabs } from "../components/ui";
import { MoreMenu, useConfirm } from "../components/dialogs";
import { rememberOpened, usePreference } from "../lib/theme";

type Side = "about" | "checks" | "facts" | "insights" | "work";

export default function DocumentPage() {
  const id = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1);
  const find = params.get("q") ?? "";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [panel, setPanel] = usePreference("aagam.doc.panel", true);
  const [side, setSide] = useState<Side>("about");
  const [editingText, setEditingText] = useState<string | null>(null);
  const [editingDetails, setEditingDetails] = useState(false);
  const confirm = useConfirm();

  const { data: doc, error } = useQuery({ queryKey: ["document", id], queryFn: () => aagam.document(id) });
  const { data: pageData } = useQuery({ queryKey: ["page", id, page], queryFn: () => aagam.page(id, page), enabled: !!doc, placeholderData: (p) => p });
  const { data: hits } = useQuery({ queryKey: ["in-doc", id, find], queryFn: () => aagam.searchIn(id, find), enabled: find.trim().length > 1 });
  const { data: insights } = useQuery({ queryKey: ["doc-insights", id], queryFn: () => aagam.insightsOf(id), enabled: !!doc && (pageData !== undefined || side === "insights") });
  const insightCount = insights?.analyses.reduce((n, a) => n + a.items.length, 0) ?? 0;
  const [showImage, setShowImage] = useState(false);
  const [findInput, setFindInput] = useState(find);
  useEffect(() => setShowImage(Boolean(pageData?.needs_vision)), [pageData?.needs_vision, page]);
  useEffect(() => {
    if (doc) rememberOpened({ id: doc.id, title: doc.title || doc.original_name });
  }, [doc?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = (updated: DocumentFull) => {
    queryClient.setQueryData(["document", id], updated);
    queryClient.invalidateQueries({ queryKey: ["tags"] });
    queryClient.invalidateQueries({ queryKey: ["documents"] });
  };
  const goTo = (p: number) => {
    setEditingText(null);
    const next = new URLSearchParams(params);
    next.set("page", String(p));
    setParams(next, { replace: true });
  };
  const savePage = useMutation({
    mutationFn: (text: string) => aagam.editPage(id, page, text),
    onSuccess: (updated) => {
      queryClient.setQueryData(["page", id, page], updated);
      queryClient.invalidateQueries({ queryKey: ["document", id] });
      setEditingText(null);
      toast.success("Page saved. Facts and resolutions were read again from your text.");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const removeDocument = async () => {
    if (!doc) return;
    const name = doc.title || doc.original_name;
    const ok = await confirm({
      title: `Move “${name}” to the Trash?`,
      body: "It leaves the library straight away: its pages, facts, resolutions and statements, and it is taken off any work.",
      items: [
        "From the Trash you can restore it as it was, with your corrections, tags and notes",
        "Values in the company file quoted from it keep their quote",
      ],
      action: "Move to Trash",
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await aagam.deleteDocument(id);
      queryClient.invalidateQueries();
      const trashId = result.trash_id;
      toast.success(
        (t) => (
          <span>
            Moved to the Trash.{" "}
            {trashId ? (
              <button
                className="underline font-medium"
                onClick={async () => {
                  toast.dismiss(t.id);
                  try {
                    const back = await aagam.restore(trashId);
                    queryClient.invalidateQueries();
                    toast.success("Restored.");
                    navigate(`/documents/${back.document_id}`);
                  } catch (e) {
                    toast.error((e as Error).message);
                  }
                }}
              >
                Undo
              </button>
            ) : result.file_kept_in ? `The file is in ${result.file_kept_in}.` : null}
          </span>
        ),
        { duration: 8000 }
      );
      navigate("/library");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  // The arrow keys turn the pages (unless she is typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (!doc || editingText !== null || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || e.ctrlKey || e.altKey || e.metaKey) return;
      if (e.key === "ArrowRight" && page < doc.pages) goTo(page + 1);
      if (e.key === "ArrowLeft" && page > 1) goTo(page - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (error) return <p className="p-6 text-accent-red">{(error as Error).message}</p>;
  if (!doc) return <PageSkeleton rows={6} />;

  const checks = (doc.doc_type === "notice" || doc.doc_type === "annual_report" ? 1 : 0) + doc.resolutions.length + (doc.financials?.length ?? 0);
  const factCount = FACT_ORDER.reduce((n, k) => n + (doc.facts[k]?.length ?? 0), 0);

  return (
    <div className="flex h-full">
      {/* Reader */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="px-5 py-2.5 border-b border-bg-border bg-bg-secondary/80 backdrop-blur space-y-2">
          <div className="flex items-center gap-2">
            <button onClick={() => navigate(-1)} className="btn btn-ghost px-1.5" aria-label="Back"><ArrowLeft size={16} /></button>
            <div className="min-w-0 flex-1">
              <h1 className="font-semibold truncate text-[17px] leading-tight" title={doc.title || doc.original_name}>{doc.title || doc.original_name}</h1>
              <p className="text-xs text-text-muted truncate">{titleCase(doc.doc_type)}{doc.company_name ? ` · ${doc.company_name}` : ""}{doc.meeting_date ? ` · ${day(doc.meeting_date)}` : ""}</p>
            </div>
            <form
              className="flex items-center gap-1.5 input py-1 w-48 focus-within:w-72 transition-[width] duration-300"
              onSubmit={(e) => {
                e.preventDefault();
                const next = new URLSearchParams(params);
                if (findInput.trim()) next.set("q", findInput.trim());
                else next.delete("q");
                setParams(next);
              }}
            >
              <Search size={13} className="text-text-muted shrink-0" />
              <input className="bg-transparent outline-none flex-1 min-w-0" placeholder="Find in this document" value={findInput} onChange={(e) => setFindInput(e.target.value)} />
            </form>
            {doc.media_type === "application/pdf" && (
              <button className={clsx("btn btn-ghost px-1.5", showImage && "bg-accent-brand/10 text-accent-brand")} onClick={() => setShowImage(!showImage)} title="Show the page as it looks" aria-pressed={showImage}>
                <Image size={16} />
              </button>
            )}
            <a className="btn btn-ghost px-1.5" href={aagam.fileUrl(id)} target="_blank" rel="noreferrer" title="Open the original"><ExternalLink size={15} /></a>
            <a className="btn btn-ghost px-1.5" href={aagam.fileUrl(id, true)} title="Download"><Download size={15} /></a>
            <button className="btn btn-ghost px-1.5" onClick={() => setPanel(!panel)} title={panel ? "Hide the side panel" : "Show the side panel"} aria-label={panel ? "Hide the side panel" : "Show the side panel"}>
              {panel ? <PanelRightClose size={16} /> : <PanelRightOpen size={16} />}
            </button>
            <MoreMenu
              label="More about this document"
              items={[
                { label: "Correct this page's text", icon: <FilePen size={14} />, onClick: () => { setShowImage(false); setEditingText(pageData?.text ?? ""); }, hidden: !pageData },
                { label: "Change the details", icon: <Pencil size={14} />, onClick: () => { setPanel(true); setSide("about"); setEditingDetails(true); } },
                { label: "Move to Trash", icon: <Trash2 size={14} />, danger: true, onClick: removeDocument },
              ]}
            />
          </div>
          {(find && hits) || doc.ocr_pages.length || doc.scanned_pages.length ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <ReadingBadges doc={doc} page={page} />
              {find && hits && (
                <>
                  <span className="text-text-muted">{hits.pages.length ? "Found on page" : "Not found in this document."}</span>
                  {hits.pages.map((h) => (
                    <button key={h.page} onClick={() => goTo(h.page)} className={clsx("chip transition-colors", h.page === page ? "bg-accent-brand text-on-accent" : "tag-0")}>
                      {h.page}
                    </button>
                  ))}
                </>
              )}
            </div>
          ) : null}
        </div>
        <div className="flex-1 overflow-auto px-6 pt-8 pb-24 bg-bg-primary relative">
          {showImage ? (
            <img key={`img-${page}`} src={aagam.pageImageUrl(id, page)} alt={`Page ${page}`} className="mx-auto rounded-sm border border-bg-border max-w-full fade-in" style={{ boxShadow: "0 12px 40px -12px rgb(var(--shadow) / 0.35)" }} />
          ) : editingText !== null ? (
            <div className="max-w-[52rem] mx-auto fade-in">
              <div className="flex items-center gap-2 mb-2 text-sm">
                <FilePen size={15} className="text-accent-brand" />
                <span className="flex-1 text-text-secondary">Correcting page {page}. When you save, its facts, resolutions and figures are read again from your text, and kept as yours.</span>
                <button className="btn" onClick={() => setEditingText(null)}>Cancel</button>
                <button className="btn btn-primary" disabled={savePage.isPending} onClick={() => savePage.mutate(editingText)}>{savePage.isPending ? <Loader2 size={14} className="animate-spin" /> : null} Save page</button>
              </div>
              <textarea
                className="legal w-full min-h-[70vh] bg-bg-surface border border-accent-brand/50 rounded-md px-12 py-10 outline-none"
                style={{ boxShadow: "0 0 0 4px rgb(var(--accent-brand) / 0.08)" }}
                value={editingText}
                onChange={(e) => setEditingText(e.target.value)}
                aria-label="Page text"
                autoFocus
              />
            </div>
          ) : pageData?.needs_vision ? (
            <p className="text-text-muted text-center">This page is a scan with no text layer yet. Use the image view, or ask Claude Desktop to read it.</p>
          ) : (
            <article
              key={`page-${page}`}
              className="legal max-w-[52rem] mx-auto bg-bg-surface border border-bg-border rounded-md px-12 py-10 fade-in"
              style={{ boxShadow: "0 1px 2px rgb(var(--shadow) / 0.05), 0 16px 40px -18px rgb(var(--shadow) / 0.25)" }}
            >
              {doc.edited_pages.includes(page) ? (
                <p className="font-sans text-xs text-accent-green mb-5 flex items-center gap-1.5 whitespace-normal">
                  <FilePen size={13} /> You corrected this page's text.
                </p>
              ) : doc.ocr_pages.includes(page) && (
                <p className="font-sans text-xs text-text-muted mb-5 flex items-center gap-1.5 whitespace-normal">
                  <ScanText size={13} /> This page is a scan; its text was read by Windows OCR. Check it against the image, and
                  <button className="underline hover:text-text-primary" onClick={() => setEditingText(pageData?.text ?? "")}>correct it</button> if needed.
                </p>
              )}
              {highlightWords(pageData?.text ?? "", find)}
              <p className="font-sans text-[11px] text-text-muted text-center mt-8 tabular">{page}</p>
            </article>
          )}
        </div>
        <div className="relative">
          <div className="absolute bottom-5 left-1/2 -translate-x-1/2 card rounded-full flex items-center gap-1 px-1.5 py-1 text-sm pop-in" style={{ boxShadow: "0 10px 30px -8px rgb(var(--shadow) / 0.3)" }}>
            <button className="btn btn-ghost rounded-full px-1.5 py-1" disabled={page <= 1} onClick={() => goTo(page - 1)} aria-label="Previous page" title="Previous page (←)"><ChevronLeft size={16} /></button>
            <span className="text-text-secondary px-1 text-center tabular whitespace-nowrap">Page {page} of {doc.pages}</span>
            <button className="btn btn-ghost rounded-full px-1.5 py-1" disabled={page >= doc.pages} onClick={() => goTo(page + 1)} aria-label="Next page" title="Next page (→)"><ChevronRight size={16} /></button>
          </div>
        </div>
      </div>

      {/* What AAGAM knows about it */}
      {panel && (
        <aside className="w-[400px] shrink-0 flex flex-col border-l border-bg-border bg-bg-secondary/80 backdrop-blur slide-in-right">
          <Tabs<Side>
            value={side}
            onChange={setSide}
            className="px-2 pt-1 shrink-0 gap-0 overflow-x-auto [&_.tab]:px-2 [&_.tab]:whitespace-nowrap"
            tabs={[
              { key: "about", label: "About" },
              { key: "checks", label: "Checks", count: checks },
              { key: "facts", label: "Facts", count: factCount },
              { key: "insights", label: "Insights", count: insightCount },
              { key: "work", label: "Notes", count: (doc.works?.length ?? 0) + (doc.notes?.length ?? 0) },
            ]}
          />
          <div key={side} className="flex-1 overflow-auto p-4 space-y-4 stagger">
            {side === "about" && (
              <>
                <Details doc={doc} onChange={refresh} editing={editingDetails} setEditing={setEditingDetails} />
                <SummaryPanel doc={doc} onChange={refresh} />
                <TagsPanel doc={doc} onChange={refresh} />
              </>
            )}
            {side === "checks" && (
              <>
                {(doc.doc_type === "notice" || doc.doc_type === "annual_report" || doc.resolutions.length > 0) && <NoticeCheckPanel doc={doc} goTo={goTo} />}
                <FinancialsPanel doc={doc} />
                {doc.resolutions.length > 0 && <Resolutions doc={doc} goTo={goTo} />}
                {checks === 0 && !["financial_statements", "annual_report", "auditor_report"].includes(doc.doc_type) && (
                  <p className="text-sm text-text-muted px-1 leading-6">Nothing to check in this kind of document. Notices get the notice check; accounts get the financial analysis.</p>
                )}
              </>
            )}
            {side === "facts" && (factCount ? <Facts doc={doc} goTo={goTo} /> : <p className="text-sm text-text-muted px-1">No CINs, DINs, amounts or other facts found.</p>)}
            {side === "insights" && <InsightsPanel id={doc.id} analyses={insights?.analyses} goTo={goTo} />}
            {side === "work" && (
              <>
                <WorkPanel doc={doc} />
                <NotesPanel kind="document" target={String(doc.id)} initial={doc.notes} />
              </>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}

const MEETINGS: Record<string, string> = { agm: "AGM", egm: "EGM", board: "Board meeting", committee: "Committee meeting", postal_ballot: "Postal ballot" };

function Details({ doc, onChange, editing, setEditing }: { doc: DocumentFull; onChange: (d: DocumentFull) => void; editing: boolean; setEditing: (v: boolean) => void }) {
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: aagam.meta, staleTime: Infinity });
  const { data: companies } = useQuery({ queryKey: ["companies"], queryFn: () => aagam.companies(), enabled: editing });
  const change = useMutation({ mutationFn: (doc_type: string) => aagam.change(doc.id, { doc_type }), onSuccess: onChange });
  const reindex = useMutation({ mutationFn: () => aagam.reindex(doc.id), onSuccess: (d) => { onChange(d); toast.success("Read again."); } });
  const blank = () => ({
    title: doc.title ?? "", company: doc.company_id ? String(doc.company_id) : "", company_name: doc.company_name ?? "",
    meeting_kind: doc.meeting_kind ?? "", meeting_date: doc.meeting_date ?? "", note: doc.note ?? "", doc_date: doc.doc_date ?? "",
  });
  const [form, setForm] = useState(blank);
  useEffect(() => { if (editing) setForm(blank()); }, [editing]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    // The document's date is sent only when she changed it, so a date AAGAM worked out doesn't become "hers" unasked.
    mutationFn: () => {
      const { doc_date, ...rest } = form;
      return aagam.change(doc.id, doc_date !== (doc.doc_date ?? "") ? { ...rest, doc_date } : rest);
    },
    onSuccess: (d) => { onChange(d); setEditing(false); toast.success("Saved. These details are kept even when the document is read again."); },
    onError: (e: Error) => toast.error(e.message),
  });
  const set = (k: keyof ReturnType<typeof blank>) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  if (editing) {
    return (
      <section className="card p-3 space-y-2.5 text-sm pop-in">
        <p className="label">Details</p>
        <label className="block"><span className="text-xs text-text-muted">Title</span><input className="input w-full mt-0.5" value={form.title} onChange={set("title")} /></label>
        <label className="block"><span className="text-xs text-text-muted">Client (whose file it belongs in)</span>
          <select className="input w-full mt-0.5" value={form.company} onChange={set("company")}>
            <option value="">Not a client's document</option>
            {companies?.companies.map((c) => <option key={c.id} value={String(c.id)}>{c.name}</option>)}
          </select>
        </label>
        <label className="block"><span className="text-xs text-text-muted">About (the company it is about, as you want it shown)</span><input className="input w-full mt-0.5" value={form.company_name} onChange={set("company_name")} /></label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block"><span className="text-xs text-text-muted">Meeting</span>
            <select className="input w-full mt-0.5" value={form.meeting_kind} onChange={set("meeting_kind")}>
              <option value="">None</option>
              {Object.entries(MEETINGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="block"><span className="text-xs text-text-muted">Meeting date</span><input type="date" className="input w-full mt-0.5" value={form.meeting_date} onChange={set("meeting_date")} /></label>
        </div>
        <label className="block"><span className="text-xs text-text-muted">The document's date (the library sorts and filters by it)</span>
          <input type="date" className="input w-full mt-0.5" value={form.doc_date} onChange={set("doc_date")} aria-label="The document's date" />
        </label>
        <label className="block"><span className="text-xs text-text-muted">Note on the file</span><textarea className="input w-full mt-0.5 h-16" value={form.note} onChange={set("note")} /></label>
        <div className="flex gap-2 pt-1">
          <button className="btn btn-primary py-1" onClick={() => save.mutate()} disabled={save.isPending}>Save</button>
          <button className="btn py-1" onClick={() => setEditing(false)}>Cancel</button>
        </div>
      </section>
    );
  }
  return (
    <section className="card p-3 space-y-2 text-sm group">
      <div className="flex items-center gap-2">
        <select className="input py-1 flex-1 min-w-0" value={doc.doc_type} onChange={(e) => change.mutate(e.target.value)} aria-label="Document type">
          {Object.entries(meta?.doc_types ?? {}).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <button className="btn px-2" onClick={() => setEditing(true)} title="Change the details" aria-label="Change the details"><Pencil size={13} /></button>
        <button className="btn px-2" onClick={() => reindex.mutate()} title="Read the document again"><RefreshCw size={13} /></button>
      </div>
      {doc.detected_why && <p className="text-xs text-text-muted">Recognised from {doc.detected_why}</p>}
      <dl className="grid grid-cols-[110px_1fr] gap-y-1 text-xs">
        {doc.company_name && (<><dt className="text-text-muted">About</dt><dd>{doc.company_name}{doc.overrides.company_name ? <span className="text-accent-green"> · yours</span> : null}</dd></>)}
        {doc.company_cin && (<><dt className="text-text-muted">CIN</dt><dd className="font-mono">{doc.company_cin}</dd></>)}
        {doc.meeting_kind && (<><dt className="text-text-muted">Meeting</dt><dd>{MEETINGS[doc.meeting_kind] ?? doc.meeting_kind.toUpperCase()}{doc.meeting_date ? `, ${day(doc.meeting_date)}` : ""}</dd></>)}
        {doc.client && (
          <>
            <dt className="text-text-muted">Client</dt>
            <dd>
              <Link to={`/companies/${doc.company_id}`} className="hover:text-accent-brand">{doc.client}</Link>
              {doc.client_why && <span className="block text-text-muted">{doc.client_why === "set by her" ? "You chose it" : `From ${doc.client_why}`}</span>}
            </dd>
          </>
        )}
        {doc.doc_date && (
          <>
            <dt className="text-text-muted">Dated</dt>
            <dd>
              {day(doc.doc_date)}{doc.fy ? ` · FY ${doc.fy}` : ""}
              {doc.doc_date_basis && <span className={clsx("block", doc.doc_date_basis === "set by her" ? "text-accent-green" : "text-text-muted")}>{doc.doc_date_basis === "set by her" ? "Yours" : `From ${doc.doc_date_basis}`}</span>}
            </dd>
          </>
        )}
        {(doc.source_path || doc.folder_path) && (
          <>
            <dt className="text-text-muted">From</dt>
            <dd className="break-all font-mono text-[11px] leading-4 pt-0.5" title="Where the file was on your computer">
              {doc.source_path ?? [doc.folder_path, doc.source_folder].filter(Boolean).join("\\")}
            </dd>
          </>
        )}
        {!doc.source_path && !doc.folder_path && doc.source_folder && (
          <><dt className="text-text-muted">Folder</dt><dd className="break-all">{doc.source_folder}</dd></>
        )}
        <dt className="text-text-muted">File</dt><dd className="truncate" title={doc.original_name}>{doc.original_name}</dd>
        <dt className="text-text-muted">Added</dt><dd>{day(doc.ingested_at.slice(0, 10))} · {doc.words.toLocaleString("en-IN")} words</dd>
        {doc.note && (<><dt className="text-text-muted">Note</dt><dd className="whitespace-pre-wrap">{doc.note}</dd></>)}
      </dl>
    </section>
  );
}

function SummaryPanel({ doc, onChange }: { doc: DocumentFull; onChange: (d: DocumentFull) => void }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(doc.summary ?? "");
  useEffect(() => setText(doc.summary ?? ""), [doc.summary]);
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: () => aagam.saveSummary(doc.id, text, doc.key_points),
    onSuccess: (d) => { onChange(d); setEditing(false); },
    onError: (e: Error) => toast.error(e.message),
  });
  const summarise = useMutation({
    mutationFn: () => aagam.summarise(doc.id),
    onSuccess: ({ ai }) => {
      toast(ai.running && ai.model_installed ? "Queued for local AI; it appears here when done." : ai.message, { icon: "🤖" });
      queryClient.invalidateQueries({ queryKey: ["ai-status"] });
    },
  });
  const lastJob = doc.ai_jobs[0];
  return (
    <section className="card p-3 space-y-2">
      <div className="flex items-center gap-2">
        <p className="label flex-1">Summary</p>
        {!editing && <button className="text-text-muted hover:text-text-primary" onClick={() => setEditing(true)} aria-label="Edit summary"><Pencil size={13} /></button>}
        {doc.summary_by !== "her" && (
          <button className="btn py-0.5 px-2 text-xs" onClick={() => summarise.mutate()} disabled={summarise.isPending}>
            <Bot size={12} /> {doc.summary ? "Again" : "Summarise"}
          </button>
        )}
      </div>
      {editing ? (
        <>
          <textarea className="input w-full h-32 text-sm" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex gap-2">
            <button className="btn btn-primary py-1" onClick={() => save.mutate()}>Save</button>
            <button className="btn py-1" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </>
      ) : doc.summary ? (
        <>
          <p className="text-sm leading-6">{doc.summary}</p>
          {doc.key_points.length > 0 && (
            <ul className="text-sm list-disc pl-5 space-y-0.5 text-text-secondary">
              {doc.key_points.map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          )}
          <p className="text-xs text-text-muted">{byWhom(doc.summary_by)}{doc.summary_at ? `, ${day(doc.summary_at.slice(0, 10))}` : ""}</p>
        </>
      ) : (
        <p className="text-sm text-text-muted">
          No summary yet.{" "}
          {lastJob?.status === "queued" ? "Waiting for local AI." : lastJob?.status === "skipped" || lastJob?.status === "failed" ? lastJob.note : ""}
        </p>
      )}
    </section>
  );
}

function TagsPanel({ doc, onChange }: { doc: DocumentFull; onChange: (d: DocumentFull) => void }) {
  const tags = useMutation({
    mutationFn: ({ add, remove }: { add?: string[]; remove?: string[] }) => aagam.tags(doc.id, add, remove),
    onSuccess: onChange,
    onError: (e: Error) => toast.error(e.message),
  });
  const navigate = useNavigate();
  return (
    <section className="card p-3 space-y-2">
      <p className="label">Tags</p>
      <div className="flex flex-wrap gap-1.5">
        {doc.tags.map((t) => (
          <TagBadge
            key={t.name}
            tag={t.name}
            title={t.added_by === "auto" ? "Added by AAGAM from the text" : t.added_by === "her" ? "Added by you" : byWhom(t.added_by)}
            onClick={() => navigate(`/library?tag=${encodeURIComponent(t.name)}`)}
            onRemove={() => tags.mutate({ remove: [t.name] })}
          />
        ))}
        <TagPicker existingTags={doc.tags.map((t) => t.name)} onAdd={(t) => tags.mutate({ add: [t] })} />
      </div>
      {doc.suggested_tags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-text-muted">Suggested:</span>
          {doc.suggested_tags.map((t) => (
            <button key={t} className="chip border border-dashed border-bg-border text-text-secondary hover:text-text-primary" onClick={() => tags.mutate({ add: [t] })}>
              + {t}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function Resolutions({ doc, goTo }: { doc: DocumentFull; goTo: (p: number) => void }) {
  return (
    <section className="card p-3 space-y-2">
      <p className="label">Resolutions ({doc.resolutions.length})</p>
      <ol className="space-y-2">
        {doc.resolutions.map((r) => (
          <li key={r.id} className="text-sm group">
            <div className="flex gap-2">
              <span className="text-text-muted w-5 shrink-0">{r.item_no}.</span>
              <div className="min-w-0">
                <Link to={`/precedents?open=${r.id}`} className="hover:text-accent-brand">{r.title}</Link>
                <Link to={`/precedents?open=${r.id}&edit=1`} className="ml-1.5 inline-flex align-middle text-text-muted hover:text-accent-brand opacity-0 group-hover:opacity-100 transition-opacity" title="Correct this resolution" aria-label="Correct this resolution"><Pencil size={11} /></Link>
                <p className="text-xs text-text-muted mt-0.5 flex flex-wrap gap-x-2">
                  <span className={clsx(r.resolution_kind === "special" && "text-accent-amber font-medium")}>
                    {r.resolution_kind ? `${titleCase(r.resolution_kind)} resolution` : "No resolution text"}
                  </span>
                  {r.sections.filter((s) => !s.includes("(")).map((s) => <span key={s} className="font-mono">s.{s}</span>)}
                  {r.max_amount ? <span>{crore(r.max_amount)}</span> : null}
                  <button className="underline" onClick={() => goTo(r.page_from)}>p.{r.page_from}</button>
                </p>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Facts({ doc, goTo }: { doc: DocumentFull; goTo: (p: number) => void }) {
  const facts = doc.facts;
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const kinds = FACT_ORDER.filter((k) => facts[k]?.length);
  const hide = async (kind: string, f: Fact) => {
    const label = kind === "amount" ? rupees(f.value) : f.shown;
    const where = await confirm({
      title: `Hide “${label}”?`,
      body: "For a fact that isn't one: a name read wrongly, a heading taken for a company. It stays hidden when the document is read again. Hidden facts can be brought back from People and companies.",
      choices: [{ key: "here", label: "In this document" }, { key: "everywhere", label: "Everywhere", danger: true }],
    });
    if (!where) return;
    await aagam.hideFact(kind, f.value, where === "here" ? doc.id : undefined);
    queryClient.invalidateQueries({ queryKey: ["document", doc.id] });
    queryClient.invalidateQueries({ queryKey: ["entities"] });
    toast.success(where === "here" ? "Hidden in this document." : "Hidden everywhere.");
  };
  if (!kinds.length) return null;
  return (
    <section className="card p-3 space-y-3">
      <p className="label">Facts found</p>
      {kinds.map((kind) => (
        <div key={kind}>
          <p className="text-xs font-medium text-text-secondary mb-1">{FACT_LABELS[kind] ?? kind}</p>
          <ul className="space-y-1">
            {facts[kind].slice(0, 12).map((f) => (
              <li key={f.value} className="group text-sm flex gap-2 items-baseline" title={f.context}>
                <span className={clsx("min-w-0 truncate", ["cin", "llpin", "din", "pan", "gstin", "frn"].includes(kind) && "font-mono text-[13px]")}>
                  {kind === "amount" ? rupees(f.value) : kind === "date" ? day(f.value) : kind === "section" ? `s.${f.value}` : f.shown}
                </span>
                {f.detail && <span className="text-xs text-text-muted truncate">{f.detail}</span>}
                <span className="ml-auto flex gap-1 shrink-0 items-center">
                  {f.pages.slice(0, 4).map((p) => (
                    <button key={p} onClick={() => goTo(p)} className="text-xs text-accent-brand hover:underline">p.{p}</button>
                  ))}
                  <button className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-accent-red transition-opacity ml-1" onClick={() => hide(kind, f)} aria-label={`Hide ${f.shown}`} title="Not a fact: hide it">
                    <EyeOff size={12} />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function ReadingBadges({ doc, page }: { doc: DocumentFull; page: number }) {
  const waiting = doc.scanned_pages.filter((p) => !doc.ocr_pages.includes(p));
  if (!doc.ocr_pages.length && !waiting.length) return null;
  return (
    <>
      {doc.ocr_pages.length > 0 && (
        <span className={clsx("chip", doc.ocr_pages.includes(page) ? "tag-2" : "bg-bg-hover text-text-secondary")} title={`Pages ${doc.ocr_pages.join(", ")}`}>
          <ScanText size={11} /> {doc.ocr_pages.length} scanned page{doc.ocr_pages.length === 1 ? "" : "s"} read by OCR
        </span>
      )}
      {waiting.length > 0 && (
        <span className="chip bg-bg-hover text-text-secondary" title={`Pages ${waiting.join(", ")}`}>
          <Loader2 size={11} className="animate-spin" /> {waiting.length} scanned page{waiting.length === 1 ? "" : "s"} waiting to be read
        </span>
      )}
    </>
  );
}

function WorkPanel({ doc }: { doc: DocumentFull }) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const { data } = useQuery({ queryKey: ["works", "open"], queryFn: () => aagam.works("open"), enabled: adding });
  const attach = useMutation({
    mutationFn: (workId: number) => aagam.attach(workId, doc.id),
    onSuccess: (w) => {
      queryClient.invalidateQueries({ queryKey: ["document", doc.id] });
      queryClient.invalidateQueries({ queryKey: ["works"] });
      setAdding(false);
      toast.success(`Added to “${w.title}”.`);
    },
  });
  const works = doc.works ?? [];
  const attached = new Set(works.map((w) => w.id));
  return (
    <section className="card p-3 space-y-2">
      <div className="flex items-center gap-2">
        <p className="label flex-1 flex items-center gap-1.5"><Briefcase size={12} /> Work</p>
        <button className="btn btn-ghost py-0.5 px-1.5 text-xs" onClick={() => setAdding(!adding)}><Plus size={12} /> Add to work</button>
      </div>
      {works.length === 0 && !adding && <p className="text-sm text-text-muted">Not part of any work yet.</p>}
      <ul className="space-y-1">
        {works.map((w) => (
          <li key={w.id}><Link to={`/work/${w.id}`} className="text-sm hover:text-accent-brand">{w.title}</Link> <span className="text-xs text-text-muted">{w.status}</span></li>
        ))}
      </ul>
      {adding && (
        <div className="space-y-1">
          {data?.works.filter((w) => !attached.has(w.id)).map((w) => (
            <button key={w.id} className="w-full text-left text-sm px-2 py-1 rounded hover:bg-bg-hover truncate" onClick={() => attach.mutate(w.id)}>+ {w.title}</button>
          ))}
          {data && data.works.length === 0 && <p className="text-sm text-text-muted">No open work. <Link className="text-accent-brand underline" to="/work?new=1">Start one</Link>.</p>}
        </div>
      )}
    </section>
  );
}

function NoticeCheckPanel({ doc, goTo }: { doc: DocumentFull; goTo: (p: number) => void }) {
  const [run, setRun] = useState(false);
  const { data, isFetching, error } = useQuery({ queryKey: ["notice-check", doc.id], queryFn: () => aagam.checkNotice(doc.id), enabled: run });
  return (
    <section className="card p-3 space-y-2">
      <div className="flex items-center gap-2">
        <p className="label flex-1 flex items-center gap-1.5"><ClipboardCheck size={12} /> Notice check</p>
        {!data && (
          <button className="btn py-0.5 px-2 text-xs" onClick={() => setRun(true)} disabled={isFetching}>
            {isFetching ? <Loader2 size={12} className="animate-spin" /> : <ClipboardCheck size={12} />} Check this notice
          </button>
        )}
      </div>
      {!run && <p className="text-xs text-text-muted">Checks the notice against ss.101 to 108, rule 20 and SS-2, without AI: clear days, explanatory statements, special resolutions, proxy, route map, e-voting.</p>}
      {error && <p className="text-sm text-accent-red">{(error as Error).message}</p>}
      {data && (
        <>
          <p className="text-xs flex gap-3">
            <span className="text-accent-red">{data.counts.missing ?? 0} missing</span>
            <span className="text-accent-amber">{data.counts.check ?? 0} to check</span>
            <span className="text-accent-green">{data.counts.ok ?? 0} in order</span>
          </p>
          <ul className="space-y-2">
            {data.findings.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm leading-5">
                <Status status={f.status} showLabel={false} />
                <div className="min-w-0">
                  <p>{f.item ? <span className="text-text-muted">Item {f.item}: </span> : null}{f.text}</p>
                  <p className="text-xs text-text-muted mt-0.5">
                    {f.basis && <span className="font-mono">{f.basis}</span>}
                    {f.page && <button className="ml-2 text-accent-brand hover:underline" onClick={() => goTo(f.page!)}>p.{f.page}</button>}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function FinancialsPanel({ doc }: { doc: DocumentFull }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const read = useMutation({
    mutationFn: () => aagam.readFinancials(doc.id),
    onSuccess: ({ statements }) => {
      queryClient.invalidateQueries({ queryKey: ["document", doc.id] });
      queryClient.invalidateQueries({ queryKey: ["financials"] });
      navigate(`/financials/${statements[0]}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const likely = ["financial_statements", "annual_report", "auditor_report"].includes(doc.doc_type);
  if (!doc.financials?.length && !likely) return null;
  return (
    <section className="card p-3 space-y-2">
      <p className="label flex items-center gap-1.5"><Landmark size={12} /> Financial statements</p>
      {doc.financials?.length ? (
        <ul className="space-y-1">
          {doc.financials.map((f) => (
            <li key={f.id}>
              <Link to={`/financials/${f.id}`} className="text-sm text-accent-brand hover:underline">
                {titleCase(f.basis)}{f.period_end ? `, year to ${day(f.period_end)}` : ""}: ratios and analysis
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <button className="btn text-xs py-1" onClick={() => read.mutate()} disabled={read.isPending}>
          {read.isPending ? <Loader2 size={12} className="animate-spin" /> : <Landmark size={12} />} Read the balance sheet and P&amp;L
        </button>
      )}
    </section>
  );
}

/** What the analysers made of this document, purpose by purpose: each with its items and key sentences. */
function InsightsPanel({ id, analyses, goTo }: { id: number; analyses?: DocInsight[]; goTo: (p: number) => void }) {
  const queryClient = useQueryClient();
  const again = useMutation({
    mutationFn: () => aagam.analyse(id),
    onSuccess: (out) => {
      queryClient.setQueryData(["doc-insights", id], out);
      queryClient.invalidateQueries({ queryKey: ["insights"] });
      toast.success(out.analyses.length ? `Analysed again: ${out.analyses.length} purpose${out.analyses.length === 1 ? "" : "s"} found.` : "Analysed again: nothing found.");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <>
      <div className="flex items-center gap-2 px-1">
        <p className="text-xs text-text-muted flex-1 leading-5">Read by rules, purpose by purpose. Click a page to see it.</p>
        <button className="btn py-0.5 px-2 text-xs" onClick={() => again.mutate()} disabled={again.isPending}>
          {again.isPending ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Analyse again
        </button>
      </div>
      {!analyses ? (
        <p className="text-sm text-text-muted px-1">Loading…</p>
      ) : analyses.length === 0 ? (
        <p className="text-sm text-text-muted px-1 leading-6">Nothing found on investments, legal matters, law cited, amendments, obligations or agreement terms. Documents are analysed as they come in; analyse again after correcting a page.</p>
      ) : (
        analyses.map((a) => <InsightCard key={a.kind} a={a} goTo={goTo} />)
      )}
    </>
  );
}

function InsightCard({ a, goTo }: { a: DocInsight; goTo: (p: number) => void }) {
  const [all, setAll] = useState(false);
  const shown = all ? a.items : a.items.slice(0, 6);
  const [first, ...rest] = a.columns;
  return (
    <section className="card p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-accent-brand"><KindIcon kind={a.kind} size={14} /></span>
        <Link to={`/insights/${a.kind}`} className="font-medium text-sm flex-1 hover:text-accent-brand">{a.title}</Link>
        <ScoreBar score={a.score} />
      </div>
      {a.summary && <p className="text-sm text-text-secondary leading-6">{a.summary}</p>}
      {a.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">{a.tags.slice(0, 6).map((t) => <TagBadge key={t} tag={t} />)}</div>
      )}
      {shown.length > 0 && (
        <ul className="divide-y divide-bg-border">
          {shown.map((item, i) => (
            <li key={i} className="py-1.5 text-sm flex gap-2 items-baseline" title={item.context ?? undefined}>
              <div className="min-w-0 flex-1">
                {first && <div className="font-medium"><Cell value={item[first.key]} type={first.type} compact /></div>}
                <p className="text-xs text-text-muted mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5">
                  {rest.filter((c) => item[c.key] !== null && item[c.key] !== undefined && item[c.key] !== "").slice(0, 4).map((c) => (
                    <span key={c.key} className="inline-flex gap-1 items-baseline min-w-0">
                      <span>{c.label}:</span>
                      <span className="text-text-secondary"><Cell value={item[c.key]} type={c.type} compact /></span>
                    </span>
                  ))}
                </p>
              </div>
              <span className="shrink-0 flex items-center gap-1.5">
                <Confidence value={item.confidence} showLabel={false} />
                {item.page ? <button className="text-xs text-accent-brand hover:underline" onClick={() => goTo(item.page!)}>p.{item.page}</button> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
      {a.items.length > 6 && (
        <button className="text-xs text-accent-brand hover:underline" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${a.items.length}`}</button>
      )}
      {a.highlights.length > 0 && (
        <div>
          <p className="label mb-1">Key sentences</p>
          <ul className="space-y-1">
            {a.highlights.slice(0, 4).map((h, i) => (
              <li key={i}>
                <button className="text-left text-xs text-text-secondary leading-5 hover:text-text-primary w-full" onClick={() => goTo(h.page)}>
                  <span className="line-clamp-3">“{h.text}”</span>
                  <span className="text-accent-brand">p.{h.page}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
