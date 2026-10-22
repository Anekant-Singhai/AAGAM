# AAGAM: the map

AAGAM is a Company Secretary's workbench that runs on her own laptop. It holds her documents and her clients' records, reads what comes in, finds things, works out dates and limits, drafts, and fills MCA forms up to the point where she signs. This page maps the whole of a CS's work to the parts of AAGAM, shows what is built, and sets out what comes next.

**Status on 18 October 2026:** built and tested (255 tests). The tests include three real listed-company AGM notices, a real set of scanned audited statements (J. Kumar-NCC), the real local model, and the interface in a browser. `scripts\setup-windows.cmd` has been run on a clean copy and ends with `aagam doctor` passing. CS Desk, built earlier, is now AAGAM's core (`src/csdesk`). [CSDESK.md](CSDESK.md) covers its parts in detail.

## How AAGAM works with her

| Who | Does what | How |
|---|---|---|
| She | Reads, decides, signs, submits | The AAGAM window (`http://127.0.0.1:8765`), Claude Desktop, and the CS Desk browser for MCA |
| AAGAM's rules | Document type, facts (CIN, DIN with the person, PAN masked, amounts, dates, sections), splitting notices into resolutions, due dates, limits | Instantly, on every document, on any laptop |
| Local AI (Ollama, on her laptop) | A summary and suggested tags for each document | In the background; documents never leave the laptop |
| Claude (Claude Desktop) | Drafting, legal reading, reading scans, checking a draft against the Act, filling forms | The same library and company file, through AAGAM's 59 tools |

Rules do what has to be exactly right. Local AI does the routine reading. Claude does the judgment. She signs.

## Everything a CS does, and where it lives

| Her work | AAGAM | State |
|---|---|---|
| **Client records:** companies, LLPs, directors, KMP, capital, auditors, charges | Company file (`csdesk/vault`), where every value records its source. **Clients** in the window shows and changes all of it: details, directors and KMP (positions and the people), meetings, resolutions, filings, charges, registrations, auditors and events, each added, changed or deleted in place | Built |
| **Documents:** keeping, finding, tagging, reading | Library: PDF, Word, Excel (.xlsx and .xls), PowerPoint, Outlook (.msg and .eml), RTF, HTML, XML, JSON and text. Scans are read by Windows OCR (up to five pages straight away, longer ones in the background). Type detected, facts found, full-text search, search within a document, tags, summaries, a drop-in inbox, filters by name, year, type, client and tag. Page images are cached | Built |
| **Search everything** | One box (Ctrl+K anywhere) over pages, resolutions, people and companies, the company file, statements, work and notes. A CIN, GSTIN or DIN typed in is recognised and opens its dossier | Built |
| **People and companies** | Every person, company, DIN, CIN, GSTIN, audit firm, member and email named in the library, grouped however it was written. Each has a dossier: every document and page with the words around it, identifiers, company-file records and appointments, who they appear with, resolutions and statements. GSTINs and CINs are decoded | Built |
| **Financial statements (with CAs)** | Reads the Schedule III balance sheet and P&L from any statements in the library (text or scanned), in their unit (lakhs, crore, thousands), with the page of each line. The 11 Schedule III ratios with the change from last year and a flag over 25%; where the money comes from; checks that the totals add up; what the figures make apply (small company, CSR, secretarial audit, internal audit, whole-time CS, independent directors, woman director, XBRL, CARO, tax audit, MSME-1, DPT-3), each with its basis and the work it brings. She can correct any line, and her figures are kept. The figures fill the s.186 calculator | Built |
| **Reading for a purpose (Insights)** | Every document is read, with rules and no AI, for six purposes; each finding keeps its page and sentence, and each purpose is a register across the library (searchable, by client, downloadable as CSV). **Investments**: loans, investments, guarantees and security (s.185/186), investee, instrument, amount, shares, approval, the s.186(3) limit; notes to accounts and MBP-2 tables too. **Legal matters**: forum and bench, case number, parties, nature (IBC s.7/9/10, ss.241-242, s.454 adjudication, tax, GST, s.138 NI Act…), sections, status, amount at stake, next date. **Law cited**: Acts, sections, rules, regulations, G.S.R./S.O. notifications, MCA and SEBI circulars, Secretarial Standards, Ind AS, case citations, each tied to its Act. **Amendments**: the instrument amended, notification and dates (retrospective flagged), each substitution, insertion or omission with its provision and new words. **Obligations and deadlines**: who must do what by when, due dates worked out where they can be. **Agreement terms**: parties, dates, term, amount, interest, governing law, jurisdiction, arbitration, termination and the rest | Built |
| **Checking a notice** | Without AI: 21 clear days, an explanatory statement for every special item with the directors' interest, special resolutions where a section requires one, s.185 particulars, the s.186 amount, proxy, route map, e-voting, signature, CIN | Built |
| **Precedents:** wording from other companies' notices | Precedent library: every notice is split into resolutions and explanatory statements, searchable by section, topic, special/ordinary, amount and words | Built (proven on 3 real notices) |
| **Compliance calendar** | Due dates: 20 rules with legal basis, worked out from the company file | Built. Next: SEBI LODR, FEMA, CSR-2, BEN-2, IEPF, SS-1/SS-2 notice periods |
| **Limits and calculations** | Calculators: s.186 limit, s.180(1)(c), s.185 conditions, with the working shown | Built. Next: s.197/Schedule V remuneration, s.135 CSR, s.2(85) small company, s.188 thresholds, deposits, MCA late fees |
| **Meetings:** notice, agenda, explanatory statements, minutes, attendance | Notice builder | **Next** (see below) |
| **Drafting:** resolutions, CTCs, consents, letters | Word templates filled from the company file (`csdesk/drafting`), plus precedents | Built (templates). Next: drafting from precedents with a redline |
| **MCA filings** | Form filler in her logged-in browser, stopping before submit; recorder that learns a form from one filling; SRN tracking | Built (practice form). Next: real recipes; AOC-4/MGT-7 through MCA's Excel utility |
| **Law:** Acts, Rules, SS-1/SS-2, circulars | Law desk search (`csdesk/lawdesk`), plus Claude reading with citations | Built. Next: load the texts; weekly digest of new MCA/SEBI circulars |
| **Due diligence and search reports** | Dossier from the company file (`csdesk/dossier`) | Built. Next: add library facts and MCA master data |
| **Statutory registers:** MGT-1, MBP-2, MBP-4, CHG-7, directors and KMP | Registers | Later. MBP-2 comes first, because every s.186 loan goes in it |
| **Secretarial audit, certificates, UDIN** | MR-3 checklist from the company file, UDIN log | Later |
| **Listed-company compliance (SEBI LODR)** | Filings calendar and checks | Later, if she is in-house at a listed company |
| **Practice:** work in hand, past work, notes | Work register: each job (board meeting, AGM, EGM, annual filings, director appointment, allotment, charge, due diligence, secretarial audit) starts with its checklist, each step citing the Act, rules or SS-1/SS-2. Ticks, notes on steps, attached documents, due dates. Notes on anything (documents, work, companies, people, statements), pinned to Home and searchable | Built. Fees and billing later |

## Last night's job, and how AAGAM does it

She prepared an AGM notice with resolutions under s.185 and s.186, starting from listed companies' notices and adapting them to her company, which needed approval for ₹100 crore.

1. **Find wording.** The listed companies' notices go into the library, ticked as "another company's document". Precedents → s.186 → special → "at least ₹50 crore" lists every matching resolution and its statement. On the three real notices loaded so far, that is Aditya Spinners (₹50 crore), Godha Cabcon (₹100 crore) and H.G. Infra (₹6,000 crore).
2. **Check the limit.** Calculators → s.186: paid-up capital, free reserves, securities premium, and what is outstanding and proposed. It shows the limit step by step, whether a special resolution is needed under s.186(3), and the related rules (s.186(5), (7), the MBP-2 register). For a private company it also notes the exemptions for s.180 and s.185.
3. **Adapt it.** Today, she copies the resolution and statement from the precedent, or asks Claude Desktop: "draft s.185 and s.186 resolutions for Acme from precedents 21 and 5, with a ₹100 crore limit". Claude uses `precedent_get`, `loan_limits` and the company file. Next, the notice builder will do this inside AAGAM.

## The notice builder (next)

1. Choose the company and meeting. Items come from the company file: accounts, rotation (who retires), auditor term, plus special business she adds.
2. Each item starts from a precedent or her own template, with the company's facts filled in: name, CIN, DINs, amounts, dates.
3. Every change from the precedent is kept as a redline, so she can see exactly what was "rectified".
4. Checks: an explanatory statement for every special business item (s.102), the s.185(2) disclosures, the s.186 figures, notice period and e-voting.
5. Export to Word on her letterhead. The resolutions then feed MGT-14 due dates and the filing.

## The interface

- **Themes:** Light, **Night light** (warm paper, low in blue light, for reading late), Dark, and **Banaras ghat** (a maroon silk sidebar edged in zari, an ivory page with a faint jaal lattice, Palatino headings, and the ghats at dawn along the foot of every page: havelis, shikharas, chhatris and umbrellas over the steps, boats rocking on the Ganga, diyas and marigolds afloat; its charts use the saree's peacock blue, marigold, parrot green and rani pink, checked for colour blindness), or follow Windows. A link can pick the theme: `http://127.0.0.1:8765/?theme=banaras`. The choice is in the top bar and is remembered. Colours glide from one theme to the next.
- **Background drawings:** line drawings that draw themselves, stroke by stroke, behind the desk: Justice, blindfolded, with her scales; the ledger; the company's seal with "Certified true copy"; the minute book with its quill. They follow the work (the ledger on Financials, the seal on People and companies, the minute book on Work) and move on by themselves every 22 seconds. They stay off the reading pages (documents and precedents), can be turned off in the theme menu, and stand still when Windows asks for less motion.
- **Help:** "What AAGAM does" in the sidebar is the guide: every feature, how to use it, and whether it needs AI. **?** on any page opens help for that page. Home offers the tour on first use.
- **Ctrl+K** opens one box that finds anything and goes anywhere: documents (with the matching words), work, notes, people, companies, statements and resolutions, plus the pages, "new work", "new note", "add documents" and the themes. The top bar's search opens it.
- **Drop files anywhere** in the window to add them; the upload box asks only for the client, the type, and whether it is another company's document.
- **Home** is one calm column: a sentence on what's in hand, late and due; work in hand; coming up; pinned notes; recent documents.
- **Reading a document:** the page is set like paper, with a page-turner at its foot (or ← →). The side panel has four tabs (About, Checks, Facts, Notes) and can be hidden.
- **Accounts** have tabs: Overview, Ratios, What applies, Figures, Notes and facts.
- **The sidebar** shows counts (work in hand, overdue filings) and narrows to icons.
- **Motion:** pages and lists ease in, numbers count up, bars grow, ticks draw themselves. All of it stops when Windows asks for less motion.
- **Charts** use one palette, checked for colour blindness against each theme's background. Every chart has its figures in a table beside it, and every status has an icon and a word, never colour alone.

## How it fits together

```
 Her browser ──> AAGAM window (React, built from Artemis's interface) ──> aagam serve: FastAPI on 127.0.0.1:8765
 Claude Desktop ──> aagam mcp (59 tools) ─────────────────────────────┐        │  background: local-AI worker, inbox watcher, OCR
                                                                      ▼        ▼
          ┌────────────────────────── one SQLite database in AAGAM_HOME ──────────────────────────┐
          │ company file · filings · documents + pages (full-text) · facts · tags · resolutions        │
          │ financial statements · work register · notes (full-text)                                  │
          └──────────────────────────────────────────────────────────────────────────────────────────┘
               │                                   │                              │
       csdesk (core): due dates,           aagam: library, OCR, notices,   Ollama (optional, local):
       form filler, recorder, drafting,    precedents, calculators,         summaries and tag suggestions
       law desk, dossier                   finance, entities, work, notes,
                                           notice checker, web, MCP
               │
       CS Desk browser window (she logs in; tools stop before submit, sign and pay)
```

### What came from Artemis

Artemis was a ten-service Docker stack (Postgres, Redis, Meilisearch, Neo4j, MinIO, Ollama, Celery and others), built for a Linux server. AAGAM keeps its shape and its interface, and runs as one program on her laptop.

| Artemis | AAGAM |
|---|---|
| React + React Query + Tailwind interface: sidebar shell, tag badges and picker, upload | Kept and re-themed (Light, Night light, Dark). Pages rebuilt for her work |
| Ingest pipeline: fingerprint → parse → normalise → chunk → enrich → persist → index | Same stages: core intake → classify → facts → notice splitting → tags → AI queue |
| Postgres + Meilisearch + pgvector | SQLite with FTS5 full-text search: one file, nothing to install |
| spaCy NER (people, organisations, places) | CS rules: CIN, DIN with the person, PAN, GSTIN, FRN, membership numbers, ₹ amounts, dates, sections |
| Celery + Redis workers | Three background threads (local AI, inbox, OCR) |
| Ollama | Kept, optional, for summaries |
| Neo4j graph; campaigns and people (OSINT) | Dropped. A director-and-company network from the company file can come later |

`I:\Artemis` is untouched.

## Running it

Her laptop: `scripts\setup-windows.cmd -ConfigureClaude -DesktopShortcut -LocalAI`. This needs Python 3.11+, plus Ollama from ollama.com for the local AI. She then opens **AAGAM** from the desktop shortcut.

| Command | What it does |
|---|---|
| `aagam` | Opens AAGAM (starts the server if needed) |
| `aagam serve` / `aagam mcp` | The web server; the Claude Desktop server |
| `aagam add FILE... [--company X] [--tag precedent]` | Brings files in from a terminal |
| `aagam reindex` | Re-reads every document (after a rule improves) |
| `aagam doctor` | Checks the installation: Python, data folder, database, interface, port, OCR, Chrome/Edge, Ollama, Claude Desktop, disk space; each problem with its fix |
| `aagam ai` | Runs queued local-AI summaries now |
| `aagam claude-config --write` | Adds AAGAM to Claude Desktop, replacing the older `csdesk` entry |
| `aagam build-ui` | Rebuilds the interface (developers; uses `.tools/node`) |
| `csdesk record FORM`, `csdesk set-sensitive`, `csdesk browser` | The core's form tools, as before |

Optional Docker (for a server or another machine; her laptop doesn't need it): `docker compose up -d` serves AAGAM on 127.0.0.1:8765 with its data in a named volume; `--profile ai` adds Ollama. Windows OCR and MCA form filling aren't available in the container. See the README.

Settings are environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `AAGAM_HOME` | `%USERPROFILE%\AAGAM` | The data folder |
| `AAGAM_PORT` | 8765 | The web server's port |
| `AAGAM_BIND` | 127.0.0.1 | Where the server listens (0.0.0.0 only inside the optional Docker container) |
| `AAGAM_LOCAL_AI` | `on` | Set to `off` to disable local AI |
| `AAGAM_LOCAL_AI_MODEL` | `qwen3:4b` | Use `qwen3:8b` if she has a graphics card |
| `AAGAM_LOCAL_AI_URL` | `http://127.0.0.1:11434` | Where Ollama listens |

Developing:

```
.venv\Scripts\python -m pytest              # 255 tests; browser ones use Chrome; one uses Ollama if it's running
$env:AAGAM_REAL_NOTICES = "<folder>"        # also run the real-notice tests against PDFs in that folder
cd frontend; npm run dev                    # live-reloading interface against a running `aagam serve`
```

## Insights: reading for a purpose

`aagam/analysis/` reads every document as it comes in (and whenever it is read again) for six purposes: investments, legal matters, law cited, amendments, obligations and deadlines, and agreement terms. Each purpose is one module with its own patterns and a weighted word list. Shared helpers in `analysis/text.py` split sentences (not on "Rs.", "Pvt. Ltd.", "u/s."), find ₹ amounts and dates with their places, score how much a document is about a subject against its length, and pick its most telling sentences as an extractive summary.

A purpose is kept only when the document is about it and something solid is found, so passing mentions don't fill the registers. A failing purpose never stops the others. Results go to the `analyses` table (one row per document and purpose) and each found purpose tags the document. In the window: Insights (a register per purpose, search, client filter, CSV) and an Insights tab on every document; Claude Desktop has `document_analysis` and `insights`. On the three real notices it finds, for example, Aditya Spinners' s.185 guarantee and security of ₹20 crore each for Sri Chakra Cement, the s.186 limit of ₹50 crore and its 50,80,320 shares in Envean Leasing. A 150-page document is read for all six purposes in about a second.

## Correcting and deleting

Everything AAGAM reads can be corrected, and anything can be deleted. What it reads is rebuilt each time a document is read again; her corrections are kept apart and applied after every reading, so they last (`aagam/editing.py`).

| What | How she does it | What lasts |
|---|---|---|
| A page's text (an OCR misreading) | Document → ⋯ → Correct this page's text | Her text; facts, resolutions and figures are read from it, and OCR leaves the page alone |
| A document's title, client, the company it is about, the meeting and its date | The pencil beside the type | Kept over what the text says |
| A fact that isn't one | Hover it → hide in this document or everywhere | Stays hidden; People and companies → Hidden brings it back (the documents are read again) |
| The name a person or company is shown under | Dossier → the pencil by the name | Shown under her name everywhere |
| A resolution split wrongly | Precedents → Correct (title, kind, sections, amount, wording) or delete | Her version, or it stays deleted |
| Tags | Library → Tags: rename, merge, delete; or take one off a document | Automatic tagging uses the new name, leaves deleted ones off, and doesn't put back one she took off |
| Statements: whose, the basis, the years, the unit | Accounts → ⋯ (a new unit rescales every figure) | Kept through re-reading; deleted statements aren't read again |
| A line of the figures | Figures → click it; the eraser clears it | Hers |
| Work, notes, statements, clients, people, meetings and other records | Their ⋯ menus or the row's delete button | Gone, after a confirmation that lists what goes with it |

Deleting is careful by design:

- **A document's file goes to the bin folder** in AAGAM_HOME, not off the disk, so it can be added again. Its pages leave the search index.
- **Her notes are never lost.** Notes on a deleted document, piece of work, resolution, set of statements or client become general notes, headed with what they were about.
- **The company file keeps its evidence.** A value quoted from a deleted document keeps its quote, marked "source document deleted".
- **A client takes its own file with it** (meetings, positions, resolutions, charges, registrations, filings, auditors, events). Its documents, work and statements stay, untied from it. A person deleted takes only their positions. The confirmation lists exactly this before anything goes.
- Deletes are recorded in the activity log. Through Claude Desktop nothing can be deleted (it can only take a tag off a document).

## Safety

- **It answers only this computer.** It listens on 127.0.0.1, rejects other Host names (against DNS rebinding), and refuses any change without the `X-AAGAM` header. A form or script on another website can't add that header.
- **Data stays local.** Client data stays in AAGAM_HOME, local AI runs on the laptop, and only what Claude Desktop reads goes to Claude.
- **Sensitive numbers are masked.** PANs are masked in the facts and in every tool reply. The page text keeps them, because it is her document.
- **Her work is never overwritten.** A summary she wrote is never replaced by an AI's. AI tags stay suggestions until she accepts them. Re-reading a document keeps her own tags and her choice of type.
- **Portal rules still hold.** All of the core's rules for MCA stay in force: she logs in, and the tools stop before submit, sign and pay.

## Known limits

- The notice splitter is tuned on three real notices and a synthetic one. Unusual layouts may split wrongly. The document page shows every resolution with its page, so a mistake is easy to spot, and adding the notice to the tests fixes the rule for good.
- Scanned pages are read by Windows OCR, which uses the English OCR language that comes with Windows. OCR misreads happen (a comma read as a point). The statement reader repairs revenue from the totals when it can and says so, and every OCR page carries a note. Check figures against the page image.
- The statement reader knows the Schedule III captions. Statements in another layout (an LLP's, or a bank's under its own schedule) are read only in part. She can fill in or correct any line, and "Show the lines not found" lists what's missing.
- What applies is worked out from one year's figures. Most thresholds look at the previous year's audited figures or any time in the year, so each card cites the rule to check the date against.
- `qwen3:4b` writes plain summaries. Its key points can list agenda lines rather than insights. Anything that matters should come from Claude.
- `.doc` (old Word) and `.ppt` (old PowerPoint) files aren't read. Save them as `.docx` or `.pptx`.
