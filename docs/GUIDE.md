# Using AAGAM: the guide

This guide is for the person who uses AAGAM every day. It walks through each job, step by step, in the words AAGAM itself uses on screen. You don't need to know anything technical.

To install AAGAM, see the [README](../README.md). This guide starts once AAGAM is on your laptop.

**Contents**

1. [Opening AAGAM and finding your way](#1-opening-aagam-and-finding-your-way)
2. [Your first hour: setting up](#2-your-first-hour-setting-up)
3. [Clients and the company file](#3-clients-and-the-company-file)
4. [Bringing documents in](#4-bringing-documents-in)
5. [Finding documents](#5-finding-documents)
6. [Reading a document, and correcting it](#6-reading-a-document-and-correcting-it)
7. [Due dates and filings](#7-due-dates-and-filings)
8. [The work register](#8-the-work-register)
9. [Notes](#9-notes)
10. [Precedents, notices and drafting](#10-precedents-notices-and-drafting)
11. [People and companies (dossiers)](#11-people-and-companies-dossiers)
12. [Insights](#12-insights)
13. [Financial statements and calculators](#13-financial-statements-and-calculators)
14. [LLPs](#14-llps)
15. [MCA forms and the CS Desk browser](#15-mca-forms-and-the-cs-desk-browser)
16. [Claude Desktop and the local AI](#16-claude-desktop-and-the-local-ai)
17. [The Trash](#17-the-trash)
18. [Keeping AAGAM well: updates, health, backups](#18-keeping-aagam-well-updates-health-backups)
19. [A typical day and a typical month](#19-a-typical-day-and-a-typical-month)
20. [Shortcuts and quick answers](#20-shortcuts-and-quick-answers)

---

## 1. Opening AAGAM and finding your way

**To open AAGAM,** double-click **AAGAM** on the desktop, or press the Windows key, type *AAGAM* and press Enter. It opens in your web browser. The address, `http://127.0.0.1:8765`, is your own laptop: nothing goes to the internet.

- The very first time after installing or updating, a small **Opening AAGAM…** window may show for up to a minute. That is normal.
- AAGAM normally starts by itself in the background when you sign in to Windows, so after the first time it opens at once.
- You can close the browser tab whenever you like. AAGAM keeps running quietly, reading folders and checking for updates. Open it again from the shortcut.

**The screen**

| Part | What it is |
|---|---|
| **The menu on the left** | **Desk** (Home, Work, Due dates, Notes), **Records** (Clients, Library, Search, Precedents, People & companies, Trash) and **Analysis** (Insights, Financials, Calculators). At the foot: **Updates & health** and **What AAGAM does** (help). The red number beside Due dates is how many items are overdue. |
| **The search box at the top** | Finds anything, anywhere (also **Ctrl+K**). |
| **Add documents** (top right) | Brings files in. You can also drop files anywhere in the window. |
| **AI on / off** | Whether the local AI is running. Everything else works without it. |
| **?** | Help for the page you are on. |
| **The palette icon** | Light, Night light (warm, for late reading), Dark, or Banaras ghat. |

**Home** is where each day starts: a sentence on what is in hand, late and due; your work in hand; filings coming up in the next 30 days; pinned notes; and the documents you opened last. When a new version of AAGAM is ready, a note on Home says so.

---

## 2. Your first hour: setting up

Do these once, in this order. Each is explained in its own section below.

1. **Add your clients:** **Clients → New client**. The name and the CIN (or LLPIN) are enough to start. See [section 3](#3-clients-and-the-company-file).
2. **Bring in your existing files:** **Library → Add a folder**, pick the folder where you keep client papers, choose **Work it out for each document**, tick **Keep watching this folder**, and press **Read … files**. See [section 4](#4-bringing-documents-in).
3. **Add the directors, KMP and partners** for each client, with their appointment dates. Due dates for DIR-12, Form 4 and DIR-3 KYC come from these.
4. **Add the last AGM, board meetings and auditor** for each company. The AGM, AOC-4, MGT-7 and ADT-1 dates come from these.
5. **Look at Due dates.** Mark what has already been filed with **Mark as filed**. See [section 7](#7-due-dates-and-filings).
6. **Make a backup:** **Updates & health → Back up my data**. See [section 18](#18-keeping-aagam-well-updates-health-backups).

---

## 3. Clients and the company file

Each client has a **company file**: everything on record for that company or LLP. Due dates, dossiers and drafts are all worked out from it.

**To add a client**

1. Open **Clients** and press **New client**.
2. Type the name and the CIN (21 characters) or, for an LLP, the LLPIN (like `AAB-1234`). Add what else you know: class, date of incorporation, registered office, email.
3. Press **Add client**.

**To open a client,** click its name in **Clients**. Its page has:

| Section | What goes in it |
|---|---|
| **Details** | Name, CIN or LLPIN, class, status, registered office, capital, PAN, and the rest. Change any field and press **Save**. |
| **Directors, KMP and partners** | Who holds which position, from when, and until when. |
| **Meetings** | Board meetings, AGMs, EGMs, committee meetings and postal ballots, with dates. |
| **Resolutions passed** | Special resolutions and others that must be filed in MGT-14. |
| **Charges** | Created, modified and satisfied, with dates. |
| **Registrations** | GSTIN, IEC, Udyam, PF, ESI and others. |
| **Auditors** | Who was appointed, when and for which years. |
| **Events (allotments, changes)** | Allotments, capital changes, a new registered office, a change of name, an LLP agreement change, a BEN-1 declaration received. |
| **Filings** | Every form filed, with its SRN and date. |
| **Due in 90 days** | What this client has coming up. |
| **Accounts read** | Financial statements found in the library for this client. |

**To add a director, KMP or partner**

1. In **Directors, KMP and partners**, press **Add a position**.
2. Pick the person if they are already on file, or press **New person or organisation** first (name, DIN, PAN, email…).
3. Choose the position (director, managing director, company secretary, designated partner, partner, and so on) and the date of appointment. Save.

**When someone leaves,** don't delete them: open their position (**Change the position**), add the date it ceased and the reason. AAGAM then works out the DIR-12 (or LLP Form 4) for the cessation.

**Where each value came from.** A small mark beside each field says where its value came from: typed by you, read from a document (with the page), or read on the portal. Every change is recorded.

**PAN, Aadhaar and passport numbers** are always shown masked (`XXXXXX234F`).

**To delete** a record, hover its row and press **Delete**. Deleting a whole client first shows exactly what goes with it. Its documents stay in the library.

---

## 4. Bringing documents in

AAGAM reads PDFs (scanned ones too), Word (.docx), Excel (.xlsx and .xls), PowerPoint (.pptx), Outlook emails (.msg and .eml), RTF, web pages and text. For each document it works out:

- **what it is** (notice, minutes, financial statements, LLP agreement, MCA form, sanction letter…);
- **whose it is** (the client, from its CIN or LLPIN, the folder it was in, or the company it names);
- **what date it is of** (its meeting, its accounts' date, its "Date:" line, or when the file was last changed);
- **the facts in it** (CINs, DINs with the person, PANs masked, amounts, dates, sections), and for a notice each resolution with its explanatory statement.

Old .doc and .ppt files can't be read: open them in Word or PowerPoint and save them as .docx or .pptx.

### A few files: drag and drop

1. Drag files, or whole folders, from File Explorer onto the AAGAM window. (Or press **Add documents**.)
2. In the box that opens, choose the **Client**:
   - **Work it out** (usually right): each file goes to the client it points to.
   - **Not a client's document**: law, circulars, your own papers.
   - or pick one client.
3. Leave **Type** on **Work it out**, unless you know better.
4. For a listed company's notice that you want only for its wording, tick **Another company's document, for the precedent library**.
5. Press **Add … documents** (the button says how many). A bar shows the progress; you can carry on working.

### A whole folder: Add a folder

Use this for your existing archive (for example `D:\Clients`), however many folders deep.

1. Open **Library** and press **Add a folder**.
2. Press **Browse…** and choose the folder (or type its place). AAGAM shows how many files it found, of which kinds, and which it can't read.
3. Choose the **Client**: **Work it out for each document** (best when your folders are named after clients), **Not a client's documents**, or one client.
4. Tick **Keep watching this folder** if you want new files saved there later to be read too.
5. Press **Read … files** (the button says how many).

Your own files stay exactly where they are: AAGAM keeps its own copy of each. Reading a big folder takes a while. The **Folders on your computer** panel at the top of the Library shows how far it has got. If AAGAM is closed meanwhile, it carries on where it stopped next time.

In that panel, for each folder:

| Button | What it does |
|---|---|
| **Show its documents** | Narrows the Library to that folder. |
| **Look again** | Reads only what is new or changed since last time. |
| **⋯ → Stop watching / Watch for new files** | Turns watching off or on. |
| **⋯ → Forget this folder** | Stops looking at it. Choose **Keep its documents** (usual) or **Move them to the Trash**. |

A document you delete is never brought back by **Look again**.

### The inbox folder

There is also an **inbox** folder in your AAGAM data folder (`C:\Users\<you>\AAGAM\inbox`). Anything saved or copied into it is brought in by itself while AAGAM is open, and moved to `inbox\processed`. This is handy for scanner output or email attachments. **Library → Check inbox** reads it at once.

---

## 5. Finding documents

### The search box (Ctrl+K)

Press **Ctrl+K** on any page and type. It finds pages, work, notes, people, companies, statements and resolutions. Press Enter on the first line to search every page. Typing a CIN, LLPIN, GSTIN or DIN offers its dossier. Typing "work", "fin" or "new note" jumps there.

### Search (every word on every page)

Open **Search**.

- Every word you type must appear on the page.
- Words of three letters or more also find longer words: *guarant* finds *guarantee*.
- Put words in quotes to find them together: `"principal business activities"`.
- Results show the matching passages, with a link straight to the page.

### The Library and its filters

The **Library** lists every document. The filters along the top narrow it down. Each choice shows how many documents it would give.

| Filter | Use it to… |
|---|---|
| **Filter by name, company or folder** | find a document by what it is called |
| **All types** | only notices, only minutes, only financial statements… |
| **All clients** | one client's documents, or **No client** for those not filed under anyone |
| **Any kind of file** | only PDFs, only emails, only Excel… |
| **Scanned or not** | only scanned documents (to check the OCR), or only typed ones |
| **Any financial year** | FY 2024-25 means 1 April 2024 to 31 March 2025, by the document's own date |
| **Dated from / to** | any range of dates |
| **Any folder** | the documents from one folder you brought in, and then the folders inside it |
| the tags under the filters | click a tag to see its documents |

Then choose the order (**Newest added**, **Newest by date**, **Oldest by date**, **Name**) and, if you like, **Group by** client, type, financial year, month or folder. That sorts the list into sections, so you can see a client's year at a glance.

**Clear** takes all the filters off.

**Choosing several:** hover a document and tick the box that appears on its left, then tick others. **Move to Trash** takes them all out together; they can be restored.

---

## 6. Reading a document, and correcting it

Click a document to open it.

- **Turning pages:** the page-turner at the foot, or the ← → keys. The image button shows the page as it really looks (useful for scans).
- **Find in this document** lists the pages where your words appear.

The side panel has tabs:

| Tab | What it shows |
|---|---|
| **About** | Type, title, client (and why AAGAM chose it), the company it is about, the meeting, the document's date (and how it was found), where the file came from on your computer, its summary and its tags. |
| **Checks** | For a notice: **Check this notice**. Also the financial statements and the resolutions read from it. |
| **Facts** | CINs, DINs with their person, PANs (masked), amounts, dates and sections, each with its pages. |
| **Insights** | What the document says about investments, legal matters, the law it cites, amendments, obligations and agreement terms ([section 12](#12-insights)). |
| **Notes** | Your notes on this document. |

### Putting things right

AAGAM reads by rules, and sometimes reads wrongly. Everything can be corrected, and **your corrections are kept** even when the document is read again.

| What's wrong | How to fix it |
|---|---|
| The title, client, the company it is about, the meeting, or **the document's date** | The **pencil** beside the type, in **About**. Change and **Save**. |
| The type | The type list in **About**. |
| A page misread by OCR | **⋯ → Correct this page's text**. Type the right text and save; facts and figures are read again from it. |
| A "fact" that isn't one (a heading read as a company name) | Hover it in **Facts** and hide it, in this document only or everywhere. **People & companies → Hidden** brings it back. |
| A tag | Remove it from the document, or **Library → Tags** to rename, merge or delete it everywhere. |
| A resolution split wrongly | In **Precedents**, open it and **Correct this resolution** (or delete it). |
| A summary | **Edit summary** in **About**. Your own summary is never replaced by the AI's. |

**To delete a document:** **⋯ → Move to Trash**. Right after, the message has an **Undo** button. Later, it can be restored from the **Trash** ([section 17](#17-the-trash)).

---

## 7. Due dates and filings

**Due dates** lists what is due for every client, worked out from the company file: AGMs, AOC-4, MGT-7, ADT-1, DIR-12, MGT-14, CHG-1, PAS-3, INC-22, DPT-3, MSME-1, DIR-3 KYC, BEN-2, and for LLPs Forms 3, 4, 5, 8, 11, 15 and LLP BEN-2.

- Choose how far ahead to look: **Next 30 / 60 / 90 / 180 / 365 days**. Overdue items stay on the list, in red, until they are filed.
- Each line shows the date, the form, the client, what it is for, how the date was worked out (for example "AGM held 30-09-2026 + 30 days") and the law it comes from (for example "s.137(1)").
- An item marked **check** rests on a reading you should confirm (for example whether ADT-1 is needed for a first auditor).

**When you have filed a form**

1. Press **Mark as filed** on its line.
2. Type the **SRN** from the MCA receipt (optional), the **Date filed** and the fees (optional).
3. Press **Mark as filed**.

The filing is kept in the client's **Filings**, and the item leaves the list.

**If a date looks wrong,** something in the company file is missing or wrong (an AGM date, an appointment date, the financial year end). Fix it in the client's file and the date follows.

**Home** shows the next 30 days, and the red number on **Due dates** in the menu counts what is overdue.

---

## 8. The work register

**Work** keeps each job you do (an AGM, a director's appointment, an annual filing) with its checklist, documents, dates and notes. Finished work stays there, so you can find how you did it last year.

**To start a piece of work**

1. **Work → New work** (or **Start a piece of work** on Home).
2. Choose the **Kind of work**: board meeting, AGM, EGM, annual filings, director appointment, allotment, charge, due diligence, secretarial audit, or one of the LLP jobs (incorporation, annual filing, partner changes, agreement changes, registered office, name change, strike off).
3. Give it a **Title** (for example *AGM 2026 · Acme Widgets*), the **Company**, the **Due by** date and, for a meeting, the **Meeting date**.
4. Press **Start this work**.

Its checklist is laid out, and **each step says where it comes from**: the section, rule or SS-1/SS-2 paragraph.

- **Tick** steps as you go. The next one is marked **Next**.
- Hover a step to add a note to it (for example *Shorter notice consent received from 96% on 12 Sept*) or to remove it. Type in **Add a step** for your own steps.
- **Attach** the notice, drafts, minutes and filings from the library as they come.
- Set the status: **In hand**, **Waiting on someone**, **Done** or **Dropped**.

---

## 9. Notes

Write a note on anything: a document, a piece of work, a client, a person, a set of accounts, or nothing in particular.

- On a document or piece of work: its **Notes** tab or panel.
- A general note: **Notes**, type it, press **Save note** (or Ctrl+Enter).
- Press the pin on a note (**Pin to Home**) to keep it on Home.
- Every note can be found with **Search notes** or Ctrl+K.

When something with notes on it is deleted, the notes are kept as general notes, so your words are never lost.

---

## 10. Precedents, notices and drafting

### Precedents

Every notice you bring in is split into its resolutions and explanatory statements. **Precedents** lets you find wording by:

- **section** (s.180, s.185, s.186…), **topic** (loans and investments, related party, borrowing powers…), **special or ordinary**, the amount, and words.

Open one to read the resolution and its **Explanatory statement**, and copy what you need. To grow the library, bring in listed companies' AGM notices with **Another company's document, for the precedent library** ticked.

### Checking a notice

Before you send a notice of a general meeting:

1. Bring the draft notice into the library.
2. Open it, go to **Checks**, and press **Check this notice**.

It checks, without any AI: 21 clear days; an explanatory statement for every special item, with directors' interests; special resolutions where the section needs one; s.185 particulars and the s.186 amount; the proxy statement; the route map; e-voting; the signature and CIN. Each finding says **ok**, **missing** or **check**, with the rule and the page.

### Drafting

Ask Claude Desktop ([section 16](#16-claude-desktop-and-the-local-ai)) to adapt a precedent to your client, for example:

> Draft the s.185 and s.186 resolutions for Acme Widgets from precedent 5, with a limit of ₹100 crore.

Always read the draft against the Act before using it.

---

## 11. People and companies (dossiers)

**People & companies** lists everyone and everything named in your documents: people, companies, DINs, CINs, LLPINs, GSTINs, audit firms and institute members. A name written differently in different papers is grouped together.

Open one to see its **dossier**:

- every document and page it appears on, with the words around it (click to open that page);
- its identifiers, decoded: a CIN's state, year and kind, and a GSTIN's state and the PAN inside it;
- its record in your company file, and who it appears with;
- for a company, its resolutions and financial statements.

To show someone under the name you prefer, use the pencil by the name (**Change the name shown**). You can write a note at the foot.

---

## 12. Insights

**Insights** reads every document for six purposes and keeps a register for each across the whole library:

| Purpose | For example |
|---|---|
| **Investments** | loans, guarantees, security and investments (s.185, s.186), with the investee and amount |
| **Legal matters** | cases, forum and bench, parties, sections, next date |
| **Law cited** | Acts, sections, rules, notifications, circulars and case citations |
| **Amendments** | what was amended, how, and from when |
| **Obligations and deadlines** | who must do what by when |
| **Agreement terms** | parties, term, amount, interest, governing law, arbitration, termination |

Pick a purpose, search, filter by client, and press **Download CSV** for a spreadsheet. Click a row to see the sentence it came from. **Clear**, **Likely** and **Check** say how sure the reading is. These are readings by rules: confirm anything important against the page.

---

## 13. Financial statements and calculators

### Financials

When audited accounts come into the library, AAGAM reads the balance sheet and the statement of profit and loss (scanned ones too) in their own unit (lakhs, crore, thousands). Open **Financials** and choose a set:

| Tab | What it shows |
|---|---|
| **Overview** | Headline figures, where the money comes from, and anything to look at |
| **Ratios** | The 11 Schedule III ratios, with any change over 25% flagged (it needs an explanation in the notes) |
| **What applies** | Small company, CSR, secretarial audit, internal audit, whole-time CS, independent and woman directors, XBRL, CARO, tax audit, MSME-1, DPT-3, each with its basis and the work it brings. Start that work from here. |
| **Figures** | Every line with its page. Click a line to correct it; your figures are kept. |
| **Notes and facts** | What the accounts don't say (listed, holding or subsidiary, bank borrowings…), which settles the "check" items |

**⋯ → Correct whose, which years, which unit** fixes the header. Changing the unit rescales every figure.

Check the figures against the pages before relying on them, especially for scanned accounts.

### Calculators

**Calculators** works out the **s.186** limit (and whether a special resolution is needed), **s.180(1)(c)** and the **s.185** conditions, with the working shown step by step. Enter the figures in crore or rupees and press **Work it out**. Opened from a set of accounts, the figures are filled in for you.

---

## 14. LLPs

Everything above works for LLPs too. What is particular to them:

- **Add an LLP** in **Clients** with its **LLPIN** (for example `AAB-1234`). AAGAM knows it is an LLP from that.
- **Partners:** add **designated partners** and **partners** under **Directors, KMP and partners**. A designated partner needs a DIN (DPIN); give their DIR-3 KYC date too. The dossier warns if fewer than two designated partners are on file.
- **Due dates:** Form 11 by **30 May**, Form 8 by **30 October**, Form 3 within 30 days of incorporation and of each change in the LLP agreement, Form 4 within 30 days of a partner joining or leaving, Form 15 for a new registered office, Form 5 for a change of name, and LLP BEN-2 within 30 days of a BEN-1 declaration. For an LLP incorporated in the second half of a financial year, the first year's dates are marked **check**.
- **Events:** record an LLP agreement change, a new registered office, a change of name or a BEN-1 declaration under **Events**. The due date follows.
- **Documents:** LLP agreements and supplementary agreements, partners' resolutions, partners' consents, and filed LLP forms (FiLLiP, RUN-LLP, Forms 3, 4, 5, 8, 11, 15) are recognised by type. An LLPIN on a document files it under that LLP.
- **Work:** the LLP checklists cover incorporation, annual filing, partner changes, agreement changes, registered office, name change and strike off.

Two LLP dates are marked **check** on purpose: Form 5 (when the 30 days start) and LLP BEN-2. The audit threshold under rule 24(8) is worth confirming with the auditor.

---

## 15. MCA forms and the CS Desk browser

AAGAM can fill MCA forms for you **in your own logged-in browser window**, and it **always stops before submit, sign and pay**. You do those.

1. Open **CS Desk browser** from the desktop. It is a separate Chrome (or Edge) window kept just for MCA.
2. Log in to the MCA portal yourself, with the captcha and OTP.
3. In Claude Desktop, ask for the form, for example: *Fill DIR-12 for the appointment of Asha Rao at Acme Widgets.* Claude checks that the browser is logged in, fills the fields from the company file, and tells you what is ready.
4. Check every field, then sign, submit and pay yourself. Then use **Mark as filed** in **Due dates** with the SRN.

A form AAGAM hasn't learnt yet can be taught once: ask Claude to *record me filling this form*. Fill it yourself on a draft; nothing is clicked or typed for you while it records. Claude then turns the recording into a recipe.

---

## 16. Claude Desktop and the local AI

### Claude Desktop

If Claude Desktop is installed and connected (**Updates & health → Health → Claude Desktop → Fix**, then quit and reopen Claude Desktop), Claude can use AAGAM's library and company file directly. Ask in plain words:

- *Summarise the 2025 accounts of J. Kumar-NCC and what they make apply.*
- *Which of my open work is late, and what is the next step on each?*
- *Draft the s.185 and s.186 resolutions for Acme with a ₹100 crore limit, from the precedents on file.*
- *Read the folder D:\Clients\New and file everything under the right clients.*
- *What does the LLP agreement of Beta Traders say about admitting a partner?*

Claude never submits, signs or pays on a portal, and it can't delete anything in AAGAM. Only what Claude reads goes to Claude; your library stays on the laptop.

### The local AI

If the local AI (Ollama) is installed, each document gets a short **summary** and suggested tags, written on the laptop itself; nothing leaves it. The top bar shows **AI on** or **AI off**. Suggested tags stay suggestions until you accept them. A summary you write yourself is never replaced. To install it: **Updates & health → Health → Local AI → Fix**, or **AAGAM Manager → Local AI**.

---

## 17. The Trash

Deleted documents wait in the **Trash** (in the menu on the left), so you can change your mind.

- **Restore** puts a document back as it was: its pages, your corrections, summary, tags and notes, and the work it was on.
- **Delete forever** removes one for good. **Empty the Trash** removes everything in it for good. Both ask first and can't be undone.
- **Deleted before the Trash existed** lists older deleted files. **Add back** reads one into the library again.

---

## 18. Keeping AAGAM well: updates, health, backups

### Updates

New versions of AAGAM arrive by themselves. You don't have to do anything.

- When one is ready, a note on Home and a mark in the menu say so. Press **Update now** whenever it suits you. AAGAM closes for about a minute and the window comes back by itself.
- With **Install updates by themselves** on (the usual setting), a new version is put in place once AAGAM has been left alone for 20 minutes, never while you are working.
- If an update goes wrong, AAGAM puts the version you had back.
- Updates never touch your documents or records.
- If you use Claude Desktop, quit it and open it again after an update.

If the window ever says **AAGAM is starting again…**, wait a minute: it is usually putting a new version in place, and comes back by itself.

### Updates & health

**Updates & health** (at the foot of the menu) has:

- **This copy of AAGAM:** the version, and where the program and your data are.
- **Updates:** **Check now**, **Update now**, what's new, and the switches **Install updates by themselves** and **Start AAGAM when I sign in to Windows**.
- **Health of this computer:** every part AAGAM needs, each **Fine**, **Worth a look** or **Needs fixing**, with what to do and a **Fix** button where AAGAM can fix it itself.
- **Backups and help:** **Back up my data** and **Save a report for help**.
- **Uninstall.**

### AAGAM Manager (when AAGAM won't open)

**AAGAM Manager**, on the desktop and in the Start menu, is a small window that works even when AAGAM itself doesn't. It shows whether AAGAM is running and whether an update is waiting. It has a button for each job: **Open AAGAM**, **Stop AAGAM**, **Check for updates**, **Update now**, **Health check**, **Repair**, **Local AI**, **Claude Desktop**, **Back up my data**, **Report for help**, **Open data folder** and **Uninstall**.

**If something is wrong,** press **Health check** first. If it finds a problem, press **Repair**: it fetches a fresh copy of AAGAM from GitHub and sets everything up again. Your documents are kept.

### Backups

Your work is in one folder: `C:\Users\<you>\AAGAM`. Back it up regularly.

- **Updates & health → Back up my data** (or **AAGAM Manager → Back up my data**) copies it into **Documents → AAGAM backups**. AAGAM can stay open. Each copy has a **READ ME.txt** saying how to put it back.
- Keep a copy somewhere else too: an external drive, or cloud storage you trust.
- **On a new laptop:** install AAGAM, close it, then replace the new `AAGAM` data folder with your copy.

### When you need help

Press **Save a report for help** (in Updates & health, or **Report for help** in the Manager). A file appears on the Desktop: send that. It has the health check and recent logs, and no documents or keys.

---

## 19. A typical day and a typical month

**Each morning**

1. Open AAGAM. Read **Home**: what is late, what is due this week, work in hand.
2. Drop in the day's papers (or save them into a watched folder or the inbox).
3. Open **Work** and tick what you finished yesterday.

**When a filing is done**

1. **Due dates → Mark as filed**, with the SRN.
2. Attach the filed form and challan to the work, then mark the work **Done**.

**When something changes at a client** (a new director, a resolution, a charge, an allotment, a new office): record it in the client's file the same day. The due date appears at once.

**Each month**

1. **Due dates → Next 60 days**, to plan ahead.
2. **Library → All clients → No client**, to file anything AAGAM couldn't place.
3. **Library → Scanned or not → Has scanned pages**, to check any important scans read badly.
4. **Updates & health → Back up my data**.

**Each year, after the AGMs**

1. Add each AGM to the client's file; AOC-4 and MGT-7 dates follow.
2. Bring in the audited accounts; check **Financials → What applies** for each client.
3. For LLPs: Form 11 by 30 May and Form 8 by 30 October.

---

## 20. Shortcuts and quick answers

| Keys | What they do |
|---|---|
| **Ctrl+K** | Find anything, go anywhere |
| **?** | Help for this page |
| **Esc** | Close a box or panel |
| **← →** | Previous and next page in a document |
| **Ctrl+Enter** | Save a note |

**Quick answers**

- **Does AAGAM change my original files?** No. It keeps its own copy of each and never touches yours.
- **Does anything go to the internet?** Only update checks (to GitHub), and what you ask Claude Desktop to read. The local AI runs on the laptop.
- **A document went under the wrong client.** Open it, press the pencil in **About**, and choose the right client. It stays that way.
- **AAGAM got a document's date wrong.** Same pencil: change **The document's date**.
- **A due date stays overdue although I filed it.** Press **Mark as filed** on it.
- **The window says "AAGAM has closed".** Open it again from the **AAGAM** shortcut, or **AAGAM Manager → Open AAGAM**.
- **Something isn't working.** **AAGAM Manager → Health check**, then **Repair**. If that doesn't do it, send the file from **Report for help**.
- **Where is my data?** `C:\Users\<you>\AAGAM`. **Updates & health** shows the exact place.

More help: **What AAGAM does** (at the foot of the menu), or **?** on any page.
