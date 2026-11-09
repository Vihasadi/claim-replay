"""A synthetic CRM for demos and tests.

Every company, person, competitor and number here is invented. The seller
is a fictional vendor of a data-quality monitoring platform; buyers are
mid-size companies whose dashboards keep breaking. The generator is
deterministic for a given seed, so tests can rely on its output.
"""

from __future__ import annotations

import json
import random
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path

INDUSTRIES = {
    "Logistics": ["Freight", "Logistics", "Haulage"],
    "Retail": ["Outfitters", "Market", "Goods"],
    "Fintech": ["Pay", "Ledger", "Capital"],
    "Manufacturing": ["Works", "Fabrication", "Industries"],
    "Media": ["Studios", "Media", "Press"],
    "Education": ["Learning", "Academy", "Campus"],
}
PREFIXES = ["Alder", "Bracken", "Cinder", "Dunmore", "Emberly", "Fallow", "Graniteview", "Hollis", "Ivorine",
            "Juniperhill", "Kestrel", "Lindenwood", "Marlow", "Nettlefield", "Oakhaven", "Pellham", "Quarrystone",
            "Rookwood", "Saltmarsh", "Thistledown"]
FIRST = ["Priya", "Marcus", "Elena", "Tomas", "Aisha", "Daniel", "Mei", "Jonas", "Farah", "Leo", "Nadia",
         "Owen", "Sofia", "Ravi", "Grace", "Mateo", "Hana", "Isaac", "Zara", "Caleb"]
LAST = ["Okafor", "Lindqvist", "Moreau", "Castillo", "Nakamura", "Brennan", "Haddad", "Varga", "Osei", "Kowalski",
        "Ferreira", "Iyer", "Sorensen", "Delgado", "Achterberg", "Mensah", "Rinaldi", "Quist", "Tanaka", "Abara"]
REPS = ["Jordan Ellis", "Sam Whitaker", "Alex Moreno", "Taylor Brooks"]
COMPETITORS = ["Corvane", "Stackwise", "Brightline", None]  # None: status quo / in-house scripts
REGIONS = ["North America", "EMEA", "APAC"]

PERSONAS = {
    "champion": ["Head of Data", "Data Engineering Manager", "Director of Analytics"],
    "economic_buyer": ["VP Engineering", "CFO", "CTO", "COO"],
    "security": ["CISO", "Security Lead"],
    "user": ["Analytics Engineer", "Senior Data Engineer"],
    "procurement": ["Procurement Manager", "Vendor Manager"],
}
PAINS = [
    "broken dashboards reached the executive team twice last quarter",
    "analysts lose most Mondays reconciling numbers by hand",
    "a bad upstream feed corrupted a month of billing data before anyone noticed",
    "nobody can say which tables are safe to build on",
    "the board report was delayed because revenue figures did not match",
]
METRICS = [
    "cut data incidents that reach business users by half",
    "free up the equivalent of two analysts",
    "catch bad data before the Monday executive report",
    "pass the next audit without manual spot checks",
]

# (objection raised by the buyer, response that wins it, weak response seen in lost deals)
OBJECTIONS = {
    "price": (
        "{buyer} said {rival} quoted about 20% less and asked whether we could match it.",
        "Rebuilt the business case with {champ} around the cost of one bad-data incident; payback came out under "
        "six months, and we offered a phased rollout instead of a discount.",
        "Offered a 10% discount; {buyer} said the gap was still too big.",
    ),
    "security": (
        "{buyer}'s security team will not move until they have a SOC 2 report and an answer on data residency.",
        "Sent the SOC 2 Type II report and DPA the same day and set up a call between {buyer} and our security "
        "lead; the review closed in nine days.",
        "The security questionnaire sat with our team for three weeks; {buyer} paused the evaluation.",
    ),
    "integration": (
        "Engineering worried the rollout would eat a quarter of their roadmap.",
        "Ran a two-week proof of concept on their noisiest pipeline; their team spent under three days on it and "
        "saw alerts on real issues.",
        "Shared the integration docs, but no proof of concept was scheduled.",
    ),
    "timing": (
        "{buyer} said budget is frozen until next quarter.",
        "Worked out the cost of waiting with {champ}: three incidents last quarter, each costing a week of "
        "analyst time. {buyer} approved pulling the budget forward.",
        "Agreed to check back next quarter.",
    ),
    "incumbent": (
        "They already pay for {rival} and switching feels risky to {buyer}.",
        "Proposed a side-by-side on five critical tables; we caught two schema changes that {rival} missed, "
        "and {champ} presented the results internally.",
        "Sent a comparison sheet; {buyer} decided switching was not worth the effort.",
    ),
}

QUALIFICATION_FIELDS = ["metrics", "economic_buyer", "decision_criteria", "decision_process", "paper_process",
                        "pain", "champion", "competition"]
OPEN_STAGES = ["discovery", "evaluation", "proposal", "negotiation"]


def schema_sql() -> str:
    return files("claim_replay").joinpath("crm_schema.sql").read_text(encoding="utf-8")


def _person(rng: random.Random, used: set[str]) -> str:
    while True:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name not in used:
            used.add(name)
            return name


def generate(path: Path, *, deals: int = 40, seed: int = 7) -> None:
    """Create (or replace) a SQLite CRM at `path` with `deals` invented deals."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    rng = random.Random(seed)
    start = datetime(2025, 1, 6, 9, 0)

    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(schema_sql())
        for deal_id in range(1, deals + 1):
            industry = rng.choice(list(INDUSTRIES))
            account = f"{PREFIXES[(deal_id - 1) % len(PREFIXES)]} {rng.choice(INDUSTRIES[industry])}"
            employees, region = rng.choice([180, 450, 900, 2200, 5000]), rng.choice(REGIONS)

            used: set[str] = set()
            contacts = []
            for persona in ("champion", "economic_buyer", "security", "user", "procurement"):
                contacts.append((_person(rng, used), rng.choice(PERSONAS[persona]), persona))
            people = {persona: name for name, _, persona in contacts}

            status = rng.choices(["won", "lost", "open"], weights=[5, 2, 3])[0]
            rival = rng.choice(COMPETITORS)
            amount = float(rng.choice([24, 36, 48, 60, 85, 120, 180]) * 1000)
            created = start + timedelta(days=rng.randint(0, 540))
            names = {"buyer": people["economic_buyer"], "champ": people["champion"],
                     "rival": rival or "their in-house scripts"}
            pain, metric = rng.choice(PAINS), rng.choice(METRICS)

            events: list[tuple[str, str, str]] = [(
                "call", "Discovery call",
                f"{names['champ']} explained the pain: {pain}. Today they rely on "
                f"{'a ' + rival + ' trial' if rival else 'hand-written SQL checks'}. Goal they named: {metric}.",
            )]
            raised = rng.sample(list(OBJECTIONS), k=rng.randint(1, 3))
            for i, key in enumerate(raised):
                ask, win, weak = OBJECTIONS[key]
                events.append(("email" if i % 2 else "call", f"Concern: {key}", ask.format(**names)))
                if status == "won" or (status == "open" and i < len(raised) - 1):
                    events.append(("note", f"Answered {key} concern", win.format(**names)))
                elif status == "lost":
                    events.append(("note", f"Answered {key} concern", weak.format(**names)))
            if status == "won":
                events.append(("meeting", "Proof of concept readout",
                               f"Proof of concept on {rng.randint(3, 9)} pipelines found {rng.randint(4, 15)} issues "
                               f"their current checks missed. {names['buyer']} joined and asked how fast we "
                               f"could {metric}."))
                events.append(("email", "Order form signed",
                               f"{people['procurement']} returned the signed order form for ${amount:,.0f}/year "
                               f"after a {rng.randint(5, 20)}-day legal review."))
            elif status == "lost":
                events.append(("note", "Closed lost",
                               f"Lost to {rival or 'the status quo'}. {names['buyer']} cited "
                               f"{rng.choice(['price', 'timing', 'switching effort'])}."))

            timeline, when = [], created
            for kind, subject, body in events:
                timeline.append((kind, when.isoformat(), subject, body))
                when += timedelta(days=rng.randint(3, 12), hours=rng.randint(0, 6))

            known = {
                "metrics": metric, "economic_buyer": names["buyer"], "pain": pain, "champion": names["champ"],
                "competition": rival or "status quo (in-house checks)",
                "decision_criteria": "time to value, security review, total cost",
                "decision_process": "champion recommends, economic buyer signs off, security must approve",
                "paper_process": f"{rng.randint(5, 20)}-day legal review, then procurement",
            }
            fill_rate = {"won": 1.0, "lost": 0.6, "open": 0.5}[status]
            meddpicc = {field: known[field] for field in QUALIFICATION_FIELDS
                        if field in ("pain", "champion") or rng.random() < fill_rate}

            closed = when.isoformat() if status != "open" else None
            stage = {"won": "closed_won", "lost": "closed_lost"}.get(status) or rng.choice(OPEN_STAGES)
            conn.execute(
                "INSERT INTO sales_deals (id, name, account_name, industry, employees, region, amount, stage, status, "
                "competitor, owner, meddpicc, created_at, closed_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (deal_id, f"{account} - data quality platform", account, industry, employees, region, amount, stage,
                 status, rival, rng.choice(REPS), json.dumps(meddpicc), created.isoformat(), closed, when.isoformat()))
            conn.executemany("INSERT INTO deal_contacts (deal_id, name, title, persona) VALUES (?, ?, ?, ?)",
                             [(deal_id, *c) for c in contacts])
            conn.executemany(
                "INSERT INTO deal_activities (deal_id, kind, occurred_at, subject, body) VALUES (?, ?, ?, ?, ?)",
                [(deal_id, *a) for a in timeline])
