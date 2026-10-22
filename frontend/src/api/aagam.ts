import { api, qs } from "./client";
import type {
  AiStatus, Analysis, ChecklistStep, CompanyFile, Dependents, DocInsight, Dossier, DocumentFull, DocumentRow, DueItem, EntityRow, Everything, Facets, FieldSpec,
  Folder, FolderDetail, FolderPreview, HealthCheck, HiddenFact, InsightPurpose, InsightRegister, LoanCheck, Meta, Note, NoticeCheck, Overview, PartyRow,
  Precedent, PrecedentFull, RecordRow, SearchHit, SystemInfo, SystemTask, TrashList, UpdateState, Work, WorkRow,
} from "../types";

export interface LibraryFilter {
  company?: string;
  doc_type?: string;
  tag?: string;
  name?: string;
  year?: string;
  fy?: string;
  date_from?: string;
  date_to?: string;
  folder?: string;
  within?: string;
  kind?: string;
  /** "true" or "false" as text, so that "only documents without scans" survives the query string. */
  scanned?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

/** A file to add, with where it sat inside a folder she dropped ("Acme/2024-25/notice.pdf"), or "" for a loose file. */
export interface UploadItem {
  file: File;
  path: string;
}

/** A moment as this computer's clock shows it (YYYY-MM-DDTHH:MM:SS), as AAGAM keeps a file's own dates. */
function localTime(ms: number): string {
  const d = new Date(ms);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}T${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
}

export interface FolderOptions {
  path: string;
  company: string;
  doc_type: string;
  tags: string[];
  precedent: boolean;
  watch: boolean;
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
  client?: string | null;
}

export const aagam = {
  meta: () => api.get<Meta>("/meta"),
  overview: () => api.get<Overview>("/overview"),
  aiStatus: () => api.get<AiStatus>("/ai/status"),
  companies: (q = "") => api.get<{ companies: { id: number; name: string; cin: string | null }[] }>(`/companies${qs({ q })}`),
  due: (days = 60) => api.get<{ today: string; items: DueItem[] }>(`/due${qs({ days })}`),

  documents: (f: LibraryFilter = {}) => api.get<{ total: number; documents: DocumentRow[] }>(`/documents${qs({ ...f })}`),
  facets: (f: LibraryFilter = {}) => api.get<Facets>(`/documents/facets${qs({ ...f })}`),
  document: (id: number) => api.get<DocumentFull>(`/documents/${id}`),
  page: (id: number, page: number) => api.get<{ page_no: number; text: string; needs_vision: number }>(`/documents/${id}/pages/${page}`),
  pageImageUrl: (id: number, page: number) => `/api/documents/${id}/pages/${page}/image`,
  fileUrl: (id: number, download = false) => `/api/documents/${id}/file${download ? "?download=true" : ""}`,
  searchIn: (id: number, q: string) => api.get<{ pages: { page: number; text: string }[] }>(`/documents/${id}/search${qs({ q })}`),
  change: (id: number, body: {
    title?: string; doc_type?: string; company?: string; note?: string; doc_date?: string; company_name?: string; meeting_kind?: string; meeting_date?: string;
  }) =>
    api.patch<DocumentFull>(`/documents/${id}`, body),
  tags: (id: number, add: string[] = [], remove: string[] = []) => api.post<DocumentFull>(`/documents/${id}/tags`, { add, remove }),
  saveSummary: (id: number, summary: string, key_points: string[] = []) =>
    api.put<DocumentFull>(`/documents/${id}/summary`, { summary, key_points }),
  summarise: (id: number) => api.post<{ queued: boolean; ai: AiStatus }>(`/documents/${id}/summarise`),
  reindex: (id: number) => api.post<DocumentFull>(`/documents/${id}/reindex`),
  upload: (items: UploadItem[], options: { company?: string; doc_type?: string; tags?: string[]; note?: string }) => {
    const form = new FormData();
    items.forEach(({ file, path }) => {
      form.append("files", file);
      // One of each per file, in the same order, so the server can tell which folder each came from.
      form.append("paths", path);
      form.append("modified", file.lastModified ? localTime(file.lastModified) : "");
    });
    if (options.company) form.append("company", options.company);
    if (options.doc_type) form.append("doc_type", options.doc_type);
    if (options.tags?.length) form.append("tags", options.tags.join(","));
    if (options.note) form.append("note", options.note);
    return api.form<{ results: UploadResult[] }>("/documents", form);
  },
  inbox: () => api.post<{ results: UploadResult[] }>("/inbox"),

  // Folders on her computer, read in the background (and watched for new files, if she likes).
  folders: () => api.get<{ folders: Folder[] }>("/folders"),
  folder: (id: number) => api.get<FolderDetail>(`/folders/${id}`),
  previewFolder: (path: string) => api.post<FolderPreview>("/folders/preview", { path }),
  addFolder: (options: FolderOptions) => api.post<Folder>("/folders", options),
  changeFolder: (id: number, body: Partial<Omit<FolderOptions, "path">>) => api.patch<Folder>(`/folders/${id}`, body),
  scanFolder: (id: number) => api.post<Folder>(`/folders/${id}/scan`),
  stopFolder: (id: number) => api.post<Folder>(`/folders/${id}/stop`),
  forgetFolder: (id: number, documents: "keep" | "trash") => api.del<{ forgotten: number; documents_trashed: number }>(`/folders/${id}${qs({ documents })}`),
  browseFolder: () => api.post<{ path: string | null }>("/folders/browse"),

  // The Trash.
  trash: () => api.get<TrashList>("/trash"),
  trashDocuments: (ids: number[]) => api.post<{ trashed: number[]; failed: { id: number; error: string }[] }>("/documents/trash", { ids }),
  restore: (trashId: number) => api.post<{ document_id: number; name: string }>(`/trash/${trashId}/restore`),
  deleteForever: (trashId: number) => api.del<{ deleted: number }>(`/trash/${trashId}`),
  emptyTrash: () => api.post<{ deleted: number; files: number }>("/trash/empty"),
  restoreLoose: (name: string) => api.post<{ document_id: number }>("/trash/loose/restore", { name }),
  deleteLoose: (name: string) => api.del<{ deleted: string }>(`/trash/loose${qs({ name })}`),

  // This copy of AAGAM and this computer: updates, health, repairs, uninstalling.
  system: () => api.get<SystemInfo>("/system"),
  checkUpdates: () => api.post<UpdateState>("/system/updates/check"),
  applyUpdate: () => api.post<{ started: boolean }>("/system/updates/apply"),
  updateSettings: (body: { auto_update?: boolean; repo?: string; branch?: string; token?: string | null }) => api.put<SystemInfo>("/system/updates/settings", body),
  health: () => api.get<{ checks: HealthCheck[] }>("/system/health"),
  repair: (action: string) => api.post<{ started: boolean; task: string }>(`/system/repair/${encodeURIComponent(action)}`),
  task: (task: string) => api.get<SystemTask>(`/system/tasks/${encodeURIComponent(task)}`),
  uninstall: (removeData: boolean, confirm: string) => api.post<{ started: boolean }>("/system/uninstall", { remove_data: removeData, confirm }),
  backup: (into?: string) => api.post<{ started: boolean; task: string }>("/system/backup", into ? { into } : {}),
  job: (task: string) => api.get<{ task: string; status: "running" | "done" | "failed"; path: string | null; files: number; bytes: number; error: string | null }>(`/system/jobs/${encodeURIComponent(task)}`),
  supportReport: (into?: string) => api.post<{ path: string; bytes: number }>("/system/support", into ? { into } : {}),
  reveal: (path: string) => api.post<{ shown: boolean }>("/system/reveal", { path }),

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
  deleteDocument: (id: number) =>
    api.del<{ deleted: number; name: string; file_kept_in: string | null; notes_kept: number; trash_id?: number | null }>(`/documents/${id}`),
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
