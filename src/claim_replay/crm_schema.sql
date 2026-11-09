-- The CRM tables ClaimReplay reads. `claim-replay demo-data` creates a SQLite
-- file with this schema and fills it with invented deals.

-- One row per deal. The account's details live on the deal, and the MEDDPICC
-- qualification is a JSON object: {"metrics": "...", "champion": "...", ...}.
-- A key that is missing or empty means that element is still unknown.
CREATE TABLE sales_deals (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    account_name  TEXT    NOT NULL,
    industry      TEXT    NOT NULL,
    employees     INTEGER,
    region        TEXT,
    amount        REAL,                 -- annual contract value, USD
    stage         TEXT    NOT NULL,
    status        TEXT    NOT NULL CHECK (status IN ('open', 'won', 'lost')),
    competitor    TEXT,                 -- NULL: no competing vendor (status quo)
    owner         TEXT,
    meddpicc      TEXT    NOT NULL DEFAULT '{}',
    created_at    TEXT    NOT NULL,     -- ISO 8601
    closed_at     TEXT,
    updated_at    TEXT    NOT NULL
);

-- The people involved in a deal. Persona is their role in THIS deal.
CREATE TABLE deal_contacts (
    id       INTEGER PRIMARY KEY,
    deal_id  INTEGER NOT NULL REFERENCES sales_deals (id),
    name     TEXT    NOT NULL,
    title    TEXT,
    persona  TEXT    -- champion, economic_buyer, security, user, procurement
);

-- Calls, emails, meetings and rep notes, in the rep's own words.
CREATE TABLE deal_activities (
    id          INTEGER PRIMARY KEY,
    deal_id     INTEGER NOT NULL REFERENCES sales_deals (id),
    kind        TEXT    NOT NULL CHECK (kind IN ('call', 'email', 'meeting', 'note')),
    occurred_at TEXT    NOT NULL,
    subject     TEXT,
    body        TEXT    NOT NULL
);

CREATE INDEX idx_deal_contacts_deal ON deal_contacts (deal_id);
CREATE INDEX idx_deal_activities_deal ON deal_activities (deal_id, occurred_at);
CREATE INDEX idx_sales_deals_status ON sales_deals (status, closed_at);
