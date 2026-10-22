import { api, qs } from "./client";
import type {
  AiStatus, Analysis, ChecklistStep, CompanyFile, Dependents, DocInsight, Dossier, DocumentFull, DocumentRow, DueItem, EntityRow, Everything, FieldSpec,
  HiddenFact, InsightPurpose, InsightRegister, LoanCheck, Meta, Note, NoticeCheck, Overview, PartyRow, Precedent, PrecedentFull, RecordRow, SearchHit, Work, WorkRow,
} from "../types";

export interface LibraryFilter {
  company?: string;
  doc_type?: string;
  tag?: string;
  name?: string;
  year?: string;
  limit?: number;
  offset?: number;
}

export interface PrecedentFilter {
  q?: string;
  section?: string;
  topic?: string;
  kind?: string;
  min_crore?: number;
  max_crore?: number;
  with_statement?: boolean;
}

export interface UploadResult {
  document_id?: number;
  file?: string;
  error?: string;
  already_on_file?: boolean;
  doc_type?: string;
  title?: string | null;
}

export const aagam = {
  meta: () => api.get<Meta>("/meta"),
  overview: () => api.get<Overview>("/overview"),
  aiStatus: () => api.get<AiStatus>("/ai/status"),
  companies: (q = "") => api.get<{ companies: { id: number; name: string; cin: string | null }[] }>(`/companies${qs({ q })}`),
  due: (days = 60) => api.get<{ today: string; items: DueItem[] }>(`/due${qs({ days })}`),

  documents: (f: LibraryFilter = {}) => api.get<{ total: number; documents: DocumentRow[] }>(`/documents${qs({ ...f })}`),
  document: (id: number) => api.get<DocumentFull>(`/documents/${id}`),
  page: (id: number, page: number) => api.get<{ page_no: number; text: string; needs_vision: number }>(`/documents/${id}/pages/${page}`),
  pageImageUrl: (id: number, page: number) => `/api/documents/${id}/pages/${page}/image`,
  fileUrl: (id: number, download = false) => `/api/documents/${id}/file${download ? "?download=true" : ""}`,
  searchIn: (id: number, q: string) => api.get<{ pages: { page: number; text: string }[] }>(`/documents/${id}/search${qs({ q })}`),
  change: (id: number, body: { title?: string; doc_type?: string; company?: string; note?: string }) =>
    api.patch<DocumentFull>(`/documents/${id}`, body),
  tags: (id: number, add: string[] = [], remove: string[] = []) => api.post<DocumentFull>(`/documents/${id}/tags`, { add, remove }),
  saveSummary: (id: number, summary: string, key_points: string[] = []) =>
    api.put<DocumentFull>(`/documents/${id}/summary`, { summary, key_points }),
  summarise: (id: number) => api.post<{ queued: boolean; ai: AiStatus }>(`/documents/${id}/summarise`),
  reindex: (id: number) => api.post<DocumentFull>(`/documents/${id}/reindex`),
  upload: (files: File[], options: { company?: string; doc_type?: string; tags?: string[]; note?: string }) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (options.company) form.append("company", options.company);
    if (options.doc_type) form.append("doc_type", options.doc_type);
    if (options.tags?.length) form.append("tags", options.tags.join(","));
    if (options.note) form.append("note", options.note);
    return api.form<{ results: UploadResult[] }>("/documents", form);
  },
  inbox: () => api.post<{ results: UploadResult[] }>("/inbox"),

  search: (q: string, f: LibraryFilter = {}) =>
    api.get<{ query: string; documents: SearchHit[]; matching_documents: number }>(`/search${qs({ q, ...f })}`),
  allTags: () => api.get<{ tags: { name: string; kind: string; documents: number }[] }>("/tags"),

  precedents: (f: PrecedentFilter) => api.get<{ resolutions: Precedent[]; count: number }>(`/precedents${qs({ ...f })}`),
  precedent: (id: number) => api.get<PrecedentFull>(`/precedents/${id}`),
  topics: () => api.get<{ topics: { topic: string; resolutions: number }[] }>("/precedents/topics"),

  loanLimits: (body: Record<string, number | string | boolean | undefined>) => api.post<LoanCheck>("/checks/loan-limits", body),

  everything: (q: string) => api.get<Everything>(`/everything${qs({ q })}`),
  entities: (kind?: string, q = "") => api.get<{ entities: EntityRow[]; counts: Record<string, number>; total: number }>(`/entities${qs({ kind, q })}`),
  dossier: (kind: string, key: string) => api.get<Dossier>(`/entities/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`),

  financials: (company?: string) =>
    api.get<{ statements: { id: number; document_id: number | null; company_name: string | null; client: string | null; basis: string; period_end: string | null; unit: string | null; original_name: string | null }[] }>(`/financials${qs({ company })}`),
  analysis: (id: number) => api.get<Analysis>(`/financials/${id}`),
  correctLine: (id: number, key: string, current: number | null, previous: number | null) =>
    api.put<Analysis>(`/financials/${id}/lines/${key}`, { current, previous }),
  statementFacts: (id: number, facts: Record<string, unknown>) => api.put<Analysis>(`/financials/${id}/facts`, facts),
  s186Inputs: (id: number) => api.get<Record<string, number | null>>(`/financials/${id}/s186`),
  linkStatement: (id: number, company: string | null) => api.put<Analysis>(`/financials/${id}/company`, { company }),
  readFinancials: (documentId: number) => api.post<{ statements: number[] }>(`/documents/${documentId}/financials`),

  checkNotice: (documentId: number) => api.get<NoticeCheck>(`/documents/${documentId}/check`),

  // Insights: every document read purpose by purpose (investments, legal matters, law cited…), by rules.
  insightsOf: (documentId: number) => api.get<{ analyses: DocInsight[] }>(`/documents/${documentId}/analysis`),
  analyse: (documentId: number) => api.post<{ analyses: DocInsight[] }>(`/documents/${documentId}/analyse`),
  insights: () => api.get<{ purposes: InsightPurpose[] }>("/insights"),
  insightRegister: (kind: string, q = "", company = "") => api.get<InsightRegister>(`/insights/${encodeURIComponent(kind)}${qs({ q, company })}`),
  insightCsvUrl: (kind: string, q = "", company = "") => `/api/insights/${encodeURIComponent(kind)}${qs({ format: "csv", q, company })}`,

  workKinds: () => api.get<{ kinds: Record<string, string> }>("/work/kinds"),
  works: (status?: string, q = "") => api.get<{ works: WorkRow[] }>(`/work${qs({ status, q })}`),
  work: (id: number) => api.get<Work>(`/work/${id}`),
  createWork: (body: { title: string; kind: string; company?: string; due_on?: string; meeting_date?: string }) => api.post<Work>("/work", body),
  changeWork: (id: number, body: Record<string, unknown>) => api.patch<Work>(`/work/${id}`, body),
  setChecklist: (id: number, checklist: ChecklistStep[]) => api.put<Work>(`/work/${id}/checklist`, { checklist }),
  attach: (workId: number, documentId: number) => api.post<Work>(`/work/${workId}/documents/${documentId}`),
  detach: (workId: number, documentId: number) => api.del<Work>(`/work/${workId}/documents/${documentId}`),

  notes: (params: { target_kind?: string; target?: string; q?: string } = {}) => api.get<{ notes: Note[] }>(`/notes${qs(params)}`),
  addNote: (body: { text: string; target_kind?: string; target?: string; pinned?: boolean }) => api.post<Note>("/notes", body),
  changeNote: (id: number, body: { text?: string; pinned?: boolean }) => api.patch<Note>(`/notes/${id}`, body),
  deleteNote: (id: number) => api.del<{ deleted: number }>(`/notes/${id}`),

  // Her corrections and deletions.
  deleteDocument: (id: number) => api.del<{ deleted: number; name: string; file_kept_in: string | null; notes_kept: number }>(`/documents/${id}`),
  editPage: (id: number, page: number, text: string) => api.put<{ page_no: number; text: string; needs_vision: number }>(`/documents/${id}/pages/${page}`, { text }),
  editPrecedent: (id: number, changes: Record<string, unknown>) => api.patch<PrecedentFull>(`/precedents/${id}`, changes),
  deletePrecedent: (id: number) => api.del<{ deleted: number }>(`/precedents/${id}`),
  renameTag: (name: string, to: string) => api.put<{ tag: string; merged: boolean }>(`/tags/${encodeURIComponent(name)}`, { name: to }),
  deleteTag: (name: string) => api.del<{ deleted: string; documents: number }>(`/tags/${encodeURIComponent(name)}`),
  hideFact: (kind: string, value: string, documentId?: number) => api.post<{ id: number; removed: number }>("/facts/hide", { kind, value, document_id: documentId ?? null }),
  hidden: () => api.get<{ hidden: HiddenFact[] }>("/facts/hidden"),
  unhide: (id: number) => api.del<{ restored: number }>(`/facts/hidden/${id}`),
  renameEntity: (kind: string, key: string, name: string | null) => api.put<{ name: string | null }>(`/entities/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`, { name }),
  hideEntity: (kind: string, key: string) => api.del<{ removed: number }>(`/entities/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`),
  editStatement: (id: number, changes: Record<string, unknown>) => api.patch<Analysis>(`/financials/${id}`, changes),
  deleteStatement: (id: number) => api.del<{ deleted: number }>(`/financials/${id}`),
  deleteWork: (id: number) => api.del<{ deleted: number }>(`/work/${id}`),

  // The company file.
  schema: () => api.get<{ entities: Record<string, FieldSpec[]> }>("/records/schema"),
  companyFile: (id: number) => api.get<CompanyFile>(`/companies/${id}/file`),
  parties: (q = "") => api.get<{ parties: PartyRow[] }>(`/parties${qs({ q })}`),
  record: (entity: string, id: number) => api.get<RecordRow>(`/records/${entity}/${id}`),
  createRecord: (entity: string, data: Record<string, unknown>) => api.post<RecordRow>(`/records/${entity}`, { data }),
  changeRecord: (entity: string, id: number, data: Record<string, unknown>) => api.patch<RecordRow>(`/records/${entity}/${id}`, { data }),
  dependents: (entity: string, id: number) => api.get<Dependents>(`/records/${entity}/${id}/dependents`),
  deleteRecord: (entity: string, id: number) => api.del<Dependents>(`/records/${entity}/${id}`),
};
