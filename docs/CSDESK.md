# CS Desk: foundations map

> CS Desk is now AAGAM's core (`src/csdesk` in this repository); [AAGAM.md](AAGAM.md) is the map of the whole system. Where this page says CSDESK_HOME, read AAGAM_HOME (default `%USERPROFILE%\AAGAM`); `I:\Shruti` paths now live under `I:\AAGAM`, and Claude Desktop starts `aagam mcp`, which includes every tool listed here.

CS Desk takes the typing and the reading off a Company Secretary's plate. Claude reads her documents and fills forms. She checks the work, signs with her DSC and submits. This page maps what is built, how the parts fit together, the rules the code enforces, and what comes next.

**Status on 10 October 2026:** the foundations are built and tested (115 tests, some of which drive a real browser). There are no recipes for real MCA forms yet. The recorder that captures them is built: the first real recipe needs one session on her laptop, with her logged in, filling a draft.

## The pieces

| Piece | What it does for her | State |
|---|---|---|
| Company file | One record per client: CIN, directors and KMP, capital, auditors, meetings, resolutions, charges, filings. Every value keeps its source. | Built |
| Document reader | Files go into each client's folder and their text is indexed. Scanned pages are shown to Claude as images. | Built. Batch extraction through the Claude API comes later |
| Due dates | Works out what is due when, with the legal basis, from what is on file. | Built: 20 rules (table below) |
| Form filler | Works inside her logged-in browser window and fills forms from the company file. It saves a draft, keeps evidence and stops before submit. | Framework built and proven on a practice page. Real MCA recipes come next |
| Recorder | Watches her fill a form once, then writes the flow down and drafts the form's recipe from it. | Built, and proven by recording the practice form and replaying the recipe it drafted |
| Drafting | Word drafts from her own templates, filled from the company file. | Built, with one sample template. Her templates go in next |
| Law desk | Searches the Acts, Rules, SS-1/SS-2 and circulars she keeps, section by section. | Built. The law folder stays empty until we add the texts |
| Dossier | One page per company: snapshot, people, filings, gaps, and where each fact came from. | Built from the company file. Outside data (MCA master data, GST) comes later |

## How it fits together

```
 She ── chat ──> Claude Desktop ── MCP over stdio ──> csdesk serve  (src/csdesk/server.py, 34 tools)
                                                          │
     ┌───────────────┬───────────────┬──────────────┬─────┴────────┬──────────────┬──────────────┐
 company file    documents       due dates      form filler     drafting       law desk       dossier
 vault/          documents/      duedates/      forms/ +        drafting/      lawdesk/       dossier/
 (SQLite)        (copy + text)   (rules)        browser/        (Word)         (search index) (Markdown)
     │                                               │               recorder/ (background process
     └── all client data lives in CSDESK_HOME        │               while she fills a form)
                                                     │ Chrome DevTools Protocol, 127.0.0.1 only
                                                     ▼
                                   CS Desk browser window  <── she logs in here (captcha, OTP)
```

## The login: she logs in, then the tools work

1. She opens the CS Desk browser with the desktop shortcut or `csdesk browser`, or Claude opens it with `browser_start`. It is Chrome with its own profile and a debugging port that listens on 127.0.0.1 only.
2. She logs in to MCA herself: email, password, captcha and OTP.
3. Claude calls `browser_status`, which lists the tabs and shows whether MCA looks logged in.
4. Claude opens a filing (`start_filing`) and runs `fill_form`. That fills the open form from the company file, reads every value back and saves a draft. It writes a fill log and a screenshot into the filing's folder, then stops.
5. She reviews the form, presses Submit, signs with her DSC and pays.
6. She tells Claude the SRN, and `update_filing` records it. The due-date item then closes.

The tools never see her password. Her session stays in the CS Desk profile until MCA ends it, and then she logs in again.

## Capturing a form's flow: the recorder

A recipe says where each value goes on a portal page. We get it by watching her fill the form once, on a draft she doesn't submit. We don't use an intercepting proxy such as Burp Suite:

- **Recipes work on the page, not on network traffic.** A proxy shows requests and responses but not labels, field order, dropdown options or which button she pressed. The form filler types into fields by their labels, so those are what we need to capture.
- **A proxy would put her laptop at risk.** Intercepting HTTPS means installing a root certificate that every site would trust. The proxy history would also hold her password, OTP and session cookies in plain text, on the machine that holds her DSC.
- **Replaying requests would go around the portal's own form.** That skips its checks, depends on undocumented internals that change without notice, and removes the step where she reviews the form on screen.

The recorder watches over the same DevTools connection the form filler uses, so it needs nothing installed. It never clicks, types or answers a dialog.

1. She logs in and opens the form, then Claude calls `record_start` with the form, the company and the person it is about. From a terminal, `csdesk record DIR-12 --company Acme --party 3` does the same.
2. She fills the form as usual and saves the draft.
3. Claude calls `record_stop`. The recorder writes into `recordings\<date>-<form>\`:
   - `flow.md`, step by step: each field's label, type, what she entered (by shape) and the company-file field it matched; fields the portal filled itself; required fields left empty; the buttons she pressed, and whether CS Desk may press them; dialogs; and the portal's requests in order (method, address, status, time).
   - `recipe_draft.py`, a draft recipe with a TODO on every field that needs a person's judgment.
   - `screens\`, with a screenshot at each new step and after each button press.
   - `events.jsonl`, the raw log everything above is built from.
4. We review the draft, check it against the live form, and add it to `forms/registry.py`.

What it keeps:

| Kind of data | Kept as |
|---|---|
| Text she types | Only its shape ("PAN", "date DD/MM/YYYY", "text, 28 characters") and the company-file field holding the same value. The value itself never reaches a file. |
| Passwords, OTPs, captchas | Not read at all |
| Dropdown and radio choices | The option text, e.g. "Additional Director" |
| Uploaded files | The file name only |
| Portal requests | Method, address without query values (the parameter names are kept), status and timing. No headers, cookies or bodies. |
| Screenshots | What was on screen, values included. They stay in the recording folder on her laptop, like the form filler's evidence. |

When the recording is for a company and person already in the company file, most keys come out filled in. On the practice form, five of the eight fields matched; the other three (date of appointment, designation, shareholder) are values the form filler is given as extras.

## Rules, and where the code enforces them

| Rule | Enforced in |
|---|---|
| Never submit, sign or pay | `browser/guard.py`. Only buttons on an allowed list (save, next, add and the like) can be clicked. Anything naming submit, sign, DSC, pay or challan is refused, and so is opening a payment or signing page. There is no general "click anything" tool. |
| Stop if the portal changed | `forms/recipe.py`. Every field is found by its label before anything is typed into it. A missing or duplicated label stops the fill there, and every value is read back after typing. |
| Every value has a source | `vault/store.py`. Every write needs a source. A document source must name a stored document and a page that exists. Each field written is logged in `field_sources`. |
| Sensitive numbers stay masked | PAN, Aadhaar and passport numbers are masked in every reply, in the field history (quotes included) and in fill logs. `csdesk set-sensitive` lets her type them on her own machine. The form filler reads them straight from the file. |
| Only known sites | `browser/session.py`. The tools open https pages on mca.gov.in, gst.gov.in, incometax.gov.in and icsi.edu, plus the practice form, and nothing else. |
| Leave her dialogs and downloads alone | `browser/session.py`. By default Playwright presses Cancel on every dialog box and sends downloads to a temporary folder it deletes on disconnect. Every attachment turns both off (`no_defaults=True` plus a dialog listener that only takes notes). Tools report dialogs that are waiting for her. If a dialog is blocking the page, they say so within 20 seconds rather than hanging. |
| Catch typos before the portal does | `validators.py` checks CIN, LLPIN, PAN (including holder type), DIN, Aadhaar (Verhoeff check digit), GSTIN (check character), TAN, PIN code, mobile, email, dates in Indian formats and rupee amounts. A director's PAN can't be saved as the company's. |

## The company file

| Table | Holds | Drives |
|---|---|---|
| companies | CIN/LLPIN, class, status, registered office, capital, financial year end, flags (small company, MSME-1, DPT-3) | AGM, DPT-3, MSME-1, OPC and LLP annual forms, INC-20A |
| parties | People and organisations: DIN, PAN, Aadhaar, address, audit firm FRN, membership numbers, next DIN KYC date | DIR-3 KYC |
| appointments | Who holds which position, from when to when | DIR-12, LLP Form 4 |
| meetings | Board meetings, AGMs, EGMs, committee meetings, postal ballots | AOC-4, MGT-7/7A, MGT-15, next board meeting |
| resolutions | Board, circular, ordinary and special resolutions | MGT-14 |
| auditor_appointments | Auditor, type, term, and the meeting that appointed them | ADT-1 |
| charges | Holder, amount, and dates of creation, modification and satisfaction | CHG-1, CHG-4 |
| events | Allotments, changes of capital, changes of registered office | PAS-3, SH-7, INC-22 |
| registrations | GSTIN, IEC, Udyam, EPF and others | Dossier |
| filings | Form, trigger, status, SRN, evidence folder | Closes due-date items |
| documents, document_pages | Stored files and their text, page by page | Document reader |
| field_sources | Every value written, with its source | Dossier, field history |
| activity | Every save and browser action | Audit trail |

## Due-date rules

| Form | Due | Basis | Notes |
|---|---|---|---|
| AOC-4 | AGM + 30 days | s.137(1) | OPC: year end + 180 days |
| MGT-7 / MGT-7A | AGM + 60 days | s.92(4) | MGT-7A for small companies and OPCs. The OPC date counts from 30 September (to confirm) |
| MGT-15 | AGM + 30 days | s.121(1) | Listed companies |
| AGM | Year end + 6 months, or previous AGM + 15 months if that is earlier | s.96(1) | First AGM: end of first year + 9 months (to confirm) |
| Board meeting | Last meeting + 120 days | s.173(1) | Small, OPC and dormant companies: one per half-year, 90 days apart (s.173(5)) |
| DIR-12 | Appointment or cessation + 30 days | s.170(2) | Not for first directors named at incorporation |
| ADT-1 | Appointing meeting + 15 days | s.139(1), rule 4(2) | First auditor appointed by the Board: to confirm |
| MGT-14 | Resolution + 30 days | s.117(1) | Special resolutions, and any others she flags |
| PAS-3 | Allotment + 15 days (private placement) or + 30 days (others) | s.42; s.39(4) with rule 12 | If the allotment type isn't recorded, 15 days is assumed |
| SH-7 | Alteration + 30 days | s.64(1) | |
| INC-22 | Change + 30 days | s.12(4) | 30 days since the 2017 amendment |
| CHG-1 | Creation or modification + 30 days | s.77(1), s.79 | |
| CHG-4 | Satisfaction + 30 days | s.82(1) | |
| INC-20A | Incorporation + 180 days | s.10A(1)(a) | Companies with share capital incorporated from 2 November 2018 |
| DPT-3 | 30 June | Rules 16 and 16A, Deposit Rules | Unless marked not applicable |
| MSME-1 | 30 April and 31 October | MSE payments order, 2019 | Only when marked applicable |
| DIR-3 KYC | Each person's next KYC date | Rule 12A (from 31 March 2026) | Once in three financial years, by 30 June; changes reported within 30 days |
| LLP Form 11 | 30 May | LLP rule 25 | |
| LLP Form 8 | 30 October | LLP rule 24 | |
| LLP Form 4 | Partner change + 30 days | LLP Act s.25(2) | |

Dates aren't moved for holidays. Items marked "check" rest on a reading she should confirm. Not covered yet: SEBI LODR and stock-exchange filings, FEMA filings with RBI, CSR-2, BEN-2, the CRA forms, IEPF, and the register-of-members work behind MGT-7.

## Where her data lives

```
CSDESK_HOME  (default C:\Users\<her>\CSDesk)
├── csdesk.db                  the company file
├── law.db                     the law-desk search index (can be deleted and rebuilt)
├── clients\<CIN>\
│   ├── documents\             her files, as ingested
│   ├── filings\<id>-<form>\   fill logs and screenshots for each filing
│   ├── drafts\                Word drafts
│   └── dossier\               dossiers
├── inbox\                     she drops files here; processed ones move to inbox\processed\<date>
├── templates\                 her Word templates
├── law\                       Acts, Rules, SS-1/SS-2, circulars
├── browser-profile\           the CS Desk browser's own profile, which holds her MCA session
├── recordings\<date>-<form>\  the recorder's flow.md, recipe_draft.py, screenshots and event log
└── logs\csdesk.log
```

The code folder never holds client data. Back up CSDESK_HOME, and turn on Windows device encryption (or BitLocker) on her laptop, because the company file isn't encrypted by CS Desk itself.

## Running it

On her laptop, run `scripts\setup-windows.cmd -ConfigureClaude -DesktopShortcut` and then restart Claude Desktop. The script creates the Python environment, installs CS Desk and sets up the data folder. It also adds CS Desk to Claude Desktop's config, keeping a backup, and puts a "CS Desk browser" shortcut on the desktop.

To work on it here:

```
.venv\Scripts\python -m pytest                                  # 115 tests; the browser ones use the installed Chrome
$env:CSDESK_HOME = "I:\Shruti\.dev-data"; .venv\Scripts\csdesk due
```

`.mcp.json` registers the server with Claude Code in this folder, with `.dev-data` as its data folder (never real client data). Claude Code asks for approval the first time.

| Command | What it does |
|---|---|
| `csdesk init` | Sets up the data folder, database and sample template, and prints the Claude Desktop entry |
| `csdesk serve` | Runs the MCP server over stdio (Claude starts this) |
| `csdesk browser` | Opens the CS Desk browser window so she can log in |
| `csdesk due [--company X] [--days N]` | Prints what is overdue and what falls due soon |
| `csdesk set-sensitive --party ID --field pan` | She types a PAN, Aadhaar or passport number on her own machine, so it never goes through the chat |
| `csdesk claude-config [--write]` | Prints the Claude Desktop entry, or adds it to Claude Desktop's config with a backup |
| `csdesk record FORM [--company X] [--party ID]` | Records her filling FORM in the CS Desk browser until Enter is pressed, then writes the flow and a draft recipe |

## What comes next

1. Her answers: whether she is in practice or in-house, her most-filed forms, and the tools she uses today.
2. Record the first MCA form in one session on her laptop. She logs in, opens the form and fills a draft while the recorder runs, and we turn the draft recipe into a real one. The draft is never submitted.
3. Multi-step replay. MCA V3 forms run over several sections, and today `fill_form` fills one recorded step per call.
4. Use her past filings and their source documents as test cases, since we already know the right answers.
5. AOC-4 and MGT-7 through MCA's offline Excel files, generated from the financial statements and the register of members.
6. Her Word templates go into `templates`; the Act, Rules and SS-1/SS-2 go into `law`.
7. Outside data for the dossier: MCA master data through a licensed API, and GSTIN checks (see `gst-lookup.md`).
8. Batch extraction through the Claude API, for many documents at once.

## Known limits

- "Logged in" is a guess (a visible Logout link) until we have seen the real V3 page.
- The practice form proves the loop. Each real MCA page needs its own recipe, and recipes will need updating when MCA changes its forms.
- The recorder sees fields in frames but can't yet fill them. Fields inside shadow DOM (some web-component libraries use it) aren't seen at all. We'll know whether MCA V3 uses either once we record a real form.
- A field's recorded label can differ slightly from the name Playwright looks it up by (a trailing "*", for example). If it does, the first fill stops at that field and says so, and we fix the label.
- Masking limits how often sensitive numbers travel, but any document Claude reads shows whatever is printed on it.
- Due dates are only as good as the facts on file.
- The debugging port lets programs on her laptop control the CS Desk browser window. It listens only on 127.0.0.1, and the window uses its own profile.
