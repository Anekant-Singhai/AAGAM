"""Entities across the whole library, and a dossier on each.

An entity is a person, company, DIN, CIN, GSTIN, audit firm or member of an
institute found in documents. Names are written many ways ("Mr. Dipesh
Godha", "DIPESH GODHA", "Godha Cabcon& Insulation Ltd."), so each is grouped
under a key: lower case, without titles, punctuation or "Private Limited"
spellings. A dossier brings together every document an entity appears in
(with pages and the words around it), the company-file records it matches,
its identifiers, the people and companies it appears with, and for a company
its resolutions and financial statements.
"""

from __future__ import annotations

import re
from typing import Any

from csdesk import validators
from csdesk.errors import Invalid, NotFound
from csdesk.vault import Vault, mask

KINDS = {
    "person": "People",
    "company": "Companies",
    "din": "DINs",
    "cin": "CINs",
    "llpin": "LLPINs",
    "gstin": "GSTINs",
    "frn": "Audit firms (FRN)",
    "membership_no": "Institute members",
    "email": "Email addresses",
}

STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh", "97": "Other Territory", "99": "Centre Jurisdiction",
}
CIN_STATES = {
    "AP": "Andhra Pradesh", "AS": "Assam", "BR": "Bihar", "CH": "Chandigarh", "CT": "Chhattisgarh", "DL": "Delhi", "GA": "Goa",
    "GJ": "Gujarat", "HP": "Himachal Pradesh", "HR": "Haryana", "JH": "Jharkhand", "JK": "Jammu and Kashmir", "KA": "Karnataka",
    "KL": "Kerala", "MH": "Maharashtra", "MP": "Madhya Pradesh", "OR": "Odisha", "PB": "Punjab", "PY": "Puducherry",
    "RJ": "Rajasthan", "TG": "Telangana", "TN": "Tamil Nadu", "UP": "Uttar Pradesh", "UR": "Uttarakhand", "WB": "West Bengal",
}


def key_of(kind: str, value: str) -> str:
    v = value.strip()
    if kind in ("person",):
        v = re.sub(r"(?i)^(mr|ms|mrs|miss|shri|smt|sri|kum|dr|ca|cs|adv)\.?\s+", "", v)
        return re.sub(r"[^a-z]+", " ", v.lower()).strip()
    if kind == "company":
        v = v.lower().replace("&", " and ")
        v = re.sub(r"\bpvt\.?\b", "private", v)
        v = re.sub(r"\bltd\.?\b", "limited", v)
        return re.sub(r"[^a-z0-9]+", " ", v).strip()
    return v.upper() if kind in ("cin", "llpin", "gstin", "frn", "membership_no") else v.lower()


def gstin_info(gstin: str) -> dict[str, Any]:
    """What a GSTIN says: state, the PAN inside it, which registration on that PAN it is."""
    value = validators.gstin(gstin)
    pan = value[2:12]
    return {
        "gstin": value,
        "state_code": value[:2],
        "state": STATES.get(value[:2], "unknown state code"),
        "pan": mask(pan),
        "pan_holder": validators.PAN_HOLDER.get(pan[3], "unknown"),
        "registration_no": value[12],
        "verify_url": "https://services.gst.gov.in/services/searchtp",
        "note": "Search this GSTIN on the GST portal to see its legal name, status and return filing; the portal doesn't search by name.",
    }


def cin_info(cin: str) -> dict[str, Any]:
    info = validators.parse_cin(cin)
    return {**info, "state": CIN_STATES.get(info["state_code"], info["state_code"])}


def _names(vault: Vault) -> dict[tuple[str, str], str]:
    return {(r["kind"], r["key"]): r["name"] for r in vault._rows("SELECT kind, key, name FROM entity_names")}


def browse(vault: Vault, kind: str | None = None, query: str = "", limit: int = 200) -> dict[str, Any]:
    """Entities grouped by key, with how many documents mention them."""
    if kind and kind not in KINDS:
        raise Invalid(f"Unknown kind {kind!r}; use one of: {', '.join(KINDS)}.")
    where, params = ["kind IN ({})".format(",".join("?" * len(KINDS)))], list(KINDS)
    if kind:
        where, params = ["kind = ?"], [kind]
    if query.strip():
        where.append("(value LIKE ? OR shown LIKE ? OR detail LIKE ?)")
        like = f"%{query.strip()}%"
        params += [like, like, like]
    rows = vault._rows(
        f"SELECT kind, value, shown, detail, document_id FROM mentions WHERE {' AND '.join(where)}", params
    )
    if kind in (None, "person"):
        # A name written next to a DIN is a person too, even without "Mr." or "Ms.".
        like = f"%{query.strip()}%"
        rows += vault._rows(
            "SELECT 'person' AS kind, detail AS value, detail AS shown, value AS detail, document_id FROM mentions "
            "WHERE kind = 'din' AND detail IS NOT NULL AND (? = '%%' OR detail LIKE ? OR value LIKE ?)",
            (like, like, like),
        )
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        k = key_of(r["kind"], r["value"])
        if not k:
            continue
        g = groups.setdefault((r["kind"], k), {"kind": r["kind"], "key": k, "name": r["value"], "detail": r["detail"], "documents": set(), "mentions": 0})
        g["documents"].add(r["document_id"])
        g["mentions"] += 1
        g["detail"] = g["detail"] or r["detail"]
        if r["kind"] in ("person", "company") and len(r["value"]) > len(g["name"]):
            g["name"] = r["value"]  # the fullest spelling
    names = _names(vault)
    for g in groups.values():
        g["name"] = names.get((g["kind"], g["key"]), g["name"])  # the name she chose, if she chose one
    out = sorted(groups.values(), key=lambda g: (-len(g["documents"]), -g["mentions"], g["name"]))
    for g in out:
        g["documents"] = len(g["documents"])
    counts: dict[str, int] = {}
    for kd, _ in groups:
        counts[kd] = counts.get(kd, 0) + 1
    return {"entities": out[:limit], "counts": counts, "total": len(out)}


def dossier(vault: Vault, kind: str, key: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise Invalid(f"Unknown kind {kind!r}.")
    rows = [r for r in vault._rows(
        """SELECT m.kind, m.value, m.shown, m.detail, m.page_no, m.context, m.document_id, d.original_name, d.doc_type,
                  dm.title, dm.meeting_date, d.ingested_at
           FROM mentions m JOIN documents d ON d.id = m.document_id LEFT JOIN doc_meta dm ON dm.document_id = d.id
           WHERE m.kind = ?""",
        (kind,),
    ) if key_of(kind, r["value"]) == key]

    # People are also found through their DIN: any DIN written next to their name, or theirs in the company file.
    # Every document carrying one of those DINs belongs in the dossier, however the name was written there.
    linked_dins: list[str] = []
    if kind == "person":
        all_dins = vault._rows(
            "SELECT m.kind, m.value, m.shown, m.detail, m.page_no, m.context, m.document_id, d.original_name, d.doc_type, "
            "dm.title, dm.meeting_date, d.ingested_at FROM mentions m JOIN documents d ON d.id = m.document_id "
            "LEFT JOIN doc_meta dm ON dm.document_id = d.id WHERE m.kind = 'din'"
        )
        named = {r["value"] for r in all_dins if r["detail"] and key_of("person", r["detail"]) == key}
        filed = {p["din"] for p in vault._rows("SELECT name, din FROM parties WHERE din IS NOT NULL") if key_of("person", p["name"]) == key}
        linked_dins = sorted(named | filed)
        rows += [r for r in all_dins if r["value"] in linked_dins]
    if not rows:
        raise NotFound("Nothing in the library matches that entity.")

    names = sorted({r["value"] for r in rows if r["kind"] == kind}, key=len, reverse=True)
    if kind == "person" and not names:
        names = sorted({r["detail"] for r in rows if r["detail"]}, key=len, reverse=True)
    name = _names(vault).get((kind, key)) or (names[0] if names else key)
    documents: dict[int, dict[str, Any]] = {}
    for r in rows:
        d = documents.setdefault(r["document_id"], {"document_id": r["document_id"], "title": r["title"] or r["original_name"],
                                                    "doc_type": r["doc_type"], "meeting_date": r["meeting_date"],
                                                    "added": r["ingested_at"][:10], "pages": [], "contexts": []})
        if r["page_no"] not in d["pages"]:
            d["pages"].append(r["page_no"])
        if len(d["contexts"]) < 3 and r["context"] not in d["contexts"]:
            d["contexts"].append({"page": r["page_no"], "text": r["context"]})

    out: dict[str, Any] = {"kind": kind, "key": key, "name": name, "spellings": names[:8], "chosen_name": _names(vault).get((kind, key))}
    doc_ids = list(documents)
    out["documents"] = sorted(documents.values(), key=lambda d: d["meeting_date"] or d["added"], reverse=True)
    out["identifiers"] = _identifiers(vault, kind, name, rows, linked_dins)
    out["company_file"] = _company_file(vault, kind, name, rows, linked_dins)
    out["appears_with"] = _appears_with(vault, doc_ids, kind, key)
    if kind in ("company", "cin", "llpin"):
        out["resolutions"] = _resolutions(vault, kind, name, rows)
        out["financials"] = _financials(vault, kind, name, out["company_file"])
    if kind == "gstin":
        out["gstin"] = gstin_info(name)
    if kind == "cin":
        out["cin"] = cin_info(name)
    return out


def _identifiers(vault: Vault, kind: str, name: str, rows: list[dict[str, Any]], dins: list[str]) -> dict[str, list[str]]:
    ids: dict[str, list[str]] = {}
    if kind == "person" and dins:
        ids["DIN"] = dins
    if kind == "din":
        people = sorted({r["detail"] for r in rows if r["detail"]})
        if people:
            ids["Named as"] = people
    if kind == "company" and rows:
        # A CIN is the company's when a document is mainly about that company; otherwise offer CINs seen alongside.
        about = vault._rows("SELECT DISTINCT company_cin FROM doc_meta WHERE company_cin IS NOT NULL AND lower(company_name) = lower(?)", (name,))
        if about:
            for a in about:
                ids.setdefault("LLPIN" if validators.is_llpin(a["company_cin"]) else "CIN", []).append(a["company_cin"])
        else:
            doc_ids = sorted({r["document_id"] for r in rows})
            marks = ",".join("?" * len(doc_ids))
            cins = sorted({r["value"] for r in vault._rows(f"SELECT value FROM mentions WHERE kind = 'cin' AND document_id IN ({marks})", doc_ids)})
            if cins:
                ids["CINs in the same documents"] = cins[:5]
    return ids


def _company_file(vault: Vault, kind: str, name: str, rows: list[dict[str, Any]], dins: list[str]) -> list[dict[str, Any]]:
    """Records in the company file that are this entity."""
    found: list[dict[str, Any]] = []
    if kind in ("person", "din"):
        din_values = dins if kind == "person" else [name]
        for din in din_values:
            for p in vault._rows("SELECT id, name, din FROM parties WHERE din = ?", (din,)):
                found.append({"type": "party", **p, "appointments": vault.party(p["id"])["appointments"]})
        if kind == "person" and not found:
            for p in vault._rows("SELECT id, name, din FROM parties WHERE kind = 'individual'"):
                if key_of("person", p["name"]) == key_of("person", name):
                    found.append({"type": "party", **p, "appointments": vault.party(p["id"])["appointments"]})
    if kind in ("company", "cin", "llpin"):
        for c in vault._rows("SELECT id, name, cin, entity_type, company_class, status FROM companies"):
            if (kind in ("cin", "llpin") and c["cin"] == name) or (kind == "company" and key_of("company", c["name"]) == key_of("company", name)):
                found.append({"type": "company", **c})
    if kind == "gstin":
        for r in vault._rows("SELECT r.company_id, c.name, c.cin FROM registrations r JOIN companies c ON c.id = r.company_id WHERE r.kind = 'gstin' AND r.number = ?", (name,)):
            found.append({"type": "company", "id": r["company_id"], "name": r["name"], "cin": r["cin"]})
        pan = name[2:12]
        for c in vault._rows("SELECT id, name, cin FROM companies WHERE pan = ?", (pan,)):
            if not any(f.get("id") == c["id"] for f in found):
                found.append({"type": "company", **c, "matched_by": "the PAN inside the GSTIN"})
    if kind == "frn":
        for p in vault._rows("SELECT id, name, frn FROM parties WHERE frn = ?", (name,)):
            found.append({"type": "party", **p})
    return found


def _appears_with(vault: Vault, doc_ids: list[int], kind: str, key: str) -> list[dict[str, Any]]:
    if not doc_ids:
        return []
    marks = ",".join("?" * len(doc_ids))
    counts: dict[tuple[str, str], dict[str, Any]] = {}
    for r in vault._rows(
        f"SELECT kind, value, detail, document_id FROM mentions WHERE document_id IN ({marks}) AND kind IN ('person', 'company', 'din', 'frn')", doc_ids
    ):
        k = key_of(r["kind"], r["value"])
        if (r["kind"], k) == (kind, key) or not k:
            continue
        entry = counts.setdefault((r["kind"], k), {"kind": r["kind"], "key": k, "name": r["value"], "detail": r["detail"], "documents": set()})
        entry["documents"].add(r["document_id"])
        if len(r["value"]) > len(entry["name"]):
            entry["name"] = r["value"]
    ranked = sorted(counts.values(), key=lambda e: -len(e["documents"]))[:20]
    for e in ranked:
        e["documents"] = len(e["documents"])
    return ranked


def _resolutions(vault: Vault, kind: str, name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if kind in ("cin", "llpin"):
        docs = vault._rows("SELECT document_id FROM doc_meta WHERE company_cin = ?", (name,))
        ids = [d["document_id"] for d in docs]
        if not ids:
            return []
        return vault._rows(
            "SELECT id, document_id, item_no, title, resolution_kind, sections, max_amount, meeting_date FROM clauses WHERE document_id IN ({}) ORDER BY meeting_date DESC, item_no".format(",".join("?" * len(ids))),
            ids,
        )
    return [r for r in vault._rows(
        "SELECT id, document_id, item_no, title, resolution_kind, sections, max_amount, meeting_date, company_name FROM clauses WHERE company_name IS NOT NULL ORDER BY meeting_date DESC, item_no"
    ) if key_of("company", r["company_name"]) == key_of("company", name)]


def _financials(vault: Vault, kind: str, name: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [r["id"] for r in records if r["type"] == "company"]
    rows = vault._rows("SELECT id, document_id, basis, period_end, company_name, company_id FROM financials")
    return [r for r in rows if (r["company_id"] in ids) or (r["company_name"] and key_of("company", r["company_name"]) == key_of("company", name))]
