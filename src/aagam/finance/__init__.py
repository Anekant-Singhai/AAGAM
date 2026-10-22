"""Financial statements: read the figures, keep her corrections, work out ratios and what applies."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault

from .. import layout, ocr
from . import applicability, ratios, statements
from .statements import CATALOGUE, LABELS

# Where each part of the statements begins, for showing the lines under their Schedule III headings.
GROUP_STARTS = {
    "share_capital": "Equity",
    "long_term_borrowings": "Non-current liabilities",
    "short_term_borrowings": "Current liabilities",
    "ppe": "Non-current assets",
    "inventories": "Current assets",
    "revenue": "Income",
    "materials": "Expenses",
    "exceptional_items": "Profit",
}


def statement_pages(vault: Vault, document_id: int, home: Path | None = None) -> list[tuple[int, str]]:
    """The statement pages, as rows: from the PDF's text positions, or from OCR word boxes for scans."""
    doc = vault.conn.execute("SELECT stored_path, media_type FROM documents WHERE id = ?", (document_id,)).fetchone()
    rows = vault._rows("SELECT page_no, text, needs_vision FROM document_pages WHERE document_id = ? ORDER BY page_no", (document_id,))
    from ..editing import edited_pages

    hers = edited_pages(vault, document_id)
    pages = []
    for r in rows:
        text = r["text"]
        if r["page_no"] in hers:
            pages.append((r["page_no"], text))  # she corrected this page; her text is what counts
            continue
        # Scanned PDFs often carry a text layer in a muddled order, with the heading far from the top, so any page
        # naming a statement is rebuilt as rows; the heading is then checked on the rows.
        mentions_statement = statements.BALANCE_SHEET.search(text) or statements.PROFIT_LOSS.search(text)
        if home is not None and doc["media_type"] == "application/pdf" and mentions_statement:
            path = home / doc["stored_path"]
            try:
                if r["needs_vision"] and ocr.available():
                    text = layout.ocr_rows(ocr.page_image(path, r["page_no"]))
                elif not r["needs_vision"]:
                    text = layout.pdf_rows(path, r["page_no"])
            except Exception:  # fall back to the plain text layer
                text = r["text"]
        pages.append((r["page_no"], text))
    return pages


def extract(vault: Vault, document_id: int, home: Path | None = None) -> list[int]:
    """Read the statements in a document into `financials`, replacing earlier automatic readings. Returns their ids."""
    found = statements.read_statements(statement_pages(vault, document_id, home))
    doc = vault.conn.execute(
        "SELECT d.company_id, m.company_name FROM documents d LEFT JOIN doc_meta m ON m.document_id = d.id WHERE d.id = ?", (document_id,)
    ).fetchone()
    kept = {}
    for r in vault._rows("SELECT id, basis, items, overrides FROM financials WHERE document_id = ?", (document_id,)):
        overrides = json.loads(r["overrides"]) if r["overrides"] else {}
        kept[overrides.get("read_basis", r["basis"])] = {**r, "overrides": overrides}
    dismissed = {r["basis"] for r in vault._rows("SELECT basis FROM dismissed_financials WHERE document_id = ?", (document_id,))}
    ids = []
    for st in found:
        if len(st.items) < 3 or st.basis in dismissed:
            continue  # a passing mention of a balance sheet, or statements she deleted
        old = kept.get(st.basis)
        items = st.items
        if old:
            # Keep what she corrected; refresh the rest.
            overrides = old["overrides"]
            factor = overrides.get("unit_factor")
            if factor and factor != st.unit_factor:
                # She said the figures are in another unit than the one read: scale what was read to hers.
                items = {k: {**v, **{c: round(v[c] * factor / st.unit_factor) for c in ("current", "previous") if v.get(c) is not None}}
                         for k, v in items.items()}
            mine = {k: v for k, v in json.loads(old["items"]).items() if v.get("by") == "her"}
            items = {**items, **mine}
            header = {"period_end": st.period_end, "prior_period_end": st.prior_period_end, "unit": st.unit, "unit_factor": st.unit_factor,
                      "company_name": doc["company_name"]}
            header.update({k: v for k, v in overrides.items() if k in header})
            vault.conn.execute(
                """UPDATE financials SET period_end = ?, prior_period_end = ?, unit = ?, unit_factor = ?, items = ?,
                   company_name = COALESCE(?, company_name), company_id = COALESCE(company_id, ?), updated_at = datetime('now') WHERE id = ?""",
                (header["period_end"], header["prior_period_end"], header["unit"], header["unit_factor"], json.dumps(items),
                 header["company_name"], doc["company_id"], old["id"]),
            )
            ids.append(old["id"])
        else:
            ids.append(vault.conn.execute(
                """INSERT INTO financials (document_id, company_id, company_name, basis, period_end, prior_period_end, unit, unit_factor, items)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (document_id, doc["company_id"], doc["company_name"], st.basis, st.period_end, st.prior_period_end, st.unit,
                 st.unit_factor, json.dumps(items)),
            ).lastrowid)
    return ids


def get(vault: Vault, financial_id: int) -> dict[str, Any]:
    row = vault.conn.execute(
        """SELECT f.*, d.original_name, c.name AS client, c.company_class, c.is_listed, c.is_section8
           FROM financials f LEFT JOIN documents d ON d.id = f.document_id LEFT JOIN companies c ON c.id = f.company_id WHERE f.id = ?""",
        (financial_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"There are no financial statements {financial_id}.")
    out = dict(row)
    out["items"] = json.loads(out["items"])
    out["facts"] = json.loads(out["facts"]) if out["facts"] else {}
    return out


def analysis(vault: Vault, financial_id: int) -> dict[str, Any]:
    fin = get(vault, financial_id)
    result = ratios.analyse(fin["items"], fin["facts"].get("principal_repaid"))
    company = {"company_class": fin.get("company_class") or fin["facts"].get("company_class"), "is_listed": fin.get("is_listed"),
               "is_section8": fin.get("is_section8")}
    if not company["company_class"] and fin["document_id"]:
        # Not in the company file: the CIN printed in the document says private, public or OPC, and listed or not.
        cin = vault.conn.execute(
            "SELECT value FROM mentions WHERE document_id = ? AND kind = 'cin' ORDER BY page_no LIMIT 1", (fin["document_id"],)
        ).fetchone()
        if cin:
            from csdesk.validators import parse_cin

            parsed = parse_cin(cin["value"])
            company.update(company_class=parsed["company_class"], is_listed=parsed["listed"], is_section8=parsed["is_section8"])
            result["class_from_cin"] = cin["value"]
    result["applicability"] = applicability.assess(company, result["derived"]["current"], fin["facts"])
    result["statement"] = {k: fin[k] for k in ("id", "document_id", "company_id", "company_name", "client", "basis", "period_end",
                                               "prior_period_end", "unit", "unit_factor", "original_name")}
    # Every Schedule III line in order, so a missing one shows as missing and she can fill it in.
    result["items"] = []
    group = None
    for key, label, statement, *_ in CATALOGUE:
        group = GROUP_STARTS.get(key, group)
        found = fin["items"].get(key)
        result["items"].append({"key": key, "label": label, "statement": statement, "group": group, "found": found is not None,
                                **(found or {"current": None, "previous": None, "page": None, "by": None})})
    result["facts"] = fin["facts"]
    return result


def correct(vault: Vault, financial_id: int, key: str, current: int | None, previous: int | None) -> dict[str, Any]:
    """She corrects (or adds) one line. Her figures survive re-reading the document."""
    if key not in LABELS:
        raise Invalid(f"Unknown line {key!r}; use one of: {', '.join(LABELS)}.")
    fin = get(vault, financial_id)
    item = fin["items"].get(key, {"label": LABELS[key], "page": None})
    item.update({"current": current, "previous": previous, "by": "her"})
    fin["items"][key] = item
    vault.conn.execute("UPDATE financials SET items = ?, updated_at = datetime('now') WHERE id = ?", (json.dumps(fin["items"]), financial_id))
    vault.log("correct financials", {"id": financial_id, "line": key})
    return analysis(vault, financial_id)


FACT_KEYS = {"company_class", "listed", "holding_or_subsidiary", "bank_borrowings", "deposits", "principal_repaid"}


def set_facts(vault: Vault, financial_id: int, facts: dict[str, Any]) -> dict[str, Any]:
    unknown = set(facts) - FACT_KEYS
    if unknown:
        raise Invalid(f"Unknown facts: {', '.join(sorted(unknown))}.")
    current = get(vault, financial_id)["facts"]
    current.update({k: v for k, v in facts.items()})
    current = {k: v for k, v in current.items() if v is not None}
    vault.conn.execute("UPDATE financials SET facts = ?, updated_at = datetime('now') WHERE id = ?", (json.dumps(current), financial_id))
    return analysis(vault, financial_id)


UNITS = {"rupees": ("₹", 1), "thousands": ("₹ in thousands", 1_000), "lakhs": ("₹ in lakhs", 100_000),
         "millions": ("₹ in millions", 1_000_000), "crore": ("₹ in crore", 10_000_000)}
HEADER_FIELDS = {"company_name", "basis", "period_end", "prior_period_end", "unit"}


def edit_header(vault: Vault, financial_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    """She corrects what the statements are: whose, which basis, which years, which unit. Kept through re-reading."""
    unknown = set(changes) - HEADER_FIELDS
    if unknown:
        raise Invalid(f"Unknown field: {', '.join(sorted(unknown))}.")
    fin = get(vault, financial_id)
    row = vault.conn.execute("SELECT overrides FROM financials WHERE id = ?", (financial_id,)).fetchone()
    overrides = json.loads(row["overrides"]) if row["overrides"] else {}
    sets: dict[str, Any] = {}
    if "basis" in changes:
        if changes["basis"] not in ("standalone", "consolidated"):
            raise Invalid("Basis is standalone or consolidated.")
        overrides.setdefault("read_basis", fin["basis"])
        sets["basis"] = changes["basis"]
    for key in ("period_end", "prior_period_end"):
        if key in changes:
            value = changes[key] or None
            if value:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise Invalid("Give the date as YYYY-MM-DD.") from exc
            sets[key] = overrides[key] = value
    if "company_name" in changes:
        sets["company_name"] = overrides["company_name"] = (changes["company_name"] or "").strip() or None
    if "unit" in changes:
        if changes["unit"] not in UNITS:
            raise Invalid(f"The unit is one of: {', '.join(UNITS)}.")
        label, factor = UNITS[changes["unit"]]
        old = fin["unit_factor"] or 1
        if factor != old:
            # Every figure is kept in rupees, so a change of unit rescales them all.
            for item in fin["items"].values():
                for column in ("current", "previous"):
                    if item.get(column) is not None:
                        item[column] = round(item[column] * factor / old)
            sets["items"] = json.dumps(fin["items"])
        sets["unit"] = overrides["unit"] = label
        sets["unit_factor"] = overrides["unit_factor"] = factor
    sets["overrides"] = json.dumps(overrides)
    assignments = ", ".join(f"{k} = ?" for k in sets)
    vault.conn.execute(f"UPDATE financials SET {assignments}, updated_at = datetime('now') WHERE id = ?", (*sets.values(), financial_id))
    vault.log("edit financials", {"id": financial_id, "fields": sorted(changes)})
    return analysis(vault, financial_id)


def delete(vault: Vault, financial_id: int) -> dict[str, Any]:
    fin = get(vault, financial_id)
    if fin["document_id"]:
        row = vault.conn.execute("SELECT overrides FROM financials WHERE id = ?", (financial_id,)).fetchone()
        read_basis = (json.loads(row["overrides"]) if row["overrides"] else {}).get("read_basis", fin["basis"])
        vault.conn.execute("INSERT OR IGNORE INTO dismissed_financials (document_id, basis) VALUES (?, ?)", (fin["document_id"], read_basis))
    vault.conn.execute(
        "UPDATE notes SET target_kind = 'general', target = '', text = ? || char(10) || text WHERE target_kind = 'financials' AND target = ?",
        (f"On the deleted statements of {fin['company_name'] or fin['client'] or 'a company'}:", str(financial_id)),
    )
    vault.conn.execute("DELETE FROM financials WHERE id = ?", (financial_id,))
    vault.log("delete financials", {"id": financial_id})
    return {"deleted": financial_id}


def link_company(vault: Vault, financial_id: int, company_id: int | None) -> dict[str, Any]:
    vault.conn.execute("UPDATE financials SET company_id = ? WHERE id = ?", (company_id, financial_id))
    return analysis(vault, financial_id)


def listing(vault: Vault, company_id: int | None = None) -> list[dict[str, Any]]:
    sql = """SELECT f.id, f.document_id, f.company_id, f.company_name, f.basis, f.period_end, f.unit, d.original_name, c.name AS client
             FROM financials f LEFT JOIN documents d ON d.id = f.document_id LEFT JOIN companies c ON c.id = f.company_id"""
    params: tuple[Any, ...] = ()
    if company_id is not None:
        sql += " WHERE f.company_id = ?"
        params = (company_id,)
    return vault._rows(sql + " ORDER BY f.period_end DESC, f.id DESC", params)


def s186_inputs(vault: Vault, financial_id: int) -> dict[str, int | None]:
    """The figures the s.186 calculator needs. Securities premium sits inside other equity and needs the notes."""
    now = ratios.derived(get(vault, financial_id)["items"], "current")
    paid_up = now["share_capital"]
    equity = now["equity"]
    return {
        "paid_up_capital": round(paid_up) if paid_up is not None else None,
        "free_reserves": round(equity - paid_up) if equity is not None and paid_up is not None else None,
        "securities_premium": 0,
        "outstanding_borrowing": round(now["borrowings"]) if now["borrowings"] is not None else None,
    }
