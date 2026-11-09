"""Read-only access to the CRM (schema: src/claim_replay/crm_schema.sql)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Contact:
    name: str
    title: str | None
    persona: str | None


@dataclass(frozen=True)
class Activity:
    kind: str
    occurred_at: str
    subject: str | None
    body: str

    def render(self) -> str:
        heading = f"[{self.occurred_at[:10]}] {self.kind.upper()}"
        if self.subject:
            heading += f": {self.subject}"
        return f"{heading}\n{self.body.strip()}"


@dataclass(frozen=True)
class Deal:
    id: int
    name: str
    account: str
    industry: str
    employees: int | None
    amount: float | None
    stage: str
    status: str
    competitor: str | None
    owner: str | None
    created_at: str
    closed_at: str | None


@dataclass(frozen=True)
class DealRecord:
    """Everything the CRM knows about one deal, activities oldest first."""

    deal: Deal
    contacts: tuple[Contact, ...]
    activities: tuple[Activity, ...]
    qualification: dict[str, str]

    def fingerprint(self) -> str:
        """Changes whenever anything the replay is based on changes."""
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def header(self) -> str:
        d = self.deal
        amount = f"${d.amount:,.0f}/yr" if d.amount else "amount unknown"
        lines = [
            f"DEAL {d.id}: {d.name}",
            f"Account: {d.account} ({d.industry}, {d.employees or '?'} employees)",
            f"Value: {amount} | Status: {d.status} | Opened {d.created_at[:10]}"
            + (f" | Closed {d.closed_at[:10]}" if d.closed_at else ""),
            f"Competing vendor: {d.competitor or 'none (status quo)'}",
        ]
        if self.contacts:
            lines.append("People: " + "; ".join(
                f"{c.name} ({c.title or 'unknown title'})" for c in self.contacts))
        if self.qualification:
            lines.append("Qualification notes: " + "; ".join(
                f"{k.replace('_', ' ')}: {v}" for k, v in sorted(self.qualification.items())))
        return "\n".join(lines)


class CRM:
    def __init__(self, path: Path):
        if not Path(path).exists():
            raise FileNotFoundError(f"CRM database not found: {path} (try `claim-replay demo-data`)")
        self._uri = f"{Path(path).resolve().as_uri()}?mode=ro"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def won_deal_ids(self) -> list[int]:
        """Won deals, most recently closed first, so a limited run covers the freshest wins."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id FROM sales_deals WHERE status = 'won' ORDER BY closed_at DESC, id")
            return [r["id"] for r in rows]

    def load(self, deal_id: int) -> DealRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """SELECT id, name, account_name AS account, industry, employees, amount, stage, status,
                          competitor, owner, created_at, closed_at, meddpicc
                   FROM sales_deals WHERE id = ?""",
                (deal_id,),
            ).fetchone()
            if row is None:
                return None
            contacts = conn.execute(
                "SELECT name, title, persona FROM deal_contacts WHERE deal_id = ? ORDER BY id", (deal_id,)
            ).fetchall()
            activities = conn.execute(
                "SELECT kind, occurred_at, subject, body FROM deal_activities WHERE deal_id = ? ORDER BY occurred_at, id",
                (deal_id,),
            ).fetchall()
        return DealRecord(
            deal=Deal(**{name: row[name] for name in Deal.__dataclass_fields__}),
            contacts=tuple(Contact(**dict(c)) for c in contacts),
            activities=tuple(Activity(**dict(a)) for a in activities),
            qualification=parse_meddpicc(row["meddpicc"]),
        )


def parse_meddpicc(raw: str | None) -> dict[str, str]:
    """The MEDDPICC JSON column as {element: value}, keeping only filled-in values.

    A malformed value reads as "nothing known yet" rather than failing the
    whole deal: a bad edit in the CRM should not take a brief down with it.
    """
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip() for k, v in data.items()
            if isinstance(v, str | int | float) and str(v).strip()}
