-- AAGAM library tables, added to the same SQLite database as the company file
-- (csdesk/vault/schema.sql). Documents and their pages are the core's
-- `documents` and `document_pages`; everything here hangs off them.

CREATE TABLE IF NOT EXISTS aagam_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- What AAGAM has worked out about a document. One row per document.
CREATE TABLE IF NOT EXISTS doc_meta (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT,
    detected_type TEXT,                 -- from the text; documents.doc_type holds what she set
    detected_why TEXT,                  -- the words that decided it
    company_name TEXT,                  -- the company the document is about, as written in it
    company_cin TEXT,
    meeting_kind TEXT,                  -- for notices and minutes: agm, egm, board, ...
    meeting_date TEXT,
    summary TEXT,
    summary_by TEXT,                    -- 'her', 'claude', 'local:<model>'
    summary_at TEXT,
    key_points TEXT,                    -- JSON list
    suggested_tags TEXT,                -- JSON list from AI; she accepts them into tags
    ocr_pages TEXT,                     -- "2,3": pages whose text was read by OCR from a scan
    edited_pages TEXT,                  -- "4": pages whose text she corrected; kept as hers
    overrides TEXT,                     -- JSON: what she set (company_name, meeting_kind, meeting_date) over what was read
    removed_tags TEXT,                  -- JSON list: automatic tags she took off; not put back on re-reading
    words INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'indexed', 'failed')),
    error TEXT,
    indexed_at TEXT,
    doc_date TEXT,                      -- the date the document is of: its meeting, its accounts, its "Date:" line, ...
    doc_date_basis TEXT,                -- how that date was found, in words
    source_path TEXT,                   -- where the file was on her computer, when known
    source_folder TEXT,                 -- its folder within the folder brought in: "Acme/2024-25/AGM" ('' at the top)
    folder_id INTEGER,                  -- folders.id it came from
    file_modified TEXT,                 -- when the file itself last changed
    client_why TEXT                     -- how its client was worked out: "its CIN ...", "the folder “Acme”", "set by her"
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    kind TEXT NOT NULL DEFAULT 'topic'  -- topic, section, client, status, ...
);

CREATE TABLE IF NOT EXISTS document_tags (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    added_by TEXT NOT NULL DEFAULT 'her', -- 'her', 'auto', 'claude', 'local:<model>'
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (document_id, tag_id)
);

-- Facts found in the text: CINs, DINs, amounts, dates, section references...
-- PAN and Aadhaar are stored masked; the page text still has them.
CREATE TABLE IF NOT EXISTS mentions (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,                -- normalised: ISO date, rupees as an integer, CIN upper case
    shown TEXT NOT NULL,                -- as written (masked when sensitive)
    detail TEXT,                        -- e.g. the person a DIN belongs to
    context TEXT
);

-- Resolutions split out of notices (and later minutes and board resolutions).
-- This is the precedent library.
CREATE TABLE IF NOT EXISTS clauses (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'resolution',
    item_no INTEGER,
    business TEXT,                      -- 'ordinary' or 'special' business of the meeting
    resolution_kind TEXT,               -- 'ordinary', 'special', 'board' or NULL when not stated
    title TEXT NOT NULL,
    body TEXT NOT NULL,                 -- the resolution itself ("RESOLVED THAT ...")
    statement TEXT,                     -- its explanatory statement, if the notice has one
    sections TEXT,                      -- " 185 186(3) " (space-separated, padded for LIKE matching)
    topics TEXT,                        -- " loans-investments related-party "
    max_amount INTEGER,                 -- the largest rupee amount in the resolution
    page_from INTEGER,
    page_to INTEGER,
    company_name TEXT,
    meeting_kind TEXT,
    meeting_date TEXT
);

-- Figures from a balance sheet and statement of profit and loss, in whole rupees.
CREATE TABLE IF NOT EXISTS financials (
    id INTEGER PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id),
    company_name TEXT,
    basis TEXT NOT NULL DEFAULT 'standalone',  -- standalone or consolidated
    period_end TEXT,                    -- the year the "current" column is for
    prior_period_end TEXT,
    unit TEXT,                          -- as printed: "₹ in lakhs"
    unit_factor INTEGER NOT NULL DEFAULT 1,
    items TEXT NOT NULL,                -- JSON {key: {label, current, previous, page, by}}
    facts TEXT,                         -- JSON: what isn't in the figures (listed, bank borrowings, ...)
    overrides TEXT,                     -- JSON: header fields she corrected (period, basis, unit, company name)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS financials_document ON financials(document_id);
CREATE INDEX IF NOT EXISTS financials_company ON financials(company_id);

-- Her notes, on anything: a document, a company, a person, a piece of work, a resolution, or on their own.
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    target_kind TEXT NOT NULL DEFAULT 'general'
        CHECK (target_kind IN ('general', 'document', 'company', 'entity', 'work', 'resolution', 'financials')),
    target TEXT NOT NULL DEFAULT '',    -- "12" for document 12, "person:asha rao" for an entity
    text TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    by TEXT NOT NULL DEFAULT 'her',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS notes_target ON notes(target_kind, target);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(text, content='notes', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE OF text ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text);
END;

-- The work register: each job she does (an AGM, a director's appointment, an annual filing, a due diligence),
-- with its checklist, documents, notes and status. Finished work stays here, so past work can be found again.
CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    company_id INTEGER REFERENCES companies(id),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'waiting', 'done', 'dropped')),
    due_on TEXT,
    meeting_date TEXT,
    fy TEXT,
    checklist TEXT NOT NULL DEFAULT '[]',  -- JSON [{text, basis, done, done_at, note}]
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS work_documents (
    work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (work_id, document_id)
);
CREATE INDEX IF NOT EXISTS works_company ON works(company_id, status);

CREATE TABLE IF NOT EXISTS ai_jobs (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    task TEXT NOT NULL,                 -- 'summary'
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped')),
    provider TEXT,
    model TEXT,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT
);

-- Full-text search over page text and over resolutions. External-content
-- tables: the text lives once, in document_pages / clauses, and triggers keep
-- the index in step however a page is written.
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    text, content='document_pages', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS pages_fts_insert AFTER INSERT ON document_pages BEGIN
    INSERT INTO pages_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS pages_fts_delete AFTER DELETE ON document_pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS pages_fts_update AFTER UPDATE OF text ON document_pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO pages_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS clauses_fts USING fts5(
    title, body, statement, content='clauses', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS clauses_fts_insert AFTER INSERT ON clauses BEGIN
    INSERT INTO clauses_fts(rowid, title, body, statement) VALUES (new.id, new.title, new.body, coalesce(new.statement, ''));
END;
CREATE TRIGGER IF NOT EXISTS clauses_fts_delete AFTER DELETE ON clauses BEGIN
    INSERT INTO clauses_fts(clauses_fts, rowid, title, body, statement)
        VALUES ('delete', old.id, old.title, old.body, coalesce(old.statement, ''));
END;

CREATE TRIGGER IF NOT EXISTS clauses_fts_update AFTER UPDATE OF title, body, statement ON clauses BEGIN
    INSERT INTO clauses_fts(clauses_fts, rowid, title, body, statement)
        VALUES ('delete', old.id, old.title, old.body, coalesce(old.statement, ''));
    INSERT INTO clauses_fts(rowid, title, body, statement) VALUES (new.id, new.title, new.body, coalesce(new.statement, ''));
END;

-- Her corrections, kept apart from what is read so that re-reading a document doesn't undo them.
-- A resolution she edited or deleted, by its document and item number.
CREATE TABLE IF NOT EXISTS clause_edits (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    item_no INTEGER NOT NULL,
    changes TEXT NOT NULL DEFAULT '{}', -- JSON of the fields she changed
    deleted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (document_id, item_no)
);
-- Facts that aren't: a name read wrongly, a table heading taken for a company. In one document, or everywhere.
CREATE TABLE IF NOT EXISTS hidden_facts (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,                  -- entities.key_of(kind, value)
    shown TEXT,                         -- as it was written, to list it again
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS hidden_facts_kind ON hidden_facts(kind, key);
-- The name she wants a person or company shown under.
CREATE TABLE IF NOT EXISTS entity_names (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
-- Tags she renamed (becomes the new name) or deleted (becomes NULL): automatic tagging follows them.
CREATE TABLE IF NOT EXISTS tag_rules (
    name TEXT PRIMARY KEY COLLATE NOCASE,
    becomes TEXT
);
-- Statements she deleted, so that re-reading the document doesn't bring them back.
CREATE TABLE IF NOT EXISTS dismissed_financials (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    basis TEXT NOT NULL,
    PRIMARY KEY (document_id, basis)
);

-- What each document says, purpose by purpose (aagam/analysis): investments, legal matters, law cited, amendments,
-- obligations, agreement terms. Rebuilt whenever the document is read.
CREATE TABLE IF NOT EXISTS analyses (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    summary TEXT,
    result TEXT NOT NULL,                -- JSON: {kind, title, columns, items, score, summary, tags, highlights, facts}
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (document_id, kind)
);

-- Folders on her computer brought into the library, once or watched for new files. Her files stay where they
-- are: each one is copied in and read like any other document. A pass over a folder runs in the background,
-- file by file, and its progress is kept here.
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- as she chose it (Windows paths ignore case)
    client_mode TEXT NOT NULL DEFAULT 'auto' CHECK (client_mode IN ('auto', 'one', 'none')),  -- worked out per file, all one client's, or no client's
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,  -- the client, when client_mode is 'one'
    doc_type TEXT,                              -- NULL: worked out per file
    tags TEXT NOT NULL DEFAULT '[]',            -- JSON: put on every document from here
    precedent INTEGER NOT NULL DEFAULT 0 CHECK (precedent IN (0, 1)),  -- other companies' documents: no client is worked out
    watch INTEGER NOT NULL DEFAULT 0 CHECK (watch IN (0, 1)),          -- look again for new files while AAGAM is open
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'stopped', 'failed')),
    found INTEGER NOT NULL DEFAULT 0,           -- files to read in this pass
    done INTEGER NOT NULL DEFAULT 0,
    added INTEGER NOT NULL DEFAULT 0,
    already INTEGER NOT NULL DEFAULT 0,         -- the same file was already in the library
    failed INTEGER NOT NULL DEFAULT 0,
    skipped TEXT,                               -- JSON {".doc": 12}: files AAGAM can't read yet
    current TEXT,                               -- the file being read now
    error TEXT,
    worker TEXT,                                -- who is reading it: "web:<pid>" or "mcp:<pid>"
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    heartbeat TEXT,                             -- touched after every file, so a pass left by a closed AAGAM is taken up again
    finished_at TEXT
);
-- Every file seen in a folder, so the next pass reads only what is new or changed, and a document she deleted
-- isn't brought back.
CREATE TABLE IF NOT EXISTS folder_files (
    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    rel_path TEXT NOT NULL COLLATE NOCASE,
    size INTEGER NOT NULL,
    modified TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('added', 'already', 'failed')),
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    error TEXT,
    seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (folder_id, rel_path)
);

-- The Trash: documents she deleted, each with what it takes to put it back as it was (trash.py).
CREATE TABLE IF NOT EXISTS trash (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'document',
    item_id INTEGER NOT NULL,                   -- its id before it was deleted
    name TEXT NOT NULL,
    detail TEXT,                                -- what the Trash lists it with: type, pages, client
    file TEXT,                                  -- the file, in the bin folder (relative to AAGAM_HOME)
    size INTEGER,
    payload TEXT NOT NULL,                      -- JSON: the rows to put back
    deleted_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_by TEXT
);

CREATE INDEX IF NOT EXISTS mentions_document ON mentions(document_id, page_no);
CREATE INDEX IF NOT EXISTS mentions_value ON mentions(kind, value);
CREATE INDEX IF NOT EXISTS clauses_document ON clauses(document_id);
CREATE INDEX IF NOT EXISTS document_tags_tag ON document_tags(tag_id);
CREATE INDEX IF NOT EXISTS ai_jobs_status ON ai_jobs(status, task);
