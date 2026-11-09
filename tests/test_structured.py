import asyncio
import json

import pytest

from claim_replay.schema import Replay
from claim_replay.structured import StructuredOutputError, ask, extract_json
from conftest import REPLAY, ScriptedModel


@pytest.mark.parametrize("reply", [
    json.dumps(REPLAY),
    f"```json\n{json.dumps(REPLAY)}\n```",
    f"<think>let me see {{draft}}</think>Here it is: {json.dumps(REPLAY)}",
])
def test_extract_json_handles_common_wrappers(reply):
    assert Replay.model_validate_json(extract_json(reply)).turning_point == REPLAY["turning_point"]


def test_invalid_reply_is_repaired_with_the_error_message():
    replies = iter([json.dumps({"summary": "only this"}), json.dumps(REPLAY)])
    model = ScriptedModel(lambda s, u: next(replies))

    replay = asyncio.run(ask(model, "system", "user", Replay))
    assert replay.summary == REPLAY["summary"]
    assert len(model.calls) == 2
    assert "turning_point" in model.calls[1][1]  # the repair prompt names the missing field


def test_gives_up_after_the_repair_attempt():
    model = ScriptedModel(lambda s, u: "no json at all")
    with pytest.raises(StructuredOutputError):
        asyncio.run(ask(model, "system", "user", Replay))
    assert len(model.calls) == 2


def test_long_lists_are_capped_not_rejected():
    data = dict(REPLAY, winning_moves=[f"move {i}" for i in range(10)])
    assert len(Replay.model_validate(data).winning_moves) == 6


def test_schema_is_included_in_the_system_prompt():
    model = ScriptedModel()
    asyncio.run(ask(model, "BASE PROMPT", "user", Replay))
    system = model.calls[0][0]
    assert system.startswith("BASE PROMPT") and '"turning_point"' in system
