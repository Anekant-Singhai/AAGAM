export interface Tag {
  name: string;
  added_by: string;
}

export interface DocumentRow {
  id: number;
  doc_type: string;
  original_name: string;
  pages: number;
  ingested_at: string;
  company_id: number | null;
  client: string | null;
  title: string | null;
  company_name: string | null;
  meeting_kind: string | null;
  meeting_date: string | null;
  has_summary: number;
  resolutions: number;
  tags: string[];
  media_type?: string | null;
  kind?: string | null;
  doc_date?: string | null;
  doc_date_basis?: string | null;
  fy?: string | null;
  source_folder?: string | null;
  folder_id?: number | null;
  client_why?: string | null;
}

/** One choice of a library filter, with how many documents it would show. */
export interface Facet {
  key: string | number | null;
  label?: string | null;
  documents: number;
}

export interface Facets {
  types: Facet[];
  clients: Facet[];
  fys: Facet[];
  folders: Facet[];
  inside: Facet[];
  kinds: Facet[];
}

export interface Folder {
  id: number;
  path: string;
  client_mode: "auto" | "one" | "none";
  company_id: number | null;
  client: string | null;
  doc_type: string | null;
  tags: string[];
  precedent: boolean;
  watch: boolean;
  status: "queued" | "running" | "done" | "stopped" | "failed";
  found: number;
  done: number;
  added: number;
  already: number;
  failed: number;
  skipped: Record<string, number> | null;
  current: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  documents: number;
  exists: boolean;
}

export interface FolderDetail extends Folder {
  failures: { rel_path: string; error: string | null }[];
  recent: { rel_path: string; status: string; document_id: number | null }[];
}

export interface FolderPreview {
  path: string;
  exists: boolean;
  files: number;
  by_kind: Record<string, number>;
  bytes: number;
  folders: number;
  skipped: Record<string, number>;
  too_big: number;
  sample: string[];
  truncated: boolean;
  already_added: number | null;
}

export interface TrashItem {
  id: number;
  kind: string;
  item_id: number;
  name: string;
  detail: string | null;
  deleted_at: string;
  size: number | null;
  file_missing: boolean;
}

export interface TrashList {
  items: TrashItem[];
  loose: { name: string; size: number; modified: string }[];
  bytes: number;
  count: number;
}

export interface UpdateState {
  checked_at: string | null;
  available: boolean;
  latest: { commit: string; date: string | null; version: string | null } | null;
  changes: { commit: string; date: string | null; message: string }[];
  status: "idle" | "checking" | "downloading" | "ready" | "applying" | "failed" | "done";
  error: string | null;
  needs_token: boolean;
  last_update: { at: string; from: string | null; to: string | null; ok: boolean; error: string | null; notes: string[] } | null;
}

export interface SystemInfo {
  version: string;
  commit: string | null;
  installed_at: string | null;
  app_folder: string | null;
  data_folder: string | null;
  mode: "archive" | "git" | "none";
  auto_update: boolean;
  repo: string | null;
  branch: string | null;
  has_token: boolean;
  updates: UpdateState;
}

export interface HealthCheck {
  key: string;
  label: string;
  status: "ok" | "warn" | "fail";
  detail: string;
  fix: string | null;
  action: string | null;
}

export interface SystemTask {
  task: string;
  status: "running" | "done" | "failed";
  log: string[];
}

export interface Fact {
  value: string;
  shown: string;
  detail: string | null;
  pages: number[];
  context: string;
}

export interface ResolutionRow {
  id: number;
  item_no: number;
  business: string | null;
  resolution_kind: string | null;
  title: string;
  sections: string[];
  topics: string[];
  max_amount: number | null;
  page_from: number;
  page_to: number;
  has_statement: number;
}

export interface DocumentFull {
  id: number;
  company_id: number | null;
  doc_type: string;
  original_name: string;
  media_type: string;
  pages: number;
  note: string | null;
  ingested_at: string;
  client: string | null;
  title: string | null;
  detected_type: string | null;
  detected_why: string | null;
  company_name: string | null;
  company_cin: string | null;
  meeting_kind: string | null;
  meeting_date: string | null;
  summary: string | null;
  summary_by: string | null;
  summary_at: string | null;
  key_points: string[];
  suggested_tags: string[];
  words: number;
  tags: Tag[];
  scanned_pages: number[];
  ocr_pages: number[];
  edited_pages: number[];
  overrides: Record<string, string | null>;
  facts: Record<string, Fact[]>;
  resolutions: ResolutionRow[];
  financials: { id: number; basis: string; period_end: string | null; unit: string | null }[];
  works?: { id: number; title: string; status: string }[];
  notes?: Note[];
  ai_jobs: { task: string; status: string; model: string | null; note: string | null; finished_at: string | null }[];
  doc_date?: string | null;
  doc_date_basis?: string | null;
  fy?: string | null;
  source_path?: string | null;
  source_folder?: string | null;
  folder_id?: number | null;
  folder_path?: string | null;
  file_modified?: string | null;
  client_why?: string | null;
}

export interface SearchHit {
  document_id: number;
  original_name: string;
  doc_type: string;
  title: string | null;
  company_name: string | null;
  pages: number[];
  passages: { page: number; text: string }[];
  tags: Tag[];
}

export interface Precedent {
  id: number;
  document_id: number;
  item_no: number;
  business: string | null;
  resolution_kind: string | null;
  title: string;
  sections: string[];
  topics: string[];
  max_amount: number | null;
  page_from: number;
  company_name: string | null;
  meeting_kind: string | null;
  meeting_date: string | null;
  has_statement: number;
  opening: string;
  original_name: string;
  client: string | null;
}

export interface PrecedentFull extends Precedent {
  body: string;
  statement: string | null;
  page_to: number;
}

export interface DueItem {
  company_id: number;
  company: string;
  form: string;
  title: string;
  due: string;
  state: string;
  days_left: number;
  basis: string;
  law: string;
  certainty: string;
  trigger: string;
}

export interface AiStatus {
  running: boolean;
  enabled?: boolean;
  model?: string;
  model_installed?: boolean;
  message: string;
  jobs?: Record<string, number>;
}

export interface Overview {
  stats: {
    documents: number;
    pages: number;
    resolutions: number;
    companies: number;
    summaries: number;
    ai_queue: number;
    by_type: { doc_type: string; documents: number }[];
    financials: number;
  };
  due: DueItem[];
  due_count: number;
  recent: DocumentRow[];
  ai: AiStatus;
  works: WorkRow[];
  works_open: number;
  pinned: Note[];
}

export interface LimitResult {
  section: string;
  limit?: number;
  limit_text?: string;
  total?: number;
  status: string;
  needs?: string;
  steps?: string[];
  notes: string[];
  basis: string[];
}

export interface LoanCheck {
  figures: Record<string, string>;
  s186: LimitResult;
  s180?: LimitResult;
  s185?: LimitResult;
  caution: string;
}

export interface Note {
  id: number;
  target_kind: string;
  target: string;
  text: string;
  pinned: number;
  by: string;
  created_at: string;
  updated_at: string;
  snippet?: string;
}

export interface ChecklistStep {
  text: string;
  basis: string | null;
  done: boolean;
  done_at: string | null;
  note: string | null;
}

export interface WorkRow {
  id: number;
  title: string;
  kind: string;
  kind_label: string;
  company_id: number | null;
  company: string | null;
  status: string;
  due_on: string | null;
  meeting_date: string | null;
  fy: string | null;
  updated_at: string;
  closed_at: string | null;
  documents: number;
  progress: { done: number; total: number };
}

export interface Work extends Omit<WorkRow, "documents"> {
  checklist: ChecklistStep[];
  documents: { id: number; original_name: string; doc_type: string; title: string | null }[];
  notes: Note[];
  created_at: string;
}

export interface FinancialItem {
  key: string;
  label: string;
  statement: "bs" | "pl";
  group: string;
  found: boolean;
  current: number | null;
  previous: number | null;
  page: number | null;
  as_written?: string;
  by: string | null;
  repaired?: Record<string, number>;
}

export interface Ratio {
  key: string;
  name: string;
  formula: string;
  unit: string;
  current: number | null;
  previous: number | null;
  change_pct: number | null;
  explain: boolean;
  missing: string | null;
}

export interface Applies {
  key: string;
  title: string;
  status: string;
  why: string;
  basis: string;
  work: string | null;
  missing: string | null;
}

export interface Analysis {
  statement: {
    id: number; document_id: number | null; company_id: number | null; company_name: string | null; client: string | null;
    basis: string; period_end: string | null; prior_period_end: string | null; unit: string | null; unit_factor: number; original_name: string | null;
  };
  items: FinancialItem[];
  ratios: Ratio[];
  derived: { current: Record<string, number | null>; previous: Record<string, number | null> };
  liabilities: { total?: number; parts?: { name: string; amount: number; share: number }[]; msme_share_of_payables?: number | null };
  checks: { level: string; text: string }[];
  applicability: Applies[];
  facts: Record<string, unknown>;
  class_from_cin?: string;
}

export interface EntityRow {
  kind: string;
  key: string;
  name: string;
  detail: string | null;
  documents: number;
  mentions: number;
}

export interface Dossier {
  kind: string;
  key: string;
  name: string;
  chosen_name: string | null;
  spellings: string[];
  documents: { document_id: number; title: string; doc_type: string; meeting_date: string | null; added: string; pages: number[]; contexts: { page: number; text: string }[] }[];
  identifiers: Record<string, string[]>;
  company_file: { type: string; id: number; name: string; din?: string; cin?: string; appointments?: { company: string; role: string; date_of_appointment: string | null; date_of_cessation: string | null }[]; matched_by?: string }[];
  appears_with: { kind: string; key: string; name: string; detail: string | null; documents: number }[];
  resolutions?: { id: number; document_id: number; item_no: number; title: string; resolution_kind: string | null; sections: string; max_amount: number | null; meeting_date: string | null }[];
  financials?: { id: number; basis: string; period_end: string | null }[];
  gstin?: { gstin: string; state_code: string; state: string; pan: string; pan_holder: string; registration_no: string; verify_url: string; note: string };
  cin?: { listed: boolean; state: string; state_code: string; year: number; ownership: string | null; company_class: string | null; nic_code: string; registration_no: string };
}

export interface NoticeCheck {
  document_id: number;
  meeting_kind: string | null;
  notice_date: string | null;
  findings: { status: string; text: string; basis: string | null; page: number | null; item: number | null }[];
  counts: Record<string, number>;
}

export interface Everything {
  query: string;
  documents: SearchHit[];
  document_count: number;
  resolutions: Precedent[];
  entities: EntityRow[];
  companies: { id: number; name: string; cin: string | null }[];
  people: { id: number; name: string; din: string | null }[];
  financials: { id: number; company_name: string | null; client: string | null; period_end: string | null; basis: string }[];
  notes: Note[];
  works: WorkRow[];
  looks_like: string | null;
}

export interface HiddenFact {
  id: number;
  kind: string;
  key: string;
  shown: string | null;
  document_id: number | null;
  document: string | null;
  created_at: string;
}

export interface FieldSpec {
  name: string;
  type: "string" | "integer" | "boolean" | "number";
  enum: string[] | null;
  description: string | null;
  required: boolean;
  sensitive: boolean;
}

export type RecordRow = Record<string, unknown> & { id: number; sources?: Record<string, FieldSource> };

export interface FieldSource {
  value: string | null;
  source_kind: string;
  document_id: number | null;
  page: number | null;
  quote: string | null;
  note: string | null;
  recorded_by: string;
  recorded_at: string;
}

export interface PartyRow {
  id: number;
  kind: string;
  name: string;
  din: string | null;
  pan: string | null;
  org_type: string | null;
  frn: string | null;
  membership_no: string | null;
}

export interface CompanyFile {
  company: RecordRow;
  people: (Record<string, unknown> & { appointment_id: number; party_id: number; name: string; role: string; din: string | null })[];
  auditors: RecordRow[];
  meetings: RecordRow[];
  resolutions: RecordRow[];
  charges: RecordRow[];
  events: RecordRow[];
  registrations: RecordRow[];
  filings: RecordRow[];
  documents: { doc_type: string; count: number }[];
  sources: Record<string, FieldSource>;
  library: { documents: number; works: number; financials: { id: number; basis: string; period_end: string | null }[] };
  due: DueItem[];
}

export interface Dependents {
  entity: string;
  id: number;
  deletes: Record<string, number>;
  unlinks: Record<string, number>;
}

export interface Meta {
  version: string;
  doc_types: Record<string, string>;
  data_folder: string;
  inbox: string;
  file_kinds?: Record<string, string>;
}

const COLOURS = 6;

export function tagClass(tag: string): string {
  if (tag === "precedent") return "tag-precedent";
  if (/^s\.\d/.test(tag)) return "tag-section";
  let hash = 0;
  for (const ch of tag) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `tag-${hash % COLOURS}`;
}

export const FACT_LABELS: Record<string, string> = {
  cin: "CIN",
  llpin: "LLPIN",
  din: "DIN",
  pan: "PAN",
  gstin: "GSTIN",
  person: "People",
  company: "Companies",
  amount: "Amounts",
  date: "Dates",
  section: "Sections",
  regulation: "Regulations",
  frn: "Firm registration no.",
  membership_no: "Membership no.",
  email: "Email",
};

export const FACT_ORDER = ["company", "cin", "din", "person", "amount", "date", "section", "regulation", "frn", "membership_no", "gstin", "pan", "llpin", "email"];

// ------------------------------------------------------------------ Insights: documents read purpose by purpose

export type InsightKind = "investments" | "legal" | "law" | "amendments" | "obligations" | "agreements";
export type ColumnType = "text" | "money" | "date" | "number" | "list" | "long";

export interface InsightColumn {
  key: string;
  label: string;
  type: ColumnType;
}

/** One thing an analyser found: the purpose's column values, with where it came from. */
export interface InsightItem {
  page?: number | null;
  context?: string | null;
  confidence?: number | null;
  [key: string]: unknown;
}

/** An item in a register across the library: with its document. */
export interface RegisterItem extends InsightItem {
  document_id: number;
  document: string | null;
  doc_type: string;
  company: string | null;
}

/** What one analyser made of one document. */
export interface DocInsight {
  kind: InsightKind | string;
  title: string;
  columns: InsightColumn[];
  items: InsightItem[];
  score: number;
  summary: string;
  tags: string[];
  highlights: { page: number; text: string; score: number }[];
  facts: Record<string, unknown>;
}

export interface InsightPurpose {
  kind: InsightKind | string;
  title: string;
  columns: InsightColumn[];
  about: string;
  documents: number;
  items: number;
}

export interface InsightRegister {
  kind: InsightKind | string;
  title: string;
  columns: InsightColumn[];
  count: number;
  items: RegisterItem[];
}
