"""Due dates: which forms fall due when, worked out from what is in the company file.

Every rule names its legal basis. Items marked "check" rest on a reading she
should confirm; the rest follow the plain words of the Act or Rules. Dates are
not moved for holidays: the MCA portal is open every day.

Sources checked on 2026-10-09 for the rules that changed recently:
- INC-22: 30 days, since the Companies (Amendment) Act, 2017 replaced
  "fifteen days" in s.12(4) (in force 27-07-2018).
- DIR-3 KYC: once in three financial years by 30 June, plus updates within
  30 days of a change, under Rule 12A as substituted by G.S.R. 943(E)
  (31-12-2025, in force 31-03-2026). The cycle anchor varies by person, so
  the date comes from each person's `kyc_next_due` rather than a formula.
  Designated partners of LLPs hold DINs, so the same KYC applies to them.

Sources checked on 2026-10-22 for LLPs (LLP Act, 2008 and LLP Rules, 2009):
- Form 11 within 60 days of the year end (30 May): s.35(1), rule 25(1).
- Form 8 within 30 days from six months after the year end (30 October):
  s.34(3), rule 24(4).
- Form 3 within 30 days of incorporation for the LLP agreement, and within
  30 days of any change in it: s.23(2), rule 21(1).
- Form 4 within 30 days of a partner joining or leaving: s.25(2), rule 22.
- Form 15 within 30 days of a change of registered office: s.13(3), rule 17.
- Form 5 within 30 days of a change of name: s.16, rule 20(2). When the
  30 days start (the partners' decision or the new name's approval) is a
  point she should confirm, so it is marked "check".
- LLP BEN-2 within 30 days of receiving a BEN-1 declaration: LLP (Significant
  Beneficial Owners) Rules, 2023 (notified 09-11-2023); marked "check" until
  the rule number is confirmed against the Gazette.
- First financial year: an LLP incorporated after 30 September may end its
  first year on 31 March of the year after next (s.2(1)(l) proviso), so the
  first year's Form 11 and Form 8 are marked "check".
- Companies' BEN-2: within 30 days of receiving a BEN-1 declaration, rule 5,
  Companies (Significant Beneficial Owners) Rules, 2018.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from ..vault import Vault

# Status values for which no further filings are tracked.
CLOSED = ("struck_off", "amalgamated", "dissolved")
# s.10A applies to companies incorporated on or after the 2018 Ordinance came into force.
SECTION_10A_START = date(2018, 11, 2)


@dataclass
class DueItem:
    company_id: int
    company: str
    form: str
    title: str
    due: date
    basis: str  # how the date was worked out
    law: str  # where the rule comes from
    trigger: str  # stable key: a filing with the same company, form and trigger closes the item
    certainty: str = "firm"  # or "check" when she should confirm the rule applies
    filing_id: int | None = None
    filing_status: str | None = None

    def state(self, today: date) -> str:
        if self.filing_status in ("submitted", "approved"):
            return "done"
        if self.due < today:
            return "overdue"
        if (self.due - today).days <= 7:
            return "due_this_week"
        return "upcoming"

    def as_dict(self, today: date) -> dict[str, Any]:
        data = asdict(self)
        data["due"] = self.due.isoformat()
        data["state"] = self.state(today)
        data["days_left"] = (self.due - today).days
        return data


def upcoming(
    vault: Vault, today: date, company_id: int | None = None, days_ahead: int = 60, lookback_days: int = 365
) -> list[DueItem]:
    """Open items due within `days_ahead`, plus overdue ones from the last `lookback_days`."""
    start, end = today - timedelta(days=lookback_days), today + timedelta(days=days_ahead)
    return [
        item
        for item in due_items(vault, today, company_id)
        if item.state(today) != "done" and start <= item.due <= end
    ]


def due_items(vault: Vault, today: date, company_id: int | None = None) -> list[DueItem]:
    sql, params = "SELECT * FROM companies", ()
    if company_id is not None:
        sql, params = sql + " WHERE id = ?", (company_id,)
    companies = [dict(row) for row in vault.conn.execute(sql, params)]
    items: list[DueItem] = []
    for company in companies:
        if company["status"] in CLOSED:
            continue
        items += _company_items(vault, company, today)
    items += _director_kyc(vault, [c["id"] for c in companies if c["status"] not in CLOSED])
    _attach_filings(vault, items)
    return sorted(items, key=lambda item: (item.due, item.company, item.form))


def _company_items(vault: Vault, c: dict[str, Any], today: date) -> list[DueItem]:
    def rows(sql: str) -> list[dict[str, Any]]:
        return [dict(row) for row in vault.conn.execute(sql, (c["id"],))]

    appointments = rows(
        "SELECT a.*, p.name FROM appointments a JOIN parties p ON p.id = a.party_id WHERE a.company_id = ?"
    )
    if c["entity_type"] == "llp":
        return (
            _llp_annual(c, today)
            + _llp_incorporation(c)
            + _appointments(c, appointments, llp=True)
            + _llp_events(c, rows("SELECT * FROM events WHERE company_id = ?"))
        )

    meetings = rows("SELECT * FROM meetings WHERE company_id = ? ORDER BY date")
    return (
        _agm_based(c, meetings)
        + _agm_deadline(c, meetings, today)
        + _board_meetings(c, meetings, today)
        + _appointments(c, appointments, llp=False)
        + _auditors(
            c,
            rows(
                """SELECT aa.*, m.date AS meeting_date, p.name FROM auditor_appointments aa
                   JOIN parties p ON p.id = aa.auditor_id LEFT JOIN meetings m ON m.id = aa.meeting_id
                   WHERE aa.company_id = ?"""
            ),
        )
        + _resolutions(c, rows("SELECT * FROM resolutions WHERE company_id = ?"))
        + _charges(c, rows("SELECT * FROM charges WHERE company_id = ?"))
        + _events(c, rows("SELECT * FROM events WHERE company_id = ?"))
        + _incorporation(c)
        + _annual(c, today)
    )


def _item(
    c: dict[str, Any], form: str, title: str, due: date, basis: str, law: str, trigger: str, certainty: str = "firm"
) -> DueItem:
    return DueItem(c["id"], c["name"], form, title, due, basis, law, trigger, certainty)


# ------------------------------------------------------------ meeting-based


def _agm_based(c: dict[str, Any], meetings: list[dict[str, Any]]) -> list[DueItem]:
    if c["company_class"] == "opc":
        return []  # an OPC holds no AGM; its dates are in _annual
    items = []
    for m in meetings:
        if m["kind"] != "agm":
            continue
        held = _d(m["date"])
        fy = f" for FY {m['fy']}" if m["fy"] else ""
        basis = f"AGM held {held:%d-%m-%Y}"
        trigger = f"meeting:{m['id']}"
        aoc4 = "AOC-4 NBFC" if c["is_nbfc"] else "AOC-4"
        items.append(
            _item(c, aoc4, f"File financial statements{fy}", held + timedelta(days=30), f"{basis} + 30 days", "s.137(1)", trigger)
        )
        mgt7 = "MGT-7A" if c["is_small_company"] else "MGT-7"
        items.append(
            _item(c, mgt7, f"File annual return{fy}", held + timedelta(days=60), f"{basis} + 60 days", "s.92(4)", trigger)
        )
        if c["is_listed"]:
            items.append(
                _item(c, "MGT-15", "File report on the AGM", held + timedelta(days=30), f"{basis} + 30 days", "s.121(1)", trigger)
            )
    return items


def _agm_deadline(c: dict[str, Any], meetings: list[dict[str, Any]], today: date) -> list[DueItem]:
    if c["company_class"] == "opc":
        return []
    fy_end = _last_fy_end(c, today)
    agms = [_d(m["date"]) for m in meetings if m["kind"] == "agm"]
    if any(held > fy_end for held in agms):
        return []  # the AGM for that year is on file
    incorporated = _d(c["date_of_incorporation"]) if c["date_of_incorporation"] else None
    if incorporated and _first_fy_end(c, incorporated) > fy_end:
        return []  # its first financial year hasn't ended yet
    label = _fy_label(fy_end)
    if incorporated and not agms and _first_fy_end(c, incorporated) == fy_end:
        due = _add_months(fy_end, 9)
        return [
            _item(
                c, "AGM", f"Hold the first AGM (FY {label})", due,
                f"first financial year ended {fy_end:%d-%m-%Y} + 9 months", "s.96(1) proviso", f"agm:{label}", "check",
            )
        ]
    due, basis = _add_months(fy_end, 6), f"financial year ended {fy_end:%d-%m-%Y} + 6 months"
    if agms:
        fifteen = _add_months(max(agms), 15)
        if fifteen < due:
            due, basis = fifteen, f"previous AGM {max(agms):%d-%m-%Y} + 15 months"
    return [_item(c, "AGM", f"Hold the AGM for FY {label}", due, basis, "s.96(1)", f"agm:{label}")]


def _board_meetings(c: dict[str, Any], meetings: list[dict[str, Any]], today: date) -> list[DueItem]:
    boards = sorted(_d(m["date"]) for m in meetings if m["kind"] == "board")
    if not boards:
        return []
    last = boards[-1]
    trigger = f"board-after:{last.isoformat()}"
    if c["company_class"] == "opc" or c["is_small_company"] or c["status"] == "dormant":
        # s.173(5): at least one meeting in each half of the calendar year, at least 90 days apart.
        half_end = date(today.year, 6, 30) if today.month <= 6 else date(today.year, 12, 31)
        half_start = date(today.year, 1, 1) if today.month <= 6 else date(today.year, 7, 1)
        if last >= half_start:
            half_end = date(today.year, 12, 31) if today.month <= 6 else date(today.year + 1, 6, 30)
        earliest = last + timedelta(days=90)
        basis = f"one meeting in each half of the calendar year; last held {last:%d-%m-%Y}, next not before {earliest:%d-%m-%Y}"
        return [_item(c, "BOARD MEETING", "Hold a board meeting this half-year", half_end, basis, "s.173(5)", trigger)]
    return [
        _item(
            c, "BOARD MEETING", "Hold the next board meeting", last + timedelta(days=120),
            f"last board meeting {last:%d-%m-%Y} + 120 days", "s.173(1)", trigger,
        )
    ]


# --------------------------------------------------------------- event-based


def _appointments(c: dict[str, Any], rows: list[dict[str, Any]], llp: bool) -> list[DueItem]:
    form, law = ("LLP FORM 4", "LLP Act s.25(2)") if llp else ("DIR-12", "s.170(2)")
    partner_roles = ("designated_partner", "partner")
    items = []
    for a in rows:
        if (a["role"] in partner_roles) != llp:
            continue
        role = a["role"].replace("_", " ")
        # First directors are named in the incorporation filing, not in DIR-12.
        if a["date_of_appointment"] and a["date_of_appointment"] != c["date_of_incorporation"]:
            start = _d(a["date_of_appointment"])
            items.append(
                _item(
                    c, form, f"Report appointment of {a['name']} as {role}", start + timedelta(days=30),
                    f"appointed {start:%d-%m-%Y} + 30 days", law, f"appointment:{a['id']}:in",
                )
            )
        if a["date_of_cessation"]:
            end = _d(a["date_of_cessation"])
            items.append(
                _item(
                    c, form, f"Report cessation of {a['name']} as {role}", end + timedelta(days=30),
                    f"ceased {end:%d-%m-%Y} + 30 days", law, f"appointment:{a['id']}:out",
                )
            )
    return items


def _auditors(c: dict[str, Any], rows: list[dict[str, Any]]) -> list[DueItem]:
    items = []
    for a in rows:
        base = a["meeting_date"] or a["appointed_on"]
        if a["audit_type"] != "statutory" or not base:
            continue
        start = _d(base)
        what = "meeting" if a["meeting_date"] else "appointment"
        # Whether ADT-1 is needed for a first auditor appointed by the Board is a point she should confirm.
        certainty = "check" if a["appointment_kind"] == "first" else "firm"
        items.append(
            _item(
                c, "ADT-1", f"Notify appointment of {a['name']} as statutory auditor", start + timedelta(days=15),
                f"{what} on {start:%d-%m-%Y} + 15 days", "s.139(1), rule 4(2) Audit and Auditors Rules",
                f"auditor:{a['id']}", certainty,
            )
        )
    return items


def _resolutions(c: dict[str, Any], rows: list[dict[str, Any]]) -> list[DueItem]:
    items = []
    for r in rows:
        required = r["mgt14_required"] if r["mgt14_required"] is not None else r["kind"] == "special"
        if not required:
            continue
        passed = _d(r["passed_on"])
        items.append(
            _item(
                c, "MGT-14", f"File resolution: {r['subject']}", passed + timedelta(days=30),
                f"passed {passed:%d-%m-%Y} + 30 days", "s.117(1)", f"resolution:{r['id']}",
            )
        )
    return items


def _charges(c: dict[str, Any], rows: list[dict[str, Any]]) -> list[DueItem]:
    items = []
    for ch in rows:
        label = f"charge {ch['charge_id']}" if ch["charge_id"] else "the charge"
        for column, form, verb, law in (
            ("created_on", "CHG-1", "Register creation of", "s.77(1)"),
            ("modified_on", "CHG-1", "Register modification of", "s.79 read with s.77(1)"),
            ("satisfied_on", "CHG-4", "Report satisfaction of", "s.82(1)"),
        ):
            if ch[column]:
                when = _d(ch[column])
                items.append(
                    _item(
                        c, form, f"{verb} {label}", when + timedelta(days=30),
                        f"{column.replace('_on', '')} {when:%d-%m-%Y} + 30 days", law,
                        f"charge:{ch['id']}:{column.removesuffix('_on')}",
                    )
                )
    return items


def _events(c: dict[str, Any], rows: list[dict[str, Any]]) -> list[DueItem]:
    items = []
    for e in rows:
        when = _d(e["date"])
        trigger = f"event:{e['id']}"
        if e["kind"] == "allotment":
            kind = e["allotment_type"]
            if kind in (None, "private_placement"):
                # Unknown type: assume the shorter private-placement period rather than risk a late filing.
                days, law = 15, "s.42 (private placement)"
                certainty = "check" if kind is None else "firm"
            else:
                days, law, certainty = 30, "s.39(4), rule 12 Prospectus and Allotment Rules", "firm"
            items.append(
                _item(
                    c, "PAS-3", f"Return of allotment ({(kind or 'type not recorded').replace('_', ' ')})",
                    when + timedelta(days=days), f"allotted {when:%d-%m-%Y} + {days} days", law, trigger, certainty,
                )
            )
        elif e["kind"] == "capital_alteration":
            items.append(
                _item(c, "SH-7", "Notice of alteration of share capital", when + timedelta(days=30),
                      f"altered {when:%d-%m-%Y} + 30 days", "s.64(1)", trigger)
            )
        elif e["kind"] == "registered_office_change":
            items.append(
                _item(c, "INC-22", "Notice of change of registered office", when + timedelta(days=30),
                      f"changed {when:%d-%m-%Y} + 30 days", "s.12(4)", trigger)
            )
        elif e["kind"] == "sbo_declaration":
            items.append(
                _item(c, "BEN-2", "Return of significant beneficial ownership (on a BEN-1 declaration)", when + timedelta(days=30),
                      f"declaration received {when:%d-%m-%Y} + 30 days",
                      "rule 5, Companies (Significant Beneficial Owners) Rules, 2018", trigger)
            )
    return items


# What each LLP event starts: (form, title, what happened, law, certainty). The clock is 30 days for all of them.
LLP_EVENTS: dict[str, tuple[str, str, str, str, str]] = {
    "registered_office_change": ("LLP FORM 15", "Notice of change of registered office", "changed", "LLP Act s.13(3); rule 17", "firm"),
    "name_change": ("LLP FORM 5", "Notice of change of name", "name changed", "LLP Act s.16; rule 20(2)", "check"),
    "llp_agreement_change": ("LLP FORM 3", "File the change in the LLP agreement", "agreement changed",
                             "LLP Act s.23(2); rule 21(1)", "firm"),
    "sbo_declaration": ("LLP BEN-2", "Return of significant beneficial ownership (on an LLP BEN-1 declaration)",
                        "declaration received", "LLP (Significant Beneficial Owners) Rules, 2023", "check"),
}


def _llp_events(c: dict[str, Any], rows: list[dict[str, Any]]) -> list[DueItem]:
    items = []
    for e in rows:
        if e["kind"] not in LLP_EVENTS:
            continue
        form, title, what, law, certainty = LLP_EVENTS[e["kind"]]
        when = _d(e["date"])
        items.append(
            _item(c, form, title, when + timedelta(days=30), f"{what} {when:%d-%m-%Y} + 30 days", law, f"event:{e['id']}", certainty)
        )
    return items


def _llp_incorporation(c: dict[str, Any]) -> list[DueItem]:
    if not c["date_of_incorporation"]:
        return []
    incorporated = _d(c["date_of_incorporation"])
    return [
        _item(
            c, "LLP FORM 3", "File the LLP agreement", incorporated + timedelta(days=30),
            f"incorporated {incorporated:%d-%m-%Y} + 30 days", "LLP Act s.23(2); rule 21(1)", "form3:incorporation",
        )
    ]


def _incorporation(c: dict[str, Any]) -> list[DueItem]:
    if not c["date_of_incorporation"]:
        return []
    incorporated = _d(c["date_of_incorporation"])
    if incorporated < SECTION_10A_START or c["category"] not in (None, "limited_by_shares"):
        return []
    certainty = "firm" if c["category"] == "limited_by_shares" else "check"
    return [
        _item(
            c, "INC-20A", "Declare commencement of business", incorporated + timedelta(days=180),
            f"incorporated {incorporated:%d-%m-%Y} + 180 days", "s.10A(1)(a)", "inc20a", certainty,
        )
    ]


# ------------------------------------------------------------------- annual


def _annual(c: dict[str, Any], today: date) -> list[DueItem]:
    items = []
    years = (today.year - 1, today.year, today.year + 1)
    for y in years:
        if c["dpt3_applicable"] != 0:
            items.append(
                _item(c, "DPT-3", f"Return of deposits as on 31-03-{y}", date(y, 6, 30), "30 June every year",
                      "rules 16 and 16A, Acceptance of Deposits Rules", f"dpt3:{y}")
            )
        if c["msme_return_applicable"]:
            items.append(
                _item(c, "MSME-1", f"MSME-1 for October {y - 1} to March {y}", date(y, 4, 30),
                      "30 April, for the half-year to March", "MSE payments order, 2019", f"msme1:{y}-03")
            )
            items.append(
                _item(c, "MSME-1", f"MSME-1 for April to September {y}", date(y, 10, 31),
                      "31 October, for the half-year to September", "MSE payments order, 2019", f"msme1:{y}-09")
            )
        if c["company_class"] == "opc":
            fy_end = _fy_end_in(c, y)
            label = _fy_label(fy_end)
            items.append(
                _item(c, "AOC-4", f"File financial statements for FY {label}", fy_end + timedelta(days=180),
                      "financial year end + 180 days (one person company)", "s.137(1) proviso", f"aoc4:{label}")
            )
            agm_last_day = _add_months(fy_end, 6)
            items.append(
                _item(c, "MGT-7A", f"File annual return for FY {label}", agm_last_day + timedelta(days=60),
                      f"60 days from {agm_last_day:%d-%m-%Y}, the last day an AGM could have been held",
                      "s.92(4)", f"mgt7a:{label}", "check")
            )
    return items


def _llp_annual(c: dict[str, Any], today: date) -> list[DueItem]:
    """Form 11 and Form 8 for each financial year (1 April to 31 March, s.2(1)(l)) the LLP has had."""
    incorporated = _d(c["date_of_incorporation"]) if c["date_of_incorporation"] else None
    first_end = _llp_first_fy_end(incorporated) if incorporated else None
    # Incorporated in the second half of a financial year (after 30 September), its first year may run on to the
    # next 31 March but one (s.2(1)(l) proviso): the first 31 March may then have no Form 11 or Form 8 of its own.
    may_run_on = incorporated is not None and not date(first_end.year - 1, 4, 1) <= incorporated <= date(first_end.year - 1, 9, 30)
    items = []
    for y in (today.year - 1, today.year, today.year + 1):
        fy_end = date(y, 3, 31)
        if first_end and fy_end < first_end:
            continue  # the LLP didn't exist yet
        label = _fy_label(fy_end)
        certainty, note = "firm", ""
        if may_run_on and fy_end == first_end:
            certainty = "check"
            note = f"; its first financial year may instead end on 31-03-{y + 1} (incorporated after 30 September)"
        items.append(
            _item(c, "LLP FORM 11", f"Annual return for FY {label}", date(y, 5, 30),
                  f"within 60 days of the year end{note}", "LLP Act s.35(1); rule 25(1)", f"form11:{label}", certainty)
        )
        items.append(
            _item(c, "LLP FORM 8", f"Statement of account and solvency for FY {label}", date(y, 10, 30),
                  f"within 30 days from six months after the year end{note}", "LLP Act s.34(3); rule 24(4)", f"form8:{label}",
                  certainty)
        )
    return items


def _llp_first_fy_end(incorporated: date) -> date:
    """The first 31 March on or after incorporation: where the first financial year ends, unless it runs on."""
    return date(incorporated.year, 3, 31) if incorporated <= date(incorporated.year, 3, 31) else date(incorporated.year + 1, 3, 31)


def _director_kyc(vault: Vault, company_ids: list[int]) -> list[DueItem]:
    if not company_ids:
        return []
    marks = ", ".join("?" * len(company_ids))
    rows = vault.conn.execute(
        f"""SELECT p.id, p.name, p.din, p.kyc_next_due, MIN(c.id) AS company_id
            FROM parties p JOIN appointments a ON a.party_id = p.id JOIN companies c ON c.id = a.company_id
            WHERE p.din IS NOT NULL AND p.kyc_next_due IS NOT NULL AND a.date_of_cessation IS NULL
              AND c.id IN ({marks})
            GROUP BY p.id""",
        company_ids,
    ).fetchall()
    names = {r["id"]: r["name"] for r in vault.conn.execute(f"SELECT id, name FROM companies WHERE id IN ({marks})", company_ids)}
    items = []
    for r in rows:
        due = _d(r["kyc_next_due"])
        items.append(
            DueItem(
                r["company_id"], names[r["company_id"]], "DIR-3 KYC", f"DIN KYC for {r['name']} (DIN {r['din']})",
                due, "next periodic KYC date on file", "rule 12A, Appointment and Qualification of Directors Rules",
                f"kyc:{r['id']}:{due.isoformat()}",
            )
        )
    return items


# ------------------------------------------------------------------ helpers


def _attach_filings(vault: Vault, items: list[DueItem]) -> None:
    filings: dict[tuple[int, str, str], Any] = {}
    for row in vault.conn.execute(
        "SELECT id, company_id, form, trigger, status FROM filings WHERE trigger IS NOT NULL AND status != 'cancelled' ORDER BY id"
    ):
        filings[(row["company_id"], form_family(row["form"]), row["trigger"])] = row
    for item in items:
        row = filings.get((item.company_id, form_family(item.form), item.trigger))
        if row:
            item.filing_id, item.filing_status = row["id"], row["status"]


def form_family(form: str) -> str:
    """AOC-4 XBRL / NBFC / CFS answer the same item as AOC-4; MGT-7A the same as MGT-7. An LLP form is the same
    however it was written: "Form 11", "FORM-11", "LLP Form No. 11" are all LLP FORM 11."""
    code = " ".join(form.upper().split())
    if code.startswith("AOC-4"):
        return "AOC-4"
    if code in ("MGT-7", "MGT-7A"):
        return "MGT-7"
    llp = re.fullmatch(r"(?:LLP[\s-]*)?FORM[\s-]*(?:NO\.?\s*)?(\d{1,2})", code) or re.fullmatch(r"LLP[\s-]*(\d{1,2})", code)
    if llp:
        return f"LLP FORM {int(llp.group(1))}"
    if re.fullmatch(r"LLP[\s-]*BEN[\s-]*(\d)", code):
        return f"LLP BEN-{code[-1]}"
    return code


def _d(text: str) -> date:
    return date.fromisoformat(text)


def _fy_end_md(c: dict[str, Any]) -> tuple[int, int]:
    month, day = (c["fy_end"] or "03-31").split("-")
    return int(month), int(day)


def _fy_end_in(c: dict[str, Any], year: int) -> date:
    month, day = _fy_end_md(c)
    return date(year, month, day)


def _last_fy_end(c: dict[str, Any], today: date) -> date:
    end = _fy_end_in(c, today.year)
    return end if end < today else _fy_end_in(c, today.year - 1)


def _first_fy_end(c: dict[str, Any], incorporated: date) -> date:
    end = _fy_end_in(c, incorporated.year)
    if end < incorporated:
        end = _fy_end_in(c, incorporated.year + 1)
    if _fy_end_md(c) == (3, 31) and incorporated.month <= 3:
        # s.2(41): a company incorporated on or after 1 January closes its first year on 31 March of the next year.
        end = date(incorporated.year + 1, 3, 31)
    return end


def _fy_label(fy_end: date) -> str:
    if (fy_end.month, fy_end.day) == (12, 31):
        return str(fy_end.year)
    return f"{fy_end.year - 1}-{fy_end.year % 100:02d}"


def _add_months(day: date, months: int) -> date:
    """Calendar months, keeping month ends at month ends (31-03 + 6 months = 30-09)."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    at_month_end = day.day == calendar.monthrange(day.year, day.month)[1]
    return date(year, month, last if at_month_end else min(day.day, last))
