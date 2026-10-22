# AAGAM

A Company Secretary's workbench that runs on her own laptop:

- **Library:** PDF (scans too, by Windows OCR), Word, Excel, PowerPoint, Outlook, RTF, HTML and more: kept, read and tagged, with full-text search and facts (CIN, DIN with the person, amounts, dates, sections)
- **Search everything** (Ctrl+K), and **dossiers** on every person, company, DIN, CIN and GSTIN named in the library
- **Financial statements:** Schedule III figures read from the accounts, the 11 ratios, where the money comes from, and what the figures make apply
- **Work register** with checklists citing the Act and SS-1/SS-2, **notes** on anything, and a **notice checker**
- **Precedents:** resolutions and explanatory statements from every notice, by section, topic and amount
- **Company file (Clients):** clients, directors and KMP, meetings, filings, charges and more, with every value tied to its source; all of it editable in the window
- **Corrections that last:** fix a misread page, a fact, a resolution, a tag or the accounts' unit, and re-reading keeps your fix; delete anything, with the file kept in a bin folder
- **Due dates** with their legal basis, and **calculators** (s.186, s.180, s.185)
- **Drafting, law desk and dossiers**
- **MCA form filling** in her own logged-in browser, stopping before submit
- **Local AI** summaries (Ollama) and **Claude Desktop** tools over the same data
- Light, **Night light** and Dark themes

[docs/AAGAM.md](docs/AAGAM.md) is the map: everything a CS does, which part handles it, and what's next. [docs/CSDESK.md](docs/CSDESK.md) covers the core.

## Install

### Her laptop (Windows)

You need Python 3.11+ (from python.org, with "Add python.exe to PATH" ticked) and Chrome or Edge. For local AI, also install Ollama (ollama.com). Then run:

```
scripts\setup-windows.cmd -ConfigureClaude -DesktopShortcut -LocalAI
```

All three switches are optional:

- `-ConfigureClaude` adds AAGAM to Claude Desktop, backing up its config first.
- `-DesktopShortcut` puts **AAGAM** and **CS Desk browser** shortcuts on the desktop.
- `-LocalAI` downloads the AI model (`-Model qwen3:4b` is the default).

The script ends by running `aagam doctor`. Open AAGAM from the **AAGAM** desktop shortcut. Client data lives in `%USERPROFILE%\AAGAM`; set `AAGAM_HOME` to use another folder.

To check the setup at any time, run `.venv\Scripts\aagam doctor`. It checks Python, the data folder, the database, the interface, the port, Windows OCR, Chrome/Edge, Ollama, Claude Desktop and disk space. Each line is ✓ (fine), ! (optional, or works with less) or ✗ (needs fixing), and every problem comes with a fix.

### Developers

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
.venv\Scripts\aagam build-ui        # rebuild the interface after changing frontend/ (needs Node.js)
```

### Docker (optional: a server or another machine)

Her laptop doesn't need Docker. To run AAGAM in a container:

```
docker compose up -d                  # AAGAM at http://127.0.0.1:8765, data in the "aagam-data" volume
docker compose --profile ai up -d     # also an Ollama container for local AI
docker compose exec ollama ollama pull qwen3:4b
```

Inside the container AAGAM listens on all addresses (`AAGAM_BIND=0.0.0.0`). The port is published only on the host's `127.0.0.1`, and AAGAM answers only requests addressed to `127.0.0.1` or `localhost`. To reach it from another computer, use an SSH tunnel; don't change the port mapping. The container has some limits:

- Windows OCR isn't available on Linux, so scanned pages aren't read. Text PDFs and Office files are.
- MCA form filling needs her own desktop browser, so it doesn't work in the container.
- Claude Desktop runs on her laptop, so it uses the laptop install, not the container.
