"""The company file: reads and writes, every write with its source.

A value read from a document is stored with the document, page and the words
that support it, so any field can be checked against the paper in seconds.
PAN, Aadhaar and passport numbers are masked in everything this module
returns, except `party(..., reveal=True)`, which only the form filler uses.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .. import validators
from ..errors import Invalid, NotFound
from .models import (
    DIRECTOR_ROLES,
    AppointmentIn,
    AuditorAppointmentIn,
    ChargeIn,
    CompanyIn,
    EventIn,
    FilingIn,
    MeetingIn,
    PartyIn,
    RegistrationIn,
    ResolutionIn,
    SourceIn,
)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Entity:
    table: str
    model: type[BaseModel]
    required: tuple[str, ...]
    sensitive: frozenset[str] = frozenset()


ENTITIES: dict[str, Entity] = {
    "company": Entity("companies", CompanyIn, ("name",)),
    "party": Entity("parties", PartyIn, ("kind", "name"), frozenset({"pan", "aadhaar", "passport_no"})),
    "appointment": Entity("appointments", AppointmentIn, ("company_id", "party_id", "role")),
    "meeting": Entity("meetings", MeetingIn, ("company_id", "kind", "date")),
    "resolution": Entity("resolutions", ResolutionIn, ("company_id", "kind", "subject", "passed_on")),
    "auditor_appointment": Entity("auditor_appointments", AuditorAppointmentIn, ("company_id", "auditor_id")),
    "charge": Entity("charges", ChargeIn, ("company_id",)),
    "event": Entity("events", EventIn, ("company_id", "kind", "date")),
    "registration": Entity("registrations", RegistrationIn, ("company_id", "kind", "number")),
    "filing": Entity("filings", FilingIn, ("company_id", "form")),
}

# What a record takes with it when it is deleted: a company its whole file, a person their positions.
OWNED: dict[str, tuple[str, ...]] = {
    "company": ("appointment", "resolution", "auditor_appointment", "charge", "event", "registration", "filing", "meeting"),
    "party": ("appointment", "auditor_appointment"),
}

# Roles only an individual can hold. (A body corporate can be an LLP partner, not a designated partner.)
INDIVIDUAL_ROLES = DIRECTOR_ROLES | {"ceo", "cfo", "company_secretary", "manager", "designated_partner"}


@dataclass(frozen=True)
class Source:
    """Where a write came from, and who recorded it."""

    kind: str
    recorded_by: str
    document_id: int | None = None
    page: int | None = None
    quote: str | None = None
    note: str | None = None

    @classmethod
    def from_input(cls, src: SourceIn, recorded_by: str) -> Source:
        return cls(src.kind, recorded_by, src.document_id, src.page, src.quote, src.note)


def mask(value: Any) -> str | None:
    """Keep only the last four characters: XXXXXX234F."""
    if value is None:
        return None
    text = str(value)
    return "X" * len(text) if len(text) <= 4 else "X" * (len(text) - 4) + text[-4:]


class Vault:
    def __init__(self, conn: sqlite3.Connection, actor: str = "claude") -> None:
        self.conn = conn
        self.actor = actor

    @classmethod
    @contextmanager
    def open(cls, db_path: Path, actor: str = "claude") -> Iterator[Vault]:
        """One connection per use; commits on success, rolls back on any error."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            _migrate(conn)
            yield cls(conn, actor)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ writes

    def save(
        self, entity: str, data: BaseModel | dict[str, Any], source: Source, record_id: int | None = None
    ) -> int:
        """Create a record (record_id None) or change the fields given in `data`. Returns the record id."""
        spec = ENTITIES[entity]
        try:
            model = data if isinstance(data, spec.model) else spec.model.model_validate(data)
        except ValidationError as exc:
            raise Invalid(describe_validation_error(exc)) from exc
        values = {name: _to_db(value) for name, value in model.model_dump(exclude_unset=True).items()}

        current = None
        if record_id is not None:
            current = self._get(spec.table, record_id)
            if current is None:
                raise NotFound(f"There is no {entity.replace('_', ' ')} with id {record_id}.")
        self._check_source(source)
        derived = self._check_and_derive(entity, values, dict(current) if current else {})

        row = {**derived, **values}
        if current is None:
            missing = [name for name in spec.required if row.get(name) in (None, "")]
            if missing:
                raise Invalid(f"A new {entity.replace('_', ' ')} also needs: {', '.join(missing)}.")
            record_id = self._insert(spec, row)
        elif row:
            self._update(spec, record_id, row)

        # A quote can contain the very PAN or Aadhaar being saved; mask it there too.
        secrets = [str(values[name]) for name in spec.sensitive if values.get(name)]
        if secrets and source.quote:
            quote = source.quote
            for secret in secrets:
                quote = quote.replace(secret, mask(secret) or "")
            source = replace(source, quote=quote)
        for name, value in values.items():
            self._record_source(entity, record_id, name, value, source, spec)
        for name, value in derived.items():
            self._record_source(entity, record_id, name, value, Source("derived", self.actor, note="from the CIN"), spec)
        self.log(f"save {entity}", {"id": record_id, "fields": sorted(row)})
        return record_id

    # ----------------------------------------------------------------- deletes

    def dependents(self, entity: str, record_id: int) -> dict[str, Any]:
        """What deleting a record takes with it, and what only loses its link to it."""
        spec = ENTITIES[entity]
        if self._get(spec.table, record_id) is None:
            raise NotFound(f"There is no {entity.replace('_', ' ')} with id {record_id}.")
        deletes: dict[str, int] = {}
        for child in OWNED.get(entity, ()):
            table = ENTITIES[child].table
            column = self._fk_column(table, spec.table)
            count = self.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (record_id,)).fetchone()[0]
            if count:
                deletes[child] = count
        unlinks: dict[str, int] = {}
        for table, column in self._references(spec.table, exclude={ENTITIES[c].table for c in OWNED.get(entity, ())}):
            count = self.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (record_id,)).fetchone()[0]
            if count:
                unlinks[f"{table}.{column}"] = count
        return {"entity": entity, "id": record_id, "deletes": deletes, "unlinks": unlinks}

    def delete(self, entity: str, record_id: int) -> dict[str, Any]:
        """Delete a record with what belongs to it (a company's meetings, a person's appointments...).

        Records elsewhere that only point at it (documents of a company, the meeting an appointment was
        approved at) keep their own data and lose the link. Its source history goes with it; the activity
        log keeps a line saying it was deleted.
        """
        summary = self.dependents(entity, record_id)
        spec = ENTITIES[entity]
        owned_tables = {ENTITIES[c].table for c in OWNED.get(entity, ())}
        # Children first (meetings last, because other children may point at them), then the record.
        for child in sorted(OWNED.get(entity, ()), key=lambda c: c == "meeting"):
            table = ENTITIES[child].table
            column = self._fk_column(table, spec.table)
            ids = [r[0] for r in self.conn.execute(f"SELECT id FROM {table} WHERE {column} = ?", (record_id,))]
            for child_id in ids:
                self._unlink_all(table, child_id, exclude=owned_tables)
                self.conn.execute("DELETE FROM field_sources WHERE entity = ? AND entity_id = ?", (child, child_id))
            self.conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (record_id,))
        self._unlink_all(spec.table, record_id, exclude=owned_tables)
        self.conn.execute("DELETE FROM field_sources WHERE entity = ? AND entity_id = ?", (entity, record_id))
        self.conn.execute(f"DELETE FROM {spec.table} WHERE id = ?", (record_id,))
        self.log(f"delete {entity}", summary)
        return summary

    def _references(self, table: str, exclude: set[str]) -> list[tuple[str, str]]:
        """(table, column) pairs anywhere in the database with a foreign key to `table`."""
        out = []
        for (name,) in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"):
            if name in exclude or name == table:
                continue
            try:
                keys = self.conn.execute(f"PRAGMA foreign_key_list({name})").fetchall()
            except sqlite3.DatabaseError:
                continue  # a virtual table
            out += [(name, k[3]) for k in keys if k[2] == table and k[6].upper() != "CASCADE"]
        return out

    def _unlink_all(self, table: str, record_id: int, exclude: set[str]) -> None:
        for other, column in self._references(table, exclude):
            notnull = {r[1]: r[3] for r in self.conn.execute(f"PRAGMA table_info({other})")}.get(column)
            if notnull:
                count = self.conn.execute(f"SELECT COUNT(*) FROM {other} WHERE {column} = ?", (record_id,)).fetchone()[0]
                if count:
                    raise Invalid(f"{count} record(s) in {other} need this {table[:-1]}; delete or change them first.")
                continue
            self.conn.execute(f"UPDATE {other} SET {column} = NULL WHERE {column} = ?", (record_id,))

    def _fk_column(self, table: str, target: str) -> str:
        for key in self.conn.execute(f"PRAGMA foreign_key_list({table})"):
            if key[2] == target:
                return key[3]
        raise Invalid(f"{table} has no link to {target}.")

    def log(self, action: str, details: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            "INSERT INTO activity (actor, action, details) VALUES (?, ?, ?)",
            (self.actor, action, json.dumps(details or {}, default=str)),
        )

    def _insert(self, spec: Entity, row: dict[str, Any]) -> int:
        columns = list(row)
        sql = f"INSERT INTO {spec.table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})"
        try:
            return self.conn.execute(sql, [row[c] for c in columns]).lastrowid
        except sqlite3.IntegrityError as exc:
            raise self._integrity_error(spec, row, exc) from exc

    def _update(self, spec: Entity, record_id: int, row: dict[str, Any]) -> None:
        assignments = ", ".join(f"{column} = ?" for column in row)
        sql = f"UPDATE {spec.table} SET {assignments}, updated_at = datetime('now') WHERE id = ?"
        try:
            self.conn.execute(sql, [*row.values(), record_id])
        except sqlite3.IntegrityError as exc:
            raise self._integrity_error(spec, row, exc) from exc

    def _record_source(
        self, entity: str, record_id: int, name: str, value: Any, source: Source, spec: Entity
    ) -> None:
        shown = mask(value) if name in spec.sensitive else (None if value is None else str(value))
        self.conn.execute(
            "INSERT INTO field_sources (entity, entity_id, field, value, source_kind, document_id, page, quote,"
            " note, recorded_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity,
                record_id,
                name,
                shown,
                source.kind,
                source.document_id,
                source.page,
                source.quote,
                source.note,
                source.recorded_by,
            ),
        )

    def _check_source(self, source: Source) -> None:
        if source.kind != "document":
            return
        if source.document_id is None or source.page is None:
            raise Invalid("A document source needs document_id and page.")
        row = self.conn.execute("SELECT pages FROM documents WHERE id = ?", (source.document_id,)).fetchone()
        if row is None:
            raise NotFound(f"There is no document {source.document_id}; ingest it first.")
        if row["pages"] and not 1 <= source.page <= row["pages"]:
            raise Invalid(f"Document {source.document_id} has {row['pages']} pages, so page {source.page} doesn't exist.")

    def _check_and_derive(self, entity: str, values: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        """Consistency checks across fields. Returns values worked out from others (only the CIN, for now)."""
        if entity == "company":
            return self._company_rules(values, current)
        if entity == "party":
            self._party_rules(values, current)
        elif entity == "appointment":
            self._appointment_rules(values, current)
        elif entity == "auditor_appointment" and "auditor_id" in values and self._get("parties", values["auditor_id"]) is None:
            raise NotFound(f"There is no party with id {values['auditor_id']}; add the auditor with save_party first.")
        return {}

    def _company_rules(self, values: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        derived: dict[str, Any] = {}
        entity_type = values.get("entity_type") or (current.get("entity_type") if current else None)
        cin = values.get("cin") or current.get("cin")
        if cin:
            from_cin = "llp" if validators.is_llpin(cin) else "company"
            if entity_type and entity_type != from_cin:
                raise Invalid(f"{cin} is {'an LLPIN' if from_cin == 'llp' else 'a CIN'}, but the record says {entity_type}.")
            if not current and "entity_type" not in values:
                derived["entity_type"] = from_cin
            entity_type = from_cin
            if from_cin == "company" and "cin" in values:
                info = validators.parse_cin(cin)
                for name, value in (
                    ("company_class", info["company_class"]),
                    ("is_listed", int(info["listed"])),
                    ("is_section8", int(info["is_section8"])),
                    ("nic_code", info["nic_code"]),
                ):
                    if value is not None and name not in values and current.get(name) is None:
                        derived[name] = value
        pan = values.get("pan")
        if pan:
            expected = "F" if entity_type == "llp" else "C"
            if pan[3] != expected:
                raise Invalid(
                    f"That PAN belongs to {_a(validators.PAN_HOLDER[pan[3]])} (4th letter {pan[3]}); "
                    f"{'an LLP' if expected == 'F' else 'a company'}'s own PAN has {expected} there. "
                    "Is it a director's PAN?"
                )
        return derived

    def _party_rules(self, values: dict[str, Any], current: dict[str, Any]) -> None:
        kind = values.get("kind") or current.get("kind")
        pan = values.get("pan") or current.get("pan")
        if pan and kind == "individual" and pan[3] != "P":
            raise Invalid(f"That PAN belongs to {_a(validators.PAN_HOLDER[pan[3]])}, not an individual (4th letter should be P).")
        if pan and kind == "organisation" and pan[3] == "P":
            raise Invalid("That PAN belongs to an individual (4th letter P), not an organisation.")
        if (values.get("din") or current.get("din")) and kind == "organisation":
            raise Invalid("Only individuals have a DIN.")

    def _appointment_rules(self, values: dict[str, Any], current: dict[str, Any]) -> None:
        merged = {**current, **values}
        if merged.get("company_id") is not None:
            self.company_row(merged["company_id"])
        if merged.get("party_id") is not None:
            party = self._get("parties", merged["party_id"])
            if party is None:
                raise NotFound(f"There is no party with id {merged['party_id']}; add the person with save_party first.")
            if merged.get("role") in INDIVIDUAL_ROLES and party["kind"] != "individual":
                raise Invalid(f"{party['name']} is an organisation; only an individual can be {merged['role'].replace('_', ' ')}.")
        start, end = merged.get("date_of_appointment"), merged.get("date_of_cessation")
        if start and end and end < start:
            raise Invalid(f"The cessation date {end} is before the appointment date {start}.")

    def _integrity_error(self, spec: Entity, row: dict[str, Any], exc: sqlite3.IntegrityError) -> Invalid:
        message = str(exc)
        if message.startswith("UNIQUE constraint failed"):
            columns = [column for _table, column in re.findall(r"(\w+)\.(\w+)", message)]
            where = " AND ".join(f"{column} = ?" for column in columns)
            existing = self.conn.execute(
                f"SELECT id FROM {spec.table} WHERE {where}", [row.get(c) for c in columns]
            ).fetchone()
            shown = ", ".join(
                f"{c} {mask(row.get(c)) if c in spec.sensitive else row.get(c)}" for c in columns
            )
            found = f" (id {existing['id']})" if existing else ""
            return Invalid(f"Another record already has {shown}{found}. Update that record instead of adding a new one.")
        if message.startswith("FOREIGN KEY"):
            ids = {name: value for name, value in row.items() if name.endswith("_id")}
            return Invalid(f"One of these ids doesn't exist: {ids}.")
        if message.startswith("NOT NULL"):
            return Invalid(f"{message.split('.')[-1]} can't be empty.")
        return Invalid(message)

    # ------------------------------------------------------------------- reads

    def _get(self, table: str, record_id: int) -> sqlite3.Row | None:
        return self.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()

    def company_row(self, company_id: int) -> dict[str, Any]:
        row = self._get("companies", company_id)
        if row is None:
            raise NotFound(f"There is no company with id {company_id}.")
        return dict(row)

    def company_folder(self, company_id: int) -> str:
        """Folder name under clients/: the CIN when known."""
        company = self.company_row(company_id)
        return company["cin"] or f"company-{company_id}"

    def resolve_company(self, ref: str | int) -> int:
        """Accepts an id, a CIN/LLPIN, or a name (or a unique part of one)."""
        text = str(ref).strip()
        if text.isdigit():
            return self.company_row(int(text))["id"]
        row = self.conn.execute("SELECT id FROM companies WHERE cin = ?", (text.replace(" ", "").upper(),)).fetchone()
        if row:
            return row["id"]
        exact = self.conn.execute("SELECT id FROM companies WHERE lower(name) = lower(?)", (text,)).fetchall()
        if len(exact) == 1:
            return exact[0]["id"]
        rows = self.conn.execute(
            "SELECT id, name, cin FROM companies WHERE instr(lower(name), lower(?)) > 0 ORDER BY name", (text,)
        ).fetchall()
        if len(rows) == 1:
            return rows[0]["id"]
        if not rows:
            raise NotFound(f"No company matches {text!r}. Use find_companies to see the companies on file.")
        listing = "; ".join(f"{r['name']} (id {r['id']}{', ' + r['cin'] if r['cin'] else ''})" for r in rows[:10])
        raise Invalid(f"{len(rows)} companies match {text!r}: {listing}. Use the id or CIN.")

    def find_companies(self, query: str = "") -> list[dict[str, Any]]:
        sql = "SELECT id, cin, name, entity_type, company_class, status FROM companies"
        params: tuple[Any, ...] = ()
        if query.strip():
            sql += " WHERE instr(lower(name), lower(?)) > 0 OR cin = ?"
            params = (query.strip(), query.replace(" ", "").upper())
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY name", params)]

    def company_file(self, company_id: int, include_sources: bool = False) -> dict[str, Any]:
        """Everything on file for one company, with sensitive numbers masked."""
        company = self.company_row(company_id)
        people = self._rows(
            """SELECT a.id AS appointment_id, a.role, a.category, a.date_of_appointment, a.date_of_cessation,
                      a.cessation_reason, p.id AS party_id, p.name, p.din, p.pan, p.email, p.mobile, p.kyc_next_due
               FROM appointments a JOIN parties p ON p.id = a.party_id
               WHERE a.company_id = ?
               ORDER BY a.date_of_cessation IS NOT NULL, a.date_of_appointment""",
            (company_id,),
        )
        for person in people:
            person["pan"] = mask(person["pan"])
        result = {
            "company": company,
            "people": people,
            "auditors": self._rows(
                """SELECT aa.*, p.name AS auditor_name, p.frn, p.membership_no
                   FROM auditor_appointments aa JOIN parties p ON p.id = aa.auditor_id
                   WHERE aa.company_id = ? ORDER BY aa.appointed_on DESC""",
                (company_id,),
            ),
            "meetings": self._rows("SELECT * FROM meetings WHERE company_id = ? ORDER BY date DESC LIMIT 20", (company_id,)),
            "resolutions": self._rows(
                "SELECT * FROM resolutions WHERE company_id = ? ORDER BY passed_on DESC LIMIT 20", (company_id,)
            ),
            "charges": self._rows(
                """SELECT c.*, p.name AS holder_name FROM charges c LEFT JOIN parties p ON p.id = c.holder_id
                   WHERE c.company_id = ? ORDER BY c.created_on DESC""",
                (company_id,),
            ),
            "events": self._rows("SELECT * FROM events WHERE company_id = ? ORDER BY date DESC", (company_id,)),
            "registrations": self._rows("SELECT * FROM registrations WHERE company_id = ? ORDER BY kind", (company_id,)),
            "filings": self._rows(
                "SELECT * FROM filings WHERE company_id = ? ORDER BY COALESCE(filed_on, due_on, created_at) DESC LIMIT 30",
                (company_id,),
            ),
            "documents": self._rows(
                "SELECT doc_type, COUNT(*) AS count FROM documents WHERE company_id = ? GROUP BY doc_type ORDER BY doc_type",
                (company_id,),
            ),
        }
        if include_sources:
            result["sources"] = self.latest_sources("company", company_id)
        return result

    def party(self, party_id: int, reveal: bool = False) -> dict[str, Any]:
        row = self._get("parties", party_id)
        if row is None:
            raise NotFound(f"There is no party with id {party_id}.")
        party = dict(row)
        if not reveal:
            for name in ENTITIES["party"].sensitive:
                party[name] = mask(party[name])
        party["appointments"] = self._rows(
            """SELECT a.id AS appointment_id, a.role, a.date_of_appointment, a.date_of_cessation,
                      c.id AS company_id, c.name AS company, c.cin
               FROM appointments a JOIN companies c ON c.id = a.company_id
               WHERE a.party_id = ? ORDER BY a.date_of_appointment""",
            (party_id,),
        )
        return party

    def find_parties(self, query: str) -> list[dict[str, Any]]:
        text = query.strip()
        compact = text.replace(" ", "").upper()
        rows = self._rows(
            """SELECT id, kind, name, din, pan, org_type, frn, membership_no FROM parties
               WHERE instr(lower(name), lower(?)) > 0 OR din = ? OR pan = ? ORDER BY name LIMIT 50""",
            (text, compact, compact),
        )
        for row in rows:
            row["pan"] = mask(row["pan"])
        return rows

    def latest_sources(self, entity: str, entity_id: int) -> dict[str, dict[str, Any]]:
        rows = self._rows(
            """SELECT field, value, source_kind, document_id, page, quote, note, recorded_by, recorded_at
               FROM field_sources WHERE id IN (
                   SELECT MAX(id) FROM field_sources WHERE entity = ? AND entity_id = ? GROUP BY field)""",
            (entity, entity_id),
        )
        return {row.pop("field"): row for row in rows}

    def field_history(self, entity: str, entity_id: int, field: str | None = None) -> list[dict[str, Any]]:
        if entity not in ENTITIES:
            raise Invalid(f"Unknown record type {entity!r}; use one of: {', '.join(ENTITIES)}.")
        sql = "SELECT * FROM field_sources WHERE entity = ? AND entity_id = ?"
        params: list[Any] = [entity, entity_id]
        if field:
            sql += " AND field = ?"
            params.append(field)
        return self._rows(sql + " ORDER BY id", params)

    def documents(self, company_id: int | None = None, doc_type: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id, company_id, doc_type, original_name, pages, note, ingested_at FROM documents WHERE 1 = 1"
        params: list[Any] = []
        if company_id is not None:
            sql += " AND company_id = ?"
            params.append(company_id)
        if doc_type:
            sql += " AND doc_type = ?"
            params.append(doc_type)
        return self._rows(sql + " ORDER BY id DESC", params)

    def filings(self, company_id: int | None = None, status: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT f.*, c.name AS company FROM filings f JOIN companies c ON c.id = f.company_id WHERE 1 = 1"""
        params: list[Any] = []
        if company_id is not None:
            sql += " AND f.company_id = ?"
            params.append(company_id)
        if status:
            sql += " AND f.status = ?"
            params.append(status)
        return self._rows(sql + " ORDER BY COALESCE(f.due_on, f.created_at)", params)

    def filing(self, filing_id: int) -> dict[str, Any]:
        row = self._get("filings", filing_id)
        if row is None:
            raise NotFound(f"There is no filing with id {filing_id}.")
        return dict(row)

    def _rows(self, sql: str, params: Any = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(sql, params)]


def _to_db(value: Any) -> Any:
    return int(value) if isinstance(value, bool) else value


def _a(noun: str) -> str:
    """'an individual', 'a company', 'an HUF'."""
    return ("an " if noun[0].lower() in "aeiou" or noun.startswith("HUF") else "a ") + noun


def describe_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"]) or "value"
        parts.append(f"{where}: {error['msg'].removeprefix('Value error, ')}")
    return "; ".join(parts)


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise Invalid(
            f"This company file was written by a newer CS Desk (schema {version}). Update CS Desk before using it."
        )
    schema = resources.files("csdesk.vault").joinpath("schema.sql").read_text(encoding="utf-8")
    try:
        conn.executescript(f"BEGIN;\n{schema}\nPRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;")
    except sqlite3.OperationalError:
        conn.rollback()
        # Another process may have created the schema at the same moment.
        if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise
