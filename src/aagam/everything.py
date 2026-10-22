"""One search across all of AAGAM: pages, resolutions, people and companies, the company file, financial statements."""

from __future__ import annotations

from typing import Any

from csdesk.errors import Invalid
from csdesk.vault import Vault

from . import entities, finance, library, precedents, workbook


def search_all(vault: Vault, query: str, limit: int = 6) -> dict[str, Any]:
    q = query.strip()
    if not q:
        raise Invalid("Type a word or two to search for.")
    try:
        docs = library.search(vault, q, limit=limit)
        resolutions = precedents.search(vault, q, limit=limit)["resolutions"]
    except Invalid:
        docs, resolutions = {"documents": [], "matching_documents": 0}, []
    found = entities.browse(vault, None, q, limit=limit * 2)["entities"]
    compact = q.replace(" ", "").upper()
    companies = vault.find_companies(q)[:limit]
    parties = vault.find_parties(q)[:limit] if len(q) >= 2 else []
    statements = [f for f in finance.listing(vault) if q.lower() in (f["company_name"] or f["client"] or "").lower()][:limit]
    try:
        found_notes = workbook.search_notes(vault, q, limit)
    except Invalid:
        found_notes = []
    works = workbook.list_works(vault, query=q)[:limit]
    return {
        "notes": found_notes,
        "works": works,
        "query": q,
        "documents": docs["documents"],
        "document_count": docs["matching_documents"],
        "resolutions": resolutions,
        "entities": found,
        "companies": companies,
        "people": parties,
        "financials": statements,
        "looks_like": _looks_like(compact),
    }


def _looks_like(value: str) -> str | None:
    """Name the identifier she typed, so the interface can say "that's a CIN" and offer its dossier."""
    from csdesk import validators

    for name, check in (("cin", validators.cin), ("gstin", validators.gstin), ("din", validators.din), ("pan", validators.pan)):
        try:
            check(value)
            return name
        except Exception:
            continue
    return None
