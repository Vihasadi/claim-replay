import asyncio
import sqlite3
from contextlib import closing

from claim_replay import prompts
from claim_replay.budget import estimate_tokens
from claim_replay.crm import CRM, parse_meddpicc
from claim_replay.pipeline import run
from claim_replay.replayer import Replayer
from claim_replay.schema import PartNotes, Replay
from claim_replay.store import ReplayStore
from claim_replay.structured import prompt_tokens
from conftest import ScriptedModel


def _run(crm_path, store, model, **kwargs):
    return asyncio.run(run(CRM(crm_path), store, model, model_name="test", prompt_budget=20_000, **kwargs))


def test_demo_crm_has_won_open_and_lost_deals(crm_path):
    with closing(sqlite3.connect(crm_path)) as conn:
        statuses = {s for (s,) in conn.execute("SELECT status FROM sales_deals")}
    assert statuses == {"won", "open", "lost"}


def test_meddpicc_column_is_parsed_leniently():
    assert parse_meddpicc('{"pain": " slow reports ", "metrics": "", "champion": null, "budget": 5}') == \
        {"pain": "slow reports", "budget": "5"}
    assert parse_meddpicc("not json") == {} and parse_meddpicc("[1, 2]") == {} and parse_meddpicc(None) == {}


def test_load_returns_the_full_record_in_date_order(crm_path):
    crm = CRM(crm_path)
    record = crm.load(crm.won_deal_ids()[0])
    dates = [a.occurred_at for a in record.activities]
    assert dates == sorted(dates)
    assert record.deal.status == "won" and "champion" in record.qualification
    assert record.deal.account in record.header()


def test_run_replays_every_won_deal_then_skips_unchanged_ones(crm_path, tmp_path):
    store = ReplayStore(tmp_path / "replays.sqlite3")
    first = _run(crm_path, store, ScriptedModel())
    assert first.replayed == first.won > 0 and first.failed == 0
    assert store.count() == first.won

    second = _run(crm_path, store, ScriptedModel())
    assert second.replayed == 0 and second.up_to_date == first.won


def test_a_changed_deal_is_replayed_again(crm_path, tmp_path):
    store = ReplayStore(tmp_path / "replays.sqlite3")
    _run(crm_path, store, ScriptedModel())
    deal_id = CRM(crm_path).won_deal_ids()[0]
    with closing(sqlite3.connect(crm_path)) as conn, conn:
        conn.execute("INSERT INTO deal_activities (deal_id, kind, occurred_at, body) VALUES (?, 'note', '2027-01-01', 'x')",
                     (deal_id,))
    assert _run(crm_path, store, ScriptedModel()).replayed == 1


def test_one_failing_deal_does_not_stop_the_others(crm_path, tmp_path):
    crm = CRM(crm_path)
    bad = crm.load(crm.won_deal_ids()[0]).deal.account
    model = ScriptedModel(lambda s, u: "server error" if bad in u else ScriptedModel()._respond(s, u))

    stats = _run(crm_path, ReplayStore(tmp_path / "r.sqlite3"), model)
    assert stats.failed == 1 and stats.replayed == stats.won - 1


def test_limit_caps_the_number_of_replays(crm_path, tmp_path):
    stats = _run(crm_path, ReplayStore(tmp_path / "r.sqlite3"), ScriptedModel(), limit=2)
    assert stats.replayed == 2


def test_long_history_is_read_in_parts_then_combined(crm_path):
    crm = CRM(crm_path)
    record = max((crm.load(i) for i in crm.won_deal_ids()), key=lambda r: len(r.activities))
    model = ScriptedModel()

    # Leave room for roughly one activity beyond the fixed prompt cost, forcing several parts.
    fixed = max(prompt_tokens(prompts.REPLAY_SYSTEM, Replay), prompt_tokens(prompts.PART_SYSTEM, PartNotes))
    budget = fixed + estimate_tokens(record.header()) + 64 + 120
    result = asyncio.run(Replayer(model, prompt_budget=budget).replay(record))
    assert result.parts > 1
    part_calls = [c for c in model.calls if "one part at a time" in c[0]]
    assert len(part_calls) == result.parts
    assert "read in parts" in model.calls[-1][1]
