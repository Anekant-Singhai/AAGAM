"""Company dossier: one readable page on a company, built from the company file.

Every fact comes from the company file and the due-date rules. The last
section says where each company-level fact came from, and the gaps list says
what is missing before the dossier can be relied on. Outside data (MCA master
data, GST status, directorships outside her client list) is a later step.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..config import Settings
from ..drafting.render import inr
from ..duedates import DueItem, due_items
from ..vault import Vault
from ..vault.models import DIRECTOR_ROLES

MIN_DIRECTORS = {"private": 2, "public": 3, "opc": 1}  # s.149(1)(a)
CORE_FIELDS = {
    "cin": "CIN",
    "date_of_incorporation": "date of incorporation",
    "roc": "RoC",
    "ro_line1": "registered office address",
    "ro_pin": "registered office PIN code",
    "pan": "PAN",
    "authorised_capital": "authorised capital",
    "paid_up_capital": "paid-up capital",
    "email": "email",
}
CLASS_NAMES = {"private": "Private company", "public": "Public company", "opc": "One person company"}


def build(vault: Vault, settings: Settings, company_id: int, today: date) -> dict[str, Any]:
    file = vault.company_file(company_id, include_sources=True)
    c = file["company"]
    is_llp = c["entity_type"] == "llp"
    items = [item for item in due_items(vault, today, company_id) if item.state(today) != "done"]
    overdue = [i for i in items if i.state(today) == "overdue" and i.due >= today - timedelta(days=730)]
    upcoming = [i for i in items if today <= i.due <= today + timedelta(days=90)]
    current = [p for p in file["people"] if not p["date_of_cessation"]]
    two_years_ago = (today - timedelta(days=730)).isoformat()
    former = [p for p in file["people"] if p["date_of_cessation"] and p["date_of_cessation"] >= two_years_ago]

    out: list[str] = [
        f"# {c['name']}",
        "",
        f"Prepared {today:%d-%m-%Y} from the CS Desk company file. It is only as complete as the file: "
        "see the gaps listed at the end.",
        "",
        "## Snapshot",
        "",
        "| | |",
        "|---|---|",
    ]
    kind = "Limited liability partnership" if is_llp else CLASS_NAMES.get(c["company_class"], "Company (class not recorded)")
    extras = [label for flag, label in (("is_listed", "listed"), ("is_section8", "section 8"), ("is_nbfc", "NBFC")) if c[flag]]
    rows = [
        ("LLPIN" if is_llp else "CIN", c["cin"]),
        ("Type", kind + (f" ({', '.join(extras)})" if extras else "")),
        ("Status", (c["status"] or "not recorded").replace("_", " ")),
        ("Incorporated", " · ".join(x for x in (_day(c["date_of_incorporation"]), c["roc"]) if x)),
        ("Registered office", ", ".join(c[k] for k in ("ro_line1", "ro_line2", "ro_city", "ro_state", "ro_pin") if c[k])),
        ("Authorised capital", _money(c["authorised_capital"])),
        ("Paid-up capital", _money(c["paid_up_capital"])),
        ("Financial year ends", _fy_end(c["fy_end"])),
        ("PAN / TAN", " / ".join(x or "—" for x in (c["pan"], c["tan"]))),
        ("Email", c["email"]),
    ]
    out += [f"| {label} | {value or '—'} |" for label, value in rows]

    out += ["", "## Partners" if is_llp else "## Directors and key managerial personnel", ""]
    if current:
        out += ["| Name | DIN | Position | Appointed | Also on (companies on file) |", "|---|---|---|---|---|"]
        for p in current:
            others = [
                a["company"]
                for a in vault.party(p["party_id"])["appointments"]
                if a["company_id"] != company_id and not a["date_of_cessation"]
            ]
            out.append(
                f"| {p['name']} | {p['din'] or '—'} | {_role(p['role'])} | {_day(p['date_of_appointment']) or '—'} "
                f"| {', '.join(sorted(set(others))) or '—'} |"
            )
    else:
        out.append("No current directors or KMP on file.")
    if former:
        out += ["", "Changes in the last two years:", "", "| Name | Position | Appointed | Ceased | Reason |", "|---|---|---|---|---|"]
        out += [
            f"| {p['name']} | {_role(p['role'])} | {_day(p['date_of_appointment']) or '—'} | {_day(p['date_of_cessation'])} "
            f"| {(p['cessation_reason'] or '—').replace('_', ' ')} |"
            for p in former
        ]

    out += ["", "## Auditors", ""]
    if file["auditors"]:
        out += ["| Auditor | FRN / membership | Type | Appointed | Term |", "|---|---|---|---|---|"]
        out += [
            f"| {a['auditor_name']} | {a['frn'] or a['membership_no'] or '—'} | {a['audit_type']} "
            f"| {_day(a['appointed_on']) or '—'} | {' to '.join(x for x in (a['from_fy'], a['to_fy']) if x) or '—'} |"
            for a in file["auditors"]
        ]
    else:
        out.append("No auditor on file.")

    out += ["", "## Charges", ""]
    if file["charges"]:
        out += ["| Charge ID | Holder | Amount | Created | Satisfied |", "|---|---|---|---|---|"]
        out += [
            f"| {ch['charge_id'] or '—'} | {ch['holder_name'] or '—'} | {_money(ch['amount']) or '—'} "
            f"| {_day(ch['created_on']) or '—'} | {_day(ch['satisfied_on']) or 'open'} |"
            for ch in file["charges"]
        ]
    else:
        out.append("No charges on file.")

    out += ["", "## Meetings on file", ""]
    if file["meetings"]:
        out += ["| Date | Meeting | FY |", "|---|---|---|"]
        out += [f"| {_day(m['date'])} | {_meeting_name(m)} | {m['fy'] or '—'} |" for m in file["meetings"][:10]]
    else:
        out.append("No meetings on file.")

    out += ["", "## Filings and due dates", ""]
    out += _items_block("Overdue", overdue, today)
    out += _items_block("Due in the next 90 days", upcoming, today)
    filed = [f for f in file["filings"] if f["status"] in ("submitted", "approved")]
    if filed:
        out += ["Filed (latest):", "", "| Form | SRN | Filed on | Status |", "|---|---|---|---|"]
        out += [f"| {f['form']} | {f['srn'] or '—'} | {_day(f['filed_on']) or '—'} | {f['status']} |" for f in filed[:10]]
        out.append("")

    if file["registrations"]:
        out += ["## Registrations", "", "| Kind | Number | State | Status |", "|---|---|---|---|"]
        out += [f"| {r['kind'].upper()} | {r['number']} | {r['state'] or '—'} | {r['status'] or '—'} |" for r in file["registrations"]]
        out.append("")

    out += ["## Documents on file", ""]
    out += [f"- {d['doc_type'].replace('_', ' ')}: {d['count']}" for d in file["documents"]] or ["None yet."]

    gaps = _gaps(c, file, current, is_llp)
    out += ["", "## Gaps and checks", ""]
    out += [f"- {gap}" for gap in gaps] or ["None found in the file."]

    out += ["", "## Where the company details came from", "", "| Field | Value | Source |", "|---|---|---|"]
    for name, src in sorted(file["sources"].items()):
        out.append(f"| {name} | {src['value'] or '—'} | {_source(src)} |")

    text = "\n".join(out) + "\n"
    folder = settings.clients_dir / vault.company_folder(company_id) / "dossier"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{today:%Y%m%d}-dossier.md"
    path.write_text(text, encoding="utf-8")
    vault.log("build dossier", {"company_id": company_id, "path": str(path), "gaps": len(gaps), "overdue": len(overdue)})
    return {"path": str(path), "markdown": text, "gaps": len(gaps), "overdue": len(overdue)}


def _gaps(c: dict[str, Any], file: dict[str, Any], current: list[dict[str, Any]], is_llp: bool) -> list[str]:
    gaps = [f"No {label} on file." for name, label in CORE_FIELDS.items() if c[name] in (None, "")]
    if is_llp:
        designated = [p for p in current if p["role"] == "designated_partner"]
        if len(designated) < 2:
            gaps.append(f"{len(designated)} designated partner(s) on file; an LLP needs at least two (LLP Act s.7).")
        gaps += [f"{p['name']} is a designated partner but has no DIN on file (LLP Act s.7(6))." for p in designated if not p["din"]]
        gaps += [f"No next DIN KYC date on file for {p['name']}." for p in designated if p["din"] and not p["kyc_next_due"]]
        return gaps
    directors = [p for p in current if p["role"] in DIRECTOR_ROLES]
    needed = MIN_DIRECTORS.get(c["company_class"])
    if needed and len(directors) < needed:
        gaps.append(f"{len(directors)} director(s) on file; a {c['company_class']} company needs at least {needed} (s.149(1)).")
    if not c["company_class"]:
        gaps.append("Company class (private, public or OPC) not recorded.")
    gaps += [f"{p['name']} is a director but has no DIN on file." for p in directors if not p["din"]]
    gaps += [f"No next DIN KYC date on file for {p['name']}." for p in directors if p["din"] and not p["kyc_next_due"]]
    if not any(a["audit_type"] == "statutory" and not a["ended_on"] for a in file["auditors"]):
        gaps.append("No current statutory auditor on file.")
    if not any(m["kind"] == "board" for m in file["meetings"]):
        gaps.append("No board meetings on file, so the next-meeting date can't be worked out.")
    if c["company_class"] == "private" and c["is_small_company"] is None:
        gaps.append("Small company status not recorded (it decides MGT-7 vs MGT-7A and the board meeting rule).")
    if c["msme_return_applicable"] is None:
        gaps.append("Not recorded whether MSME-1 applies (dues to micro or small suppliers beyond 45 days).")
    return gaps


def _items_block(heading: str, items: list[DueItem], today: date) -> list[str]:
    if not items:
        return [f"{heading}: none.", ""]
    lines = [f"{heading}:", ""]
    for i in items:
        check = " — rule to confirm" if i.certainty == "check" else ""
        lines.append(f"- **{i.form}** {i.title}: due {i.due:%d-%m-%Y} ({i.basis}; {i.law}){check}")
    return lines + [""]


def _source(src: dict[str, Any]) -> str:
    kind = src["source_kind"]
    when = (src["recorded_at"] or "")[:10]
    if kind == "document":
        quote = f": “{src['quote']}”" if src["quote"] else ""
        return f"document {src['document_id']}, p.{src['page']}{quote}"
    if kind == "user":
        return f"she said so ({when})"
    if kind == "derived":
        return src["note"] or "worked out"
    return f"{kind} ({when})"


def _day(value: str | None) -> str | None:
    return date.fromisoformat(value).strftime("%d-%m-%Y") if value else None


def _money(value: int | None) -> str | None:
    return f"₹{inr(value)}" if value is not None else None


def _fy_end(value: str | None) -> str:
    month, day = (value or "03-31").split("-")
    return date(2001, int(month), int(day)).strftime("%d %B").lstrip("0")


def _meeting_name(m: dict[str, Any]) -> str:
    if m["kind"] in ("agm", "egm"):
        return m["kind"].upper()
    if m["kind"] == "committee":
        return m["committee"] or "Committee"
    return m["kind"].replace("_", " ").capitalize()


def _role(role: str) -> str:
    return {"company_secretary": "Company Secretary", "ceo": "CEO", "cfo": "CFO"}.get(role, role.replace("_", " ").capitalize())
