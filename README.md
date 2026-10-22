# AAGAM

AAGAM is a desk for a Company Secretary that runs on her own Windows laptop. It keeps her clients' documents and records in one place, reads them, finds anything in seconds, works out due dates, and helps with drafting and MCA forms. Nothing leaves the laptop unless she uses Claude Desktop.

**What it does**

- **Library:** PDFs (scanned ones too), Word, Excel, PowerPoint, Outlook emails, RTF, web pages and text. Every page is read and searchable. AAGAM works out what each document is, which client it belongs to, and what date it is of.
- **Bring in whole folders:** point AAGAM at a folder (for example `D:\Clients`). It reads every file in every subfolder in the background, files each document under its client, and can keep watching the folder for new files. Your own files stay exactly where they are.
- **Find things by date and more:** filter the library by financial year, dates, client, folder, type of document and kind of file, and group the list by any of them.
- **Trash:** deleted documents wait in the Trash and can be put back exactly as they were, or deleted for good.
- **Companies and LLPs:** directors, KMP, designated partners, meetings, resolutions, charges and filings, every value tied to where it came from. For LLPs: LLPIN, Forms 3, 4, 5, 8, 11 and 15, LLP BEN-2, and LLP checklists.
- **Due dates** with their legal basis, **calculators** (s.186, s.180, s.185), **precedents** from other companies' notices, a **notice checker**, **financial statements** with ratios, a **work register** with checklists, and **notes** on anything.
- **MCA forms** filled in her own logged-in browser, always stopping before submit, sign and pay.
- **Local AI** summaries (Ollama, on the laptop) and **Claude Desktop** tools over the same data.
- **Updates itself** from GitHub, checks its own health, and can repair or uninstall itself.

---

## Install AAGAM on a new laptop

You need a Windows 10 or 11 laptop and an internet connection. The installer downloads everything else (Python, AAGAM, and if you want it, the local AI). It takes about 15 to 30 minutes, mostly downloading. No technical knowledge is needed.

### Step 1: Download AAGAM

1. Open **Microsoft Edge** or **Google Chrome** and go to **https://github.com/Anekant-Singhai/AAGAM**.
   If the page says "404" and the repository is private, sign in to GitHub first with an account that has access.
2. Click the green **Code** button, then **Download ZIP**.

### Step 2: Unzip it

1. Open your **Downloads** folder.
2. Right-click **AAGAM-main.zip** and choose **Extract All…**, then **Extract**.

Don't run anything from inside the ZIP without extracting it first.

### Step 3: Run the installer

The same steps are on one plain page in the folder: **START-HERE.txt**. Open that if you would rather not read this file.

1. Open the extracted folder **AAGAM-main**.
2. Double-click **install.cmd**.
3. If Windows shows **"Windows protected your PC"**, click **More info**, then **Run anyway**. (Windows says this about any program that isn't from the Microsoft Store.)

A black window opens and shows what it is doing:

- installing Python, if the laptop doesn't have it;
- installing AAGAM into `C:\Users\<you>\AppData\Local\Programs\AAGAM`;
- setting up your data folder, `C:\Users\<you>\AAGAM`;
- installing the local AI (Ollama and its model, about 3 GB);
- connecting AAGAM to Claude Desktop, if Claude Desktop is installed;
- putting **AAGAM**, **CS Desk browser** and **AAGAM Manager** on the desktop and in the Start menu;
- finally, a health check. When it says **AAGAM is ready**, press any key to close the window.

If the internet drops halfway, just double-click **install.cmd** again. It carries on from where it stopped.

You can delete the downloaded ZIP and the extracted folder afterwards. AAGAM doesn't need them any more.

### Step 4: Open AAGAM

Double-click **AAGAM** on the desktop (or press the Windows key and type **AAGAM**). It opens in your web browser at `http://127.0.0.1:8765`. That address is your own laptop, not a website.

### Installing with one line instead (public repository only)

If the repository is public, you can skip steps 1 to 3. Open **PowerShell** (Windows key, type *PowerShell*, Enter) and paste:

```
irm https://raw.githubusercontent.com/Anekant-Singhai/AAGAM/main/scripts/install.ps1 | iex
```

### Choosing what gets installed

Most people should just double-click **install.cmd**. To leave something out, open PowerShell in the extracted folder and run, for example:

```
.\install.cmd -NoLocalAI          # no local AI (saves about 3 GB)
.\install.cmd -NoClaude           # don't connect Claude Desktop
.\install.cmd -NoShortcuts        # no desktop or Start menu shortcuts
```

### Claude Desktop (optional)

To use AAGAM's tools from Claude, install Claude Desktop from **https://claude.ai/download** and sign in. Then, in AAGAM, open **Updates & health** and press **Fix** next to *Claude Desktop* (or run the installer again). Quit Claude Desktop completely (right-click its icon by the clock, **Quit**) and open it again.

---

## First steps in AAGAM

1. **Add your clients.** Open **Clients**, then **Add**. Give the name and the CIN (or the LLPIN for an LLP). Everything else can come later.
2. **Bring in your documents.** Open **Library** and choose **Add a folder**. Click **Browse…** and pick the folder where you keep client files. AAGAM shows how many files it found and what it can read. Choose how to file them:
   - **Work it out** (recommended): each document goes to the client whose CIN or LLPIN it carries, whose name its folder has (a folder called *Acme Widgets* matches *Acme Widgets Private Limited*), or whose name it is about.
   - **One client**: everything in the folder belongs to one client.
   - **Not a client's documents**: for law, circulars and the like.
   Tick **Keep watching this folder** to have new files picked up while AAGAM is open. Then press **Start**. You can carry on working: the folder is read in the background and the Library shows its progress.
3. **Drop files in.** Drag files, or whole folders, from Explorer onto the AAGAM window.
4. **Find documents.** Use the search box at the top (or **Ctrl+K**), or the filters in **Library**: financial year, from and to dates, client, folder, type of document and kind of file. **Group by** sorts the list into sections, for example by client or by financial year.
5. **MCA portal.** Open **CS Desk browser** from the desktop and log in to MCA yourself (captcha and OTP). AAGAM can then fill forms in that window. It always stops before submit, sign and pay; you do those.

### The Trash

Deleting a document moves it to the **Trash** (in the menu on the left). From there you can **Restore** it, with your corrections, tags, notes and links put back, or **Delete forever**. **Empty Trash** removes everything in it for good. Nothing is deleted for good without asking you first.

### LLPs

Add an LLP in **Clients** with its LLPIN (for example `AAB-1234`). AAGAM then:

- works out its due dates: Form 11 (30 May), Form 8 (30 October), Form 3 for the LLP agreement and its changes, Form 4 for partners joining or leaving, Form 15 for a new registered office, Form 5 for a change of name, LLP BEN-2, and DIR-3 KYC for designated partners. Each date shows the rule it comes from; items marked **check** need your confirmation;
- recognises LLP documents: LLP agreements and supplementary agreements, partners' resolutions, consents, and filed LLP forms;
- has LLP checklists in **Work**: incorporation, annual filing, partner changes, agreement changes, registered office, name change and strike off.

---

## Updates

AAGAM looks for a new version on GitHub by itself, shortly after it opens and every few hours. Once a day at 8:00, if AAGAM is closed, it installs a waiting update and stays closed until you open it. It never installs an update while you are in the middle of bringing documents in.

- When there is one, AAGAM shows **"A new version of AAGAM is ready"**. Press **Update now**. AAGAM closes for about a minute, updates itself, and comes back on its own.
- With **Install updates automatically** switched on (it is, unless you turn it off), AAGAM updates itself when it isn't busy reading anything.
- **Your documents and records are never touched by an update.** If anything goes wrong during an update, AAGAM puts the previous version back by itself.
- To check now: **Updates & health** → **Check for updates**. Or Start menu → **AAGAM Manager** → **Update**.
- After an update, if you use Claude Desktop, quit it and open it again so it gets the new version too. AAGAM reminds you.

**Private repository?** The laptop then needs an access key to see updates:

1. On GitHub (signed in as the owner), go to **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Choose **Only select repositories**, pick **AAGAM**, and under **Repository permissions** set **Contents** to **Read-only**. Generate it and copy it.
3. In AAGAM, open **Updates & health → Advanced**, paste it into **Access key**, and save. It is stored encrypted for your Windows account and never shown again.

---

## Health check and repairs

Open **Updates & health**. The **Health** list checks Python, the data folder, the database, the interface, the port, scanned-page reading (Windows OCR), Chrome or Edge, the local AI, Claude Desktop and disk space. Each line shows **OK**, **Worth a look** or **Needs fixing**, says what to do, and has a **Fix** button where AAGAM can fix it itself.

**If AAGAM won't open at all,** use the Start menu → **AAGAM Manager**. It is a small window with numbered choices:

```
 1  Open AAGAM
 2  Check for updates
 3  Update now
 4  Health check
 5  Repair (set AAGAM up again; your data is kept)
 6  Install or repair the local AI
 7  Connect Claude Desktop
 8  Set the update key (only for a private GitHub repository)
 9  Uninstall
10  Back up my data
11  Save a report for help
 0  Exit
```

Type the number and press Enter. The same window is **AAGAM Manager** on the desktop.

---

## Uninstall

Any of these works:

- Windows **Settings → Apps → Installed apps → AAGAM → Uninstall**;
- Start menu → **AAGAM Manager** → **Uninstall**;
- in AAGAM: **Updates & health → Uninstall**.

Uninstalling removes the program, its shortcuts and its entry in Claude Desktop. **Your data folder (`C:\Users\<you>\AAGAM`) is kept** unless you choose to remove it as well, which asks you to type REMOVE to be sure. Ollama (the local AI) and Claude Desktop are separate programs: remove them from **Settings → Apps** if you no longer want them.

---

## Where everything is

| What | Where |
|---|---|
| The program | `C:\Users\<you>\AppData\Local\Programs\AAGAM` |
| Your data: clients, documents, database, Trash, logs | `C:\Users\<you>\AAGAM` |
| Documents in the Trash | `C:\Users\<you>\AAGAM\bin` |
| Logs (or use **Save a report for help**, which packs these up) | `C:\Users\<you>\AAGAM\logs` and `%TEMP%\aagam-install.log` |
| Backups you make from **Back up my data** | `Documents\AAGAM backups` |

**Back up** by copying the whole `C:\Users\<you>\AAGAM` folder (close AAGAM first). Turning on Windows device encryption (or BitLocker) protects it if the laptop is lost.

**Moving to a new laptop:** install AAGAM on the new laptop, close it, then copy the `AAGAM` data folder from the old laptop into `C:\Users\<you>\` on the new one, replacing the empty one.

---

## When something goes wrong

| What you see | What to do |
|---|---|
| "Windows protected your PC" | Click **More info**, then **Run anyway**. |
| The installer stops with a download error | Check the internet connection and double-click **install.cmd** again. |
| AAGAM doesn't open from the desktop | Start menu → **AAGAM Manager** → **3 Health check**, then **4 Repair** if it finds a problem. |
| "The port is used by another program" | Close the other program, or restart the laptop. |
| Scanned PDFs aren't searchable | Windows **Settings → Time & language → Language & region → English (India) → Language options → Optical character recognition → Download**. The health check tells you when this is needed. |
| Claude Desktop doesn't show AAGAM | **Updates & health → Health → Claude Desktop → Fix**, then quit Claude Desktop from the tray and open it again. |
| No AI summaries | **Updates & health → Health → Local AI → Fix**. Everything else works without it. |
| An update failed | AAGAM has already gone back to the previous version. **Updates & health** shows what happened; try again later. |
| You need to ask someone for help | **Updates & health → Save a report for help**. A file appears on the Desktop. Send that file. It has no documents and no update key. |
| You want a copy of your work | **Updates & health → Back up my data**. The copy is in **Documents → AAGAM backups**, with a READ ME.txt that says how to put it back. |

---

## Privacy and safety

- AAGAM answers only on this laptop (`127.0.0.1`). Other computers and websites can't reach it.
- Client data stays in the data folder on the laptop. The local AI runs on the laptop too. Only what Claude Desktop reads goes to Claude.
- PAN, Aadhaar and passport numbers are masked everywhere AAGAM shows them.
- AAGAM never submits, signs or pays anything on a portal. You do.
- Updates replace only the program. They never read, send or change your data.

---

## For the maintainer: publishing and shipping updates

**First upload to GitHub**

```
git add -A
git commit -m "AAGAM 0.2.0"
git branch -M main
git remote add origin https://github.com/Anekant-Singhai/AAGAM.git
git push -u origin main
```

If the repository lives somewhere else, change the one line `$DefaultRepo = ...` near the top of `scripts\install.ps1`, and the links in this README, before pushing.

**Shipping an update:** change the code, rebuild the interface if `frontend\` changed (`.venv\Scripts\aagam build-ui`; the built files in `src\aagam\web\static` are what laptops run, so they never need Node.js), raise `__version__` in `src\aagam\__init__.py` (that is the version Windows and the window show; `pyproject.toml` reads it from there), run the tests, commit and push to `main`.

GitHub runs the tests in `.github/workflows/test.yml` on that push. Laptops install whatever is on `main`, so wait until the check is green. Laptops see the new commit within a few hours, at 8:00 if AAGAM is closed, or straight away with **Check for updates**. Work on another branch until it is ready.

**If a bad version went out:** revert that commit on `main` and push. Each laptop also keeps the previous version and puts it back by itself if an update fails to start. **AAGAM Manager → Repair** reinstalls the program and keeps the data folder.

The built interface (`src\aagam\web\static`) is kept in the repository so laptops never need Node.js.

## For developers

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest                 # browser tests use Chrome or Edge; one uses Ollama if it is running
.venv\Scripts\python -m pytest -m "not browser"  # without the browser tests
.venv\Scripts\aagam build-ui                   # rebuild the interface after changing frontend\ (needs Node.js, or .tools\node)
cd frontend; npm run dev                       # live-reloading interface against a running `aagam serve`
```

Use a throwaway data folder while developing: `$env:AAGAM_HOME = "$PWD\.dev-data"`. For Claude Code, `aagam claude-config` prints the server entry to put in a local `.mcp.json` (it isn't kept in the repository).

`aagam --help` lists the commands: `aagam` (open), `serve`, `mcp`, `init`, `add FILE-OR-FOLDER...`, `reindex`, `ai`, `doctor`, `update`, `uninstall`, `claude-config`, `build-ui`. [docs/AAGAM.md](docs/AAGAM.md) maps the whole system and what comes next; [docs/CSDESK.md](docs/CSDESK.md) covers the core.

**Docker** (optional, for a server; the laptop doesn't need it): `docker compose up -d` serves AAGAM on `http://127.0.0.1:8765` with its data in the `aagam-data` volume; `docker compose --profile ai up -d` adds Ollama (`docker compose exec ollama ollama pull qwen3:4b`). Windows OCR and MCA form filling aren't available in a container, and Claude Desktop uses the laptop install.
