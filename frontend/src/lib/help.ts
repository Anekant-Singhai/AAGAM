/** What AAGAM does, in her words: the Help page and the "?" drawer read from here. */

export type Power = "rules" | "local" | "claude";

export interface Feature {
  key: string;
  title: string;
  icon: string;
  to: string;
  what: string;
  how: string[];
  power: Power[];
}

export const POWER: Record<Power, { label: string; hint: string }> = {
  rules: { label: "No AI needed", hint: "Exact rules on this laptop; works offline" },
  local: { label: "Local AI", hint: "Ollama on this laptop, if it is running; documents never leave it" },
  claude: { label: "Claude Desktop", hint: "Ask Claude; it works on this same library through AAGAM's tools" },
};

export const GROUPS: { title: string; blurb: string; features: Feature[] }[] = [
  {
    title: "Keep and find",
    blurb: "Everything that comes in is kept, read and made findable.",
    features: [
      {
        key: "clients", title: "Clients (the company file)", icon: "building", to: "/companies",
        what: "Each client's details, directors and KMP, meetings, resolutions, charges, registrations, auditors and filings. Due dates are worked out from it.",
        how: [
          "New client: the name is enough to start; with the CIN, the class, listing and state are filled in.",
          "Every field can be changed; each change is recorded as yours, and a small mark shows where each value came from.",
          "PAN and Aadhaar are written in but only ever shown masked. Deleting a client or a person shows first what goes with it.",
        ],
        power: ["rules"],
      },
      {
        key: "library", title: "Library", icon: "files", to: "/library",
        what: "Every document, read page by page: its type, the company, the meeting, facts and resolutions.",
        how: [
          "Drop files or whole folders anywhere in the window, or use Add documents. PDF (scanned too), Word, Excel, PowerPoint, Outlook, RTF, HTML and text all work.",
          "Each document is filed under its client by itself: from its CIN or LLPIN, the name of the folder it was in, or the company it names. You can always change it.",
          "Each document gets the date it is of: its meeting, the date of its accounts, its \"Date:\" line, or else when the file was last changed.",
          "Filter by name, type, client, kind of file, financial year, dates, folder and tag; sort by date or name; and group the list by client, type, year, month or folder.",
          "Scanned pages are read by Windows OCR: five pages straight away, longer documents in the background.",
        ],
        power: ["rules", "local"],
      },
      {
        key: "folders", title: "Folders from your computer", icon: "folder", to: "/library?add=folder",
        what: "Point AAGAM at a folder, such as D:\\Clients, and it reads every file in it and in the folders inside it, while you carry on working.",
        how: [
          "Library → Add a folder. Type the folder's place or use Browse…; AAGAM shows how many files it can read before it starts.",
          "Your files stay where they are. AAGAM keeps its own copy of each, so moving or deleting the originals later doesn't harm the library.",
          "A big folder takes a while. The Library shows how far it has got; if AAGAM is closed, it carries on where it stopped next time.",
          "Tick \"Keep watching\" and files saved into the folder later are read too. Look again reads only what is new or changed.",
          "Files AAGAM can't read yet (old .doc or .ppt files, zips) are counted and named, with what to do about them.",
        ],
        power: ["rules"],
      },
      {
        key: "find", title: "Find anything (Ctrl+K)", icon: "command", to: "/",
        what: "One box over everything: pages, work, notes, people, companies, statements and resolutions.",
        how: [
          "Press Ctrl+K on any page and type. Enter on the first line searches every page.",
          "Type a CIN, LLPIN, GSTIN or DIN and AAGAM recognises it and offers its dossier.",
          "Type the start of a place (\"fin\", \"work\") to jump there, or \"new work\", \"new note\", \"night\".",
        ],
        power: ["rules"],
      },
      {
        key: "search", title: "Full-text search", icon: "search", to: "/search",
        what: "Every word on every page, with the matches marked and a link straight to the page.",
        how: [
          "Every word must appear. Words of three letters or more also find longer words (\"guarant\" finds guarantee).",
          "Put words in quotes to find them together: \"principal business activities\".",
          "Inside a document, use its own Find box; the pages with matches are listed.",
        ],
        power: ["rules"],
      },
      {
        key: "entities", title: "People and companies", icon: "users", to: "/entities",
        what: "Everyone named in the library, however it was written, with a dossier on each.",
        how: [
          "A dossier shows every document and page they appear on, with the words around it.",
          "Their DIN, CIN, LLPIN or GSTIN, their record in the company file, and who they appear with.",
          "A GSTIN is decoded (state, the PAN inside, which registration); a CIN too (listed, state, year, kind).",
        ],
        power: ["rules"],
      },
      {
        key: "notes", title: "Notes", icon: "note", to: "/notes",
        what: "Write a note on anything: a document, a piece of work, a company, a person, a set of accounts.",
        how: ["Pin a note to keep it on Home.", "Every note is searchable, here and in Ctrl+K.", "Ctrl+Enter saves."],
        power: ["rules"],
      },
    ],
  },
  {
    title: "Correct and clean up",
    blurb: "Everything AAGAM reads can be corrected, and anything can be deleted. Your corrections are kept when a document is read again.",
    features: [
      {
        key: "correct", title: "Correcting what was read", icon: "pen", to: "/library",
        what: "A page misread by OCR, the company or meeting of a document, a resolution split wrongly, a figure in the accounts: all can be put right.",
        how: [
          "In a document, ⋯ → Correct this page's text; the facts, resolutions and figures are read again from your text.",
          "The pencil beside the type changes the title, client, the company it is about, and the meeting and date.",
          "In Precedents, Correct changes a resolution's title, kind, sections, amount and wording.",
          "In the accounts, ⋯ corrects whose they are, the years and the unit (every figure is rescaled).",
        ],
        power: ["rules"],
      },
      {
        key: "clean", title: "Hiding and deleting", icon: "trash", to: "/entities",
        what: "Take out what isn't right or isn't wanted, with a clear warning of what goes with it.",
        how: [
          "A fact that isn't one (a heading read as a company): hover it and hide it in that document or everywhere. Bring it back from People and companies → Hidden.",
          "Tags: Library → Tags renames, merges or deletes them; automatic tagging follows.",
          "A document you delete goes to the Trash, and can be restored from there as it was.",
          "Work, notes, statements, resolutions, clients and people can all be deleted from their ⋯ menus.",
        ],
        power: ["rules"],
      },
      {
        key: "trash", title: "Trash", icon: "trash", to: "/trash",
        what: "Deleted documents wait in the Trash, so you can change your mind.",
        how: [
          "In a document, ⋯ → Move to Trash. In the Library, choose several and Move to Trash.",
          "Restore puts a document back as it was: its pages, your corrections, summary, tags and notes, and the work it was on.",
          "Delete forever, or Empty the Trash, removes the files from your computer for good.",
        ],
        power: ["rules"],
      },
    ],
  },
  {
    title: "Do the work",
    blurb: "The jobs in hand, each with the law behind every step.",
    features: [
      {
        key: "work", title: "Work register", icon: "briefcase", to: "/work",
        what: "Each job, from a board meeting to a charge, with its checklist, documents, dates and notes.",
        how: [
          "New work → choose the kind (board meeting, AGM, EGM, annual filings, appointment, allotment, charge, due diligence, secretarial audit, and the LLP jobs: incorporation, annual filing, partners, agreement, office, name, strike off).",
          "Each step cites its basis: the section, rule or SS-1/SS-2 paragraph. Tick it, note against it, or add your own.",
          "Attach the notice, drafts and filings. Home shows what is late and what is next.",
        ],
        power: ["rules"],
      },
      {
        key: "precedents", title: "Precedents", icon: "book", to: "/precedents",
        what: "Every resolution and explanatory statement from every notice, ready to adapt.",
        how: [
          "Add listed companies' notices (tick \"another company's document\").",
          "Filter by section, topic, special or ordinary, amount, and words; copy the wording.",
          "Ask Claude to adapt one to your client: \"draft s.186 for Acme from precedent 5, ₹100 crore\".",
        ],
        power: ["rules", "claude"],
      },
      {
        key: "notice", title: "Notice check", icon: "check", to: "/library?type=notice",
        what: "Checks a notice of a meeting against the Act and SS-2, without any AI.",
        how: [
          "Open a notice → Checks → Check this notice.",
          "21 clear days; an explanatory statement for each special item, with directors' interest; special resolutions where the section needs one.",
          "s.185 particulars, the s.186 amount, proxy, route map, e-voting, signature and CIN.",
        ],
        power: ["rules"],
      },
      {
        key: "due", title: "Due dates", icon: "calendar", to: "/due",
        what: "What is due for each client company, worked out from the company file, each with its legal basis.",
        how: ["Items marked \"check\" rest on a reading to confirm.", "Once a form is filed, Mark as filed records it (with its SRN) in the client's Filings and takes it off the list.", "Home shows the next 30 days. Companies and LLPs alike."],
        power: ["rules"],
      },
      {
        key: "mca", title: "MCA forms", icon: "globe", to: "/help#mca",
        what: "Fills MCA forms in your own logged-in browser window, and stops before submit.",
        how: [
          "You log in yourself (captcha and OTP). AAGAM never submits, signs or pays.",
          "Ask Claude Desktop to fill a form; it checks the browser first.",
          "A form without a recipe is learnt by recording you fill it once.",
        ],
        power: ["claude"],
      },
    ],
  },
  {
    title: "Figures and limits",
    blurb: "Read the accounts and test them against the thresholds.",
    features: [
      {
        key: "insights", title: "Insights: read for me", icon: "scan", to: "/insights",
        what: "Every document is read for six purposes: investments (s.186), legal matters, the law it cites, amendments, obligations and deadlines, and agreement terms. What is found is brought together across the library as registers.",
        how: [
          "Pick a purpose to see its register: every investment, every matter, every provision cited, each with its document and page.",
          "Search and filter by client; Download CSV takes the register to a spreadsheet.",
          "Click a row to see the sentence it came from. Clear, Likely or Check says how sure the reading is.",
          "In a document, the Insights tab shows what was found in it; Analyse again reads it afresh.",
        ],
        power: ["rules"],
      },
      {
        key: "financials", title: "Financial statements", icon: "landmark", to: "/financials",
        what: "The balance sheet and profit and loss read from the accounts in the library, with the ratios and what they make apply.",
        how: [
          "Overview: headline figures, where the money comes from, and things to look at.",
          "Ratios: the 11 Schedule III ratios, with any change of more than 25% flagged to explain.",
          "What applies: small company, CSR, secretarial and internal audit, whole-time CS, independent and woman directors, XBRL, CARO, tax audit, MSME-1, DPT-3, each with its basis; start the work from there.",
          "Figures: every line with its page. Click to correct; your figures are kept.",
        ],
        power: ["rules"],
      },
      {
        key: "calculators", title: "Loan and borrowing limits", icon: "calculator", to: "/calculators",
        what: "The s.186 limit and whether a special resolution is needed; s.180(1)(c); the s.185 conditions.",
        how: ["Enter the figures in crore or rupees, or open it from a set of accounts to start from their figures.", "The working is shown step by step, with the sections."],
        power: ["rules"],
      },
    ],
  },
  {
    title: "AI, when you want it",
    blurb: "Rules do what must be exact. AI does the reading and drafting you ask for.",
    features: [
      {
        key: "local", title: "Local AI", icon: "bot", to: "/library",
        what: "A summary and suggested tags for each document, written by a model on this laptop.",
        how: ["Needs Ollama running (ollama.com). The top bar shows whether it is.", "Your own summary is never replaced."],
        power: ["local"],
      },
      {
        key: "claude", title: "Claude Desktop", icon: "sparkles", to: "/help#claude",
        what: "Claude works on this same library and company file through AAGAM's tools.",
        how: [
          "Ask: \"Summarise the 2025 accounts of J. Kumar-NCC and what they make apply.\"",
          "\"Draft the s.185 and s.186 resolutions for Acme with a ₹100 crore limit.\"",
          "\"Which of my open work is late, and what is the next step on each?\"",
        ],
        power: ["claude"],
      },
    ],
  },
  {
    title: "Looking after AAGAM",
    blurb: "New versions arrive by themselves, and AAGAM can check and repair itself.",
    features: [
      {
        key: "updates", title: "Updates", icon: "sparkles", to: "/system",
        what: "When a new version of AAGAM is published, AAGAM finds it and puts it in place. Your documents and records are never touched.",
        how: [
          "A note on Home and a mark in the sidebar say when a new version is ready; Update now puts it in place in about a minute.",
          "With automatic updates on, a new version is put in place once AAGAM has been left alone for 20 minutes, never while you are working. At 8:00, if AAGAM is closed, it is installed too.",
          "If an update goes wrong, the version you had is put back. Your documents are never touched. If you use Claude Desktop, quit it and open it again afterwards.",
        ],
        power: ["rules"],
      },
      {
        key: "health", title: "Health and repairs", icon: "heart", to: "/system",
        what: "A check of everything AAGAM needs on this computer, with a button to fix what is missing.",
        how: [
          "Updates & health → Health lists each part: fine, worth a look, or needs fixing, with what to do.",
          "Install local AI, connect Claude Desktop, put the desktop shortcuts back, or repair AAGAM, each with one button.",
          "Uninstall removes the program but keeps your data folder, unless you choose to delete that too.",
          "If AAGAM won't open at all, AAGAM Manager in the Start menu has the same buttons: Open, Health check, Repair, Update now and more.",
        ],
        power: ["rules"],
      },
      {
        key: "backup", title: "Backups and a report for help", icon: "life", to: "/system",
        what: "A copy of your documents and records, and a small file you can send if something goes wrong.",
        how: [
          "Updates & health, then Back up my data. The copy goes in Documents, in a folder called AAGAM backups. Open the READ ME.txt inside it to put the copy back.",
          "On a new laptop: install AAGAM, close it, and replace the AAGAM data folder with that copy.",
          "Save a report for help writes a file on the Desktop. It has the health check and recent logs. It does not contain your documents or your update key.",
        ],
        power: ["rules"],
      },
    ],
  },
];

export const SHORTCUTS: [string, string][] = [
  ["Ctrl K", "Find anything, go anywhere"],
  ["?", "Help for this page"],
  ["Esc", "Close a box or panel"],
  ["← →", "Previous and next page, in a document"],
  ["Ctrl Enter", "Save a note"],
];

/** A few lines of help for the page she is on. */
export const PAGE_HELP: [RegExp, string, string[]][] = [
  [/^\/$/, "Home", [
    "Work in hand shows progress and what is late; Coming up shows filings due in 30 days.",
    "Drop files anywhere to add them to the library.",
    "Pin a note to keep it here.",
  ]],
  [/^\/work\/\d+/, "A piece of work", [
    "Tick steps as you go; the next one is marked.",
    "Hover a step to add a note to it or remove it. Add your own steps at the end.",
    "Attach documents from the library; set the meeting and due dates on the right.",
  ]],
  [/^\/work/, "Work register", ["New work lays out the checklist for that kind of job.", "In hand, Done and Dropped keep past work findable."]],
  [/^\/library/, "Library", [
    "Drop files or folders anywhere, or use Add documents. Add a folder reads a whole folder from your computer in the background, and can keep watching it.",
    "Filter by type, client, kind of file, financial year, dates and folder; the numbers say how many documents each choice shows. Click a tag to see its documents.",
    "Sort by date or name, and group the list by client, type, year, month or folder.",
    "Hover a document and tick it to choose several; Move to Trash takes them out (they can be restored).",
  ]],
  [/^\/trash/, "Trash", ["Restore puts a document back as it was, with your corrections, tags and notes.", "Delete forever and Empty the Trash can't be undone."]],
  [/^\/system/, "Updates & health", [
    "Check now looks for a new version; Update now puts it in place, and AAGAM opens again by itself.",
    "Health lists what AAGAM needs on this computer, with a button to fix each missing part.",
    "Back up my data copies your documents to Documents. Save a report for help writes a file on the Desktop, with no documents in it.",
    "Uninstall keeps your data folder unless you choose otherwise.",
  ]],
  [/^\/documents/, "Reading a document", [
    "← and → turn the pages. The image button shows the page as it looks.",
    "Find in this document lists the pages with matches.",
    "The side panel: About (type, details, summary, tags), Checks (notice check, statements, resolutions), Facts, Insights (investments, legal matters, law cited and more, with their pages), and Notes.",
    "⋯ corrects this page's text (an OCR misreading) or moves the document to the Trash. Hover a fact to hide it if it isn't one.",
    "About shows the document's date and how it was found, the client and why, and where the file came from on your computer.",
  ]],
  [/^\/search/, "Search", ["Every word must appear; quotes keep a phrase together.", "On the right: work, notes, people and statements that match too."]],
  [/^\/precedents/, "Precedents", ["Pick a section or topic, or type words; open one to read its explanatory statement and copy it."]],
  [/^\/entities\/.+/, "A dossier", ["Every mention, with the words around it; click to open that page.", "Write a note on this person or company at the foot."]],
  [/^\/entities/, "People and companies", ["Pick a kind; type to narrow. Names written differently are grouped together."]],
  [/^\/insights/, "Insights", [
    "Each purpose is a register across the library: investments, legal matters, law cited, amendments, obligations, agreement terms.",
    "Search by name, section or forum and filter by client; Download CSV gives the same rows as a spreadsheet.",
    "Click a row to see the sentence it came from; the document link opens that page. Clear, Likely and Check say how sure the reading is.",
  ]],
  [/^\/financials\/\d+/, "A set of accounts", [
    "Tabs: Overview, Ratios, What applies, Figures, Notes and facts.",
    "Correct any figure in Figures; the ratios and tests are worked out again.",
    "Tell AAGAM what the accounts don't say (listed, holding or subsidiary, bank borrowings) under Notes and facts.",
  ]],
  [/^\/financials/, "Financial statements", ["Accounts in the library are read automatically. Open one to see its analysis."]],
  [/^\/companies\/\d+/, "A client", [
    "Details: change any field and save; the mark beside a label says where the value came from.",
    "Directors and KMP: add a position for someone on file, or a new person first. To record a resignation, change the position and give the date it ceased.",
    "Meetings, filings and other records: hover a row to change or delete it. Due dates follow.",
  ]],
  [/^\/companies/, "Clients", ["New client starts a company file. Open one to see and change everything on it."]],
  [/^\/notes/, "Notes", ["Search finds words in any note. Pinned notes show on Home."]],
  [/^\/calculators/, "Calculators", ["Enter the figures and Work it out. Opened from a set of accounts, the figures are filled in."]],
  [/^\/due/, "Due dates", ["Worked out from the company file. Choose how far ahead to look.", "Mark as filed records the filing (SRN, date, fees) and takes the item off the list."]],
];
