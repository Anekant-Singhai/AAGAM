-- CS Desk company file: one SQLite database for all clients.
-- Columns mirror the input models in models.py (a test keeps them in step).
-- Every value written through the vault also gets a row in field_sources
-- saying where it came from: a document page and quote, or "she told us".
-- Dates are ISO text (YYYY-MM-DD); money is whole rupees.

CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL DEFAULT 'company' CHECK (entity_type IN ('company', 'llp')),
    cin TEXT UNIQUE,                          -- CIN for a company, LLPIN for an LLP
    name TEXT NOT NULL,
    company_class TEXT CHECK (company_class IN ('private', 'public', 'opc')),
    category TEXT,
    subcategory TEXT,
    is_listed INTEGER CHECK (is_listed IN (0, 1)),
    is_small_company INTEGER CHECK (is_small_company IN (0, 1)),
    is_section8 INTEGER CHECK (is_section8 IN (0, 1)),
    is_nbfc INTEGER CHECK (is_nbfc IN (0, 1)),
    status TEXT,
    date_of_incorporation TEXT,
    roc TEXT,
    nic_code TEXT,
    ro_line1 TEXT,
    ro_line2 TEXT,
    ro_city TEXT,
    ro_district TEXT,
    ro_state TEXT,
    ro_pin TEXT,
    email TEXT,
    phone TEXT,
    website TEXT,
    pan TEXT,
    tan TEXT,
    authorised_capital INTEGER,
    paid_up_capital INTEGER,
    fy_end TEXT,                              -- MM-DD; NULL means 03-31
    msme_return_applicable INTEGER CHECK (msme_return_applicable IN (0, 1)),
    dpt3_applicable INTEGER CHECK (dpt3_applicable IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- People and organisations: directors, KMP, auditors, audit firms, banks.
CREATE TABLE parties (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('individual', 'organisation')),
    name TEXT NOT NULL,
    father_name TEXT,
    dob TEXT,
    gender TEXT,
    nationality TEXT,
    occupation TEXT,
    din TEXT UNIQUE,
    pan TEXT UNIQUE,                          -- sensitive: masked in every reply
    aadhaar TEXT,                             -- sensitive
    passport_no TEXT,                         -- sensitive
    email TEXT,
    mobile TEXT,
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    district TEXT,
    state TEXT,
    pin TEXT,
    country TEXT,
    org_type TEXT,
    org_cin TEXT,
    frn TEXT,
    membership_no TEXT,
    professional_body TEXT,
    cop_no TEXT,
    kyc_next_due TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE meetings (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    kind TEXT NOT NULL CHECK (kind IN ('board', 'agm', 'egm', 'committee', 'postal_ballot')),
    committee TEXT,
    serial_no TEXT,
    date TEXT NOT NULL,
    time TEXT,
    venue TEXT,
    mode TEXT,
    fy TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE appointments (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    party_id INTEGER NOT NULL REFERENCES parties(id),
    role TEXT NOT NULL,
    category TEXT,
    date_of_appointment TEXT,
    date_of_cessation TEXT,
    cessation_reason TEXT,
    meeting_id INTEGER REFERENCES meetings(id),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE resolutions (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    meeting_id INTEGER REFERENCES meetings(id),
    kind TEXT NOT NULL CHECK (kind IN ('board', 'circular', 'ordinary', 'special')),
    subject TEXT NOT NULL,
    text TEXT,
    passed_on TEXT NOT NULL,
    section_ref TEXT,
    mgt14_required INTEGER CHECK (mgt14_required IN (0, 1)),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE auditor_appointments (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    auditor_id INTEGER NOT NULL REFERENCES parties(id),
    audit_type TEXT NOT NULL DEFAULT 'statutory',
    appointment_kind TEXT,
    appointed_on TEXT,
    meeting_id INTEGER REFERENCES meetings(id),
    from_fy TEXT,
    to_fy TEXT,
    ended_on TEXT,
    end_reason TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE charges (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    holder_id INTEGER REFERENCES parties(id),
    charge_id TEXT,
    amount INTEGER,
    created_on TEXT,
    modified_on TEXT,
    satisfied_on TEXT,
    property TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    kind TEXT NOT NULL,
    date TEXT NOT NULL,
    allotment_type TEXT,
    details TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE registrations (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    kind TEXT NOT NULL,
    number TEXT NOT NULL,
    state TEXT,
    status TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (kind, number)
);

CREATE TABLE filings (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    form TEXT NOT NULL,
    trigger TEXT,                             -- the due-date item it answers, e.g. meeting:12
    due_on TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN (
        'planned', 'in_progress', 'ready_for_review', 'submitted',
        'approved', 'resubmission', 'rejected', 'cancelled')),
    srn TEXT,
    filed_on TEXT,
    fees INTEGER,
    folder TEXT,                              -- evidence folder, relative to AAGAM_HOME
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    doc_type TEXT NOT NULL DEFAULT 'other',
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,                -- relative to AAGAM_HOME
    sha256 TEXT NOT NULL,
    media_type TEXT,
    pages INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE document_pages (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    needs_vision INTEGER NOT NULL DEFAULT 0,  -- 1 when the page has no text layer (a scan)
    PRIMARY KEY (document_id, page_no)
);

-- Provenance: one row per field per write.
CREATE TABLE field_sources (
    id INTEGER PRIMARY KEY,
    entity TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    field TEXT NOT NULL,
    value TEXT,                               -- as shown; sensitive values are masked here too
    source_kind TEXT NOT NULL CHECK (source_kind IN ('document', 'user', 'portal', 'derived', 'import')),
    document_id INTEGER REFERENCES documents(id),
    page INTEGER,
    quote TEXT,
    note TEXT,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE activity (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL DEFAULT (datetime('now')),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT
);

CREATE INDEX appointments_company ON appointments(company_id);
CREATE INDEX appointments_party ON appointments(party_id);
CREATE INDEX meetings_company ON meetings(company_id, kind, date);
CREATE INDEX filings_company ON filings(company_id, form, trigger);
CREATE INDEX documents_company ON documents(company_id, sha256);
CREATE INDEX field_sources_entity ON field_sources(entity, entity_id, field);
