"""The replay store: one SQLite row per won deal.

Besides the replay itself, each row carries the deal attributes downstream
tools group and filter on (industry, competitor, amount, close date), so
they never need access to the CRM. `fingerprint` records which version of
the deal the replay was written from.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from claim_replay.crm import DealRecord
from claim_replay.schema import Replay

_SCHEMA = """
CREATE TABLE IF NOT EXISTS deal_replays (
    deal_id        INTEGER PRIMARY KEY,
    fingerprint    TEXT    NOT NULL,
    account        TEXT    NOT NULL,
    industry       TEXT,
    competitor     TEXT,
    amount         REAL,
    closed_at      TEXT,
    replay_json    TEXT    NOT NULL,
    parts          INTEGER NOT NULL,
    model          TEXT    NOT NULL,
    prompt_version TEXT    NOT NULL,
    created_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deal_replays_competitor ON deal_replays (competitor, industry);
"""


class ReplayStore:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._path)) as conn:
            conn.executescript(_SCHEMA)

    def fingerprints(self) -> dict[int, str]:
        with closing(sqlite3.connect(self._path)) as conn:
            return dict(conn.execute("SELECT deal_id, fingerprint FROM deal_replays"))

    def save(self, record: DealRecord, replay: Replay, *, parts: int, model: str, prompt_version: str) -> None:
        """Insert or replace the replay for this deal."""
        d = record.deal
        row = (d.id, record.fingerprint(), d.account, d.industry, d.competitor, d.amount, d.closed_at,
               replay.model_dump_json(), parts, model, prompt_version, datetime.now(UTC).isoformat(timespec="seconds"))
        with closing(sqlite3.connect(self._path)) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO deal_replays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row
            )

    def get(self, deal_id: int) -> Replay | None:
        with closing(sqlite3.connect(self._path)) as conn:
            row = conn.execute("SELECT replay_json FROM deal_replays WHERE deal_id = ?", (deal_id,)).fetchone()
        return Replay.model_validate_json(row[0]) if row else None

    def count(self) -> int:
        with closing(sqlite3.connect(self._path)) as conn:
            return conn.execute("SELECT COUNT(*) FROM deal_replays").fetchone()[0]
