"""Which form recipes exist, and how each one's values are gathered from the company file.

Recipes for real MCA forms are added here one at a time, each recorded against
the live portal with her logged in, on a draft that is never submitted.
DEMO-1 fills the bundled practice page, so the whole loop can be tried
without touching MCA.
"""

from __future__ import annotations

from typing import Any

from ..errors import NotFound
from ..vault import Vault
from .recipe import Field, Recipe

DEMO = Recipe(
    code="DEMO-1",
    title="Practice form (not an MCA form)",
    url_contains="demo_form.html",
    page_marker="DEMO-1",
    fields=(
        Field("company.cin", "Corporate Identification Number (CIN)"),
        Field("company.name", "Name of the company"),
        Field("party.din", "Director Identification Number (DIN)"),
        Field("party.name", "Name of the director"),
        Field("party.pan", "Income-tax PAN of the director", sensitive=True),
        Field("extra.date_of_appointment", "Date of appointment", kind="date"),
        Field("extra.designation", "Designation", kind="select"),
        Field(
            "extra.is_shareholder",
            "Is the director also a shareholder?",
            kind="radio",
            selector='input[type=radio][name="shareholder"]',
            required=False,
        ),
    ),
    save_button="Save as draft",
    recorded_on="2026-10-09",
)

RECIPES: dict[str, Recipe] = {recipe.code: recipe for recipe in (DEMO,)}


def recipe_for(form: str) -> Recipe:
    recipe = RECIPES.get(form.upper())
    if recipe is None:
        raise NotFound(
            f"There is no recipe for {form} yet (recipes so far: {', '.join(sorted(RECIPES))}). Record her filling it "
            "once on a draft (record_start, then record_stop) to draft one; until then she fills it by hand from "
            "get_company."
        )
    return recipe


def build_values(
    vault: Vault, filing: dict[str, Any], party_id: int | None = None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Values a recipe can use: company.*, party.* and extra.*.

    Party values are unmasked here because they are typed into the portal.
    They go from the company file straight to the page and are never returned to Claude.
    """
    values = {f"company.{k}": v for k, v in vault.company_row(filing["company_id"]).items() if v is not None}
    if party_id is not None:
        party = vault.party(party_id, reveal=True)
        values |= {f"party.{k}": v for k, v in party.items() if v is not None and k != "appointments"}
    values |= {f"extra.{k}": v for k, v in (extra or {}).items()}
    return values
