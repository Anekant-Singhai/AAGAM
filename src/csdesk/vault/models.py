"""What can be written to the company file, and how each value is checked.

These models are the single definition of every field: the vault writes them
to SQLite, and the MCP tools publish them to Claude as the input schema.
Every field is optional so the same model serves create and update; the
vault says which fields a new record needs.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from .. import validators as v

CinOrLlpin = Annotated[str, BeforeValidator(v.cin_or_llpin)]
Pan = Annotated[str, BeforeValidator(v.pan)]
Tan = Annotated[str, BeforeValidator(v.tan)]
Din = Annotated[str, BeforeValidator(v.din)]
Aadhaar = Annotated[str, BeforeValidator(v.aadhaar)]
Pin = Annotated[str, BeforeValidator(v.pin)]
Mobile = Annotated[str, BeforeValidator(v.mobile)]
Email = Annotated[str, BeforeValidator(v.email)]
Day = Annotated[str, BeforeValidator(v.iso_date)]
FinYear = Annotated[str, BeforeValidator(v.fin_year)]
MonthDay = Annotated[str, BeforeValidator(v.month_day)]
Rupees = Annotated[int, BeforeValidator(v.rupees)]
FormCode = Annotated[str, AfterValidator(lambda s: " ".join(s.upper().split()))]

Role = Literal[
    "director",
    "managing_director",
    "whole_time_director",
    "additional_director",
    "alternate_director",
    "nominee_director",
    "independent_director",
    "ceo",
    "cfo",
    "company_secretary",
    "manager",
    "designated_partner",
    "partner",
]
DIRECTOR_ROLES = frozenset(
    {
        "director",
        "managing_director",
        "whole_time_director",
        "additional_director",
        "alternate_director",
        "nominee_director",
        "independent_director",
    }
)
FilingStatus = Literal[
    "planned", "in_progress", "ready_for_review", "submitted", "approved", "resubmission", "rejected", "cancelled"
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceIn(Input):
    """Where the values came from. Required on every write."""

    kind: Literal["document", "user", "portal", "derived", "import"] = Field(
        description=(
            "document: read from a stored document (give document_id, page and quote); "
            "user: she said so; portal: seen on the MCA/GST portal; derived: worked out from other data; "
            "import: bulk import from another system"
        )
    )
    document_id: int | None = None
    page: int | None = Field(None, ge=1, description="Page number in the stored document, starting at 1")
    quote: str | None = Field(None, max_length=1000, description="The exact words on the page that support the values")
    note: str | None = None

    @model_validator(mode="after")
    def _document_needs_page(self) -> SourceIn:
        if self.kind == "document" and (self.document_id is None or self.page is None):
            raise ValueError("a document source needs document_id and page")
        return self


class CompanyIn(Input):
    """A company or LLP. Pass only the fields you are setting."""

    entity_type: Literal["company", "llp"] | None = Field(None, description="Worked out from the CIN/LLPIN if omitted")
    cin: CinOrLlpin | None = Field(None, description="CIN (21 characters) or LLPIN (e.g. AAB-1234)")
    name: str | None = None
    company_class: Literal["private", "public", "opc"] | None = None
    category: Literal["limited_by_shares", "limited_by_guarantee", "unlimited"] | None = None
    subcategory: str | None = Field(
        None, description="e.g. non-government, union government, state government, subsidiary of foreign company"
    )
    is_listed: bool | None = None
    is_small_company: bool | None = Field(None, description="Small company under s.2(85); confirm with her each year")
    is_section8: bool | None = None
    is_nbfc: bool | None = None
    status: (
        Literal["active", "dormant", "under_strike_off", "struck_off", "amalgamated", "under_liquidation", "dissolved"]
        | None
    ) = None
    date_of_incorporation: Day | None = None
    roc: str | None = Field(None, description="Registrar of Companies, e.g. RoC-Mumbai")
    nic_code: str | None = None
    ro_line1: str | None = Field(None, description="Registered office address, line 1")
    ro_line2: str | None = None
    ro_city: str | None = None
    ro_district: str | None = None
    ro_state: str | None = None
    ro_pin: Pin | None = None
    email: Email | None = None
    phone: str | None = None
    website: str | None = None
    pan: Pan | None = Field(None, description="The company's own PAN (4th letter C; F for an LLP)")
    tan: Tan | None = None
    authorised_capital: Rupees | None = Field(None, description="Whole rupees")
    paid_up_capital: Rupees | None = Field(None, description="Whole rupees")
    fy_end: MonthDay | None = Field(None, description="MM-DD. 03-31 unless the Tribunal approved another year end")
    msme_return_applicable: bool | None = Field(
        None, description="True if it owes micro/small suppliers for more than 45 days (half-yearly MSME-1)"
    )
    dpt3_applicable: bool | None = Field(
        None, description="False only for companies outside the Deposit Rules (e.g. banks, NBFCs, government companies)"
    )
    notes: str | None = None


class PartyIn(Input):
    """A person (director, KMP, shareholder, auditor) or an organisation (audit firm, bank, holding company)."""

    kind: Literal["individual", "organisation"] | None = None
    name: str | None = Field(None, description="Full name as on PAN for a person; registered name for an organisation")
    father_name: str | None = None
    dob: Day | None = None
    gender: Literal["male", "female", "transgender"] | None = None
    nationality: str | None = None
    occupation: str | None = None
    din: Din | None = None
    pan: Pan | None = Field(
        None, description="Shown masked in replies. Better: she types it locally with `csdesk set-sensitive`"
    )
    aadhaar: Aadhaar | None = Field(None, description="Shown masked in replies. Better typed locally with `csdesk set-sensitive`")
    passport_no: str | None = None
    email: Email | None = None
    mobile: Mobile | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    district: str | None = None
    state: str | None = None
    pin: Pin | None = None
    country: str | None = None
    org_type: Literal["audit_firm", "bank", "company", "llp", "government", "other"] | None = None
    org_cin: CinOrLlpin | None = Field(None, description="CIN or LLPIN when the organisation is a company or LLP")
    frn: str | None = Field(None, description="ICAI firm registration number of an audit firm")
    membership_no: str | None = Field(None, description="ICSI / ICAI / ICMAI membership number")
    professional_body: Literal["ICSI", "ICAI", "ICMAI"] | None = None
    cop_no: str | None = Field(None, description="Certificate of practice number")
    kyc_next_due: Day | None = Field(
        None,
        description="Next periodic DIR-3 KYC date. Under Rule 12A as substituted from 31-03-2026 it is once in three "
        "financial years, by 30 June; changes of mobile, email or address are reported within 30 days",
    )
    notes: str | None = None


class AppointmentIn(Input):
    """A person's position in a company: director, KMP, or designated partner of an LLP."""

    company_id: int | None = None
    party_id: int | None = None
    role: Role | None = None
    category: (
        Literal["promoter", "professional", "independent", "nominee", "executive", "non_executive"] | None
    ) = None
    date_of_appointment: Day | None = None
    date_of_cessation: Day | None = None
    cessation_reason: (
        Literal["resignation", "removal", "death", "disqualification", "vacation", "completion_of_term", "other"]
        | None
    ) = None
    meeting_id: int | None = Field(None, description="The meeting that approved it, if recorded")
    notes: str | None = None


class MeetingIn(Input):
    company_id: int | None = None
    kind: Literal["board", "agm", "egm", "committee", "postal_ballot"] | None = None
    committee: str | None = Field(None, description="Committee name when kind is committee, e.g. Audit Committee")
    serial_no: str | None = None
    date: Day | None = None
    time: str | None = None
    venue: str | None = None
    mode: Literal["physical", "video_conference", "hybrid"] | None = None
    fy: FinYear | None = Field(
        None, description="Financial year it relates to, e.g. 2025-26 (for an AGM: the year whose accounts it adopted)"
    )
    notes: str | None = None


class ResolutionIn(Input):
    company_id: int | None = None
    meeting_id: int | None = Field(None, description="Leave empty for a circular resolution")
    kind: Literal["board", "circular", "ordinary", "special"] | None = None
    subject: str | None = None
    text: str | None = None
    passed_on: Day | None = None
    section_ref: str | None = Field(None, description="Section relied on, e.g. 180(1)(c)")
    mgt14_required: bool | None = Field(
        None,
        description="Special resolutions are always filed in MGT-14; set true for other resolutions that must be "
        "filed (e.g. a public company's board resolutions under s.179(3))",
    )
    notes: str | None = None


class AuditorAppointmentIn(Input):
    company_id: int | None = None
    auditor_id: int | None = Field(None, description="Party id of the audit firm or individual auditor")
    audit_type: Literal["statutory", "secretarial", "cost", "internal", "tax"] | None = None
    appointment_kind: Literal["first", "regular", "reappointment", "casual_vacancy"] | None = None
    appointed_on: Day | None = None
    meeting_id: int | None = Field(None, description="The AGM or board meeting that appointed the auditor")
    from_fy: FinYear | None = None
    to_fy: FinYear | None = None
    ended_on: Day | None = None
    end_reason: str | None = None
    notes: str | None = None


class ChargeIn(Input):
    company_id: int | None = None
    holder_id: int | None = Field(None, description="Party id of the charge holder (usually a bank)")
    charge_id: str | None = Field(None, description="Charge ID allotted by MCA")
    amount: Rupees | None = None
    created_on: Day | None = None
    modified_on: Day | None = None
    satisfied_on: Day | None = None
    property: str | None = Field(None, description="Short description of the property charged")
    notes: str | None = None


class EventIn(Input):
    """Company events that start a filing clock and aren't meetings, appointments or charges."""

    company_id: int | None = None
    kind: (
        Literal[
            "allotment",
            "capital_alteration",
            "registered_office_change",
            "name_change",
            "objects_change",
            "conversion",
            "other",
        ]
        | None
    ) = None
    date: Day | None = None
    allotment_type: (
        Literal["private_placement", "rights", "bonus", "preferential", "esop", "conversion", "other"] | None
    ) = Field(None, description="For allotments: decides whether PAS-3 is due in 15 or 30 days")
    details: str | None = None
    notes: str | None = None


class RegistrationIn(Input):
    """Other registrations the company holds (GST, IEC, Udyam, EPF, ...)."""

    company_id: int | None = None
    kind: (
        Literal["gstin", "iec", "udyam", "epf", "esic", "professional_tax", "shops_establishment", "other"] | None
    ) = None
    number: str | None = None
    state: str | None = None
    status: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_gstin(self) -> RegistrationIn:
        if self.kind == "gstin" and self.number:
            self.number = v.gstin(self.number)
        return self


class FilingIn(Input):
    company_id: int | None = None
    form: FormCode | None = Field(None, description="e.g. DIR-12, AOC-4, MGT-7A")
    trigger: str | None = Field(None, description="The due-date item this filing answers, e.g. meeting:12")
    due_on: Day | None = None
    status: FilingStatus | None = None
    srn: str | None = None
    filed_on: Day | None = None
    fees: Rupees | None = None
    folder: str | None = None
    notes: str | None = None
