"""Opening the database: the core's company file plus AAGAM's library tables."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from csdesk.vault import Vault

SCHEMA_VERSION = "5"
# Columns added after a table first shipped: CREATE TABLE IF NOT EXISTS won't add them to an existing table.
ADDED_COLUMNS = [
    ("doc_meta", "ocr_pages", "TEXT"),
    ("doc_meta", "edited_pages", "TEXT"),
    ("doc_meta", "overrides", "TEXT"),
    ("doc_meta", "removed_tags", "TEXT"),
    ("financials", "overrides", "TEXT"),
]


@contextmanager
def open_db(db_path: Path, actor: str = "aagam") -> Iterator[Vault]:
    """One connection per use, as the core does; AAGAM's tables are created on first use."""
    with Vault.open(db_path, actor=actor) as vault:
        migrate(vault.conn)
        yield vault


def migrate(conn: sqlite3.Connection) -> None:
    try:
        row = conn.execute("SELECT value FROM aagam_meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError:
        row = None
    if row and row[0] == SCHEMA_VERSION:
        return
    schema = resources.files("aagam").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    for table, column, kind in ADDED_COLUMNS:
        if column not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
    if not row:
        # Pages ingested before the index existed get indexed now.
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES ('rebuild')")
    conn.execute(
        "INSERT INTO aagam_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCHEMA_VERSION,),
    )
    conn.commit()
