"""Test helpers: a scripted chat model and a small invented CRM."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from claim_replay import demo

REPLAY = {
    "summary": "They bought to stop bad data reaching executives.",
    "turning_point": "The proof of concept found issues their checks missed.",
    "winning_moves": ["Ran a two-week proof of concept", "Answered security the same day"],
    "objections": [{"objection": "Too expensive", "response": "Built a payback case", "outcome": "resolved"}],
    "stakeholders": [{"name": "Priya Okafor", "title": "Head of Data", "role_in_deal": "champion"}],
    "competitor_notes": None,
}
NOTES = {"events": ["Discovery call held"], "objections": [], "stakeholders": []}


class ScriptedModel:
    """Answers from a function of (system, user); records every call."""

    def __init__(self, respond: Callable[[str, str], str] | None = None):
        self.calls: list[tuple[str, str]] = []
        self._respond = respond or default_reply

    async def complete(self, system: str, user: str, *, json: bool = False) -> str:
        self.calls.append((system, user))
        return self._respond(system, user)


def default_reply(system: str, user: str) -> str:
    return json.dumps(NOTES if "one part at a time" in system else REPLAY)


@pytest.fixture
def crm_path(tmp_path: Path) -> Path:
    path = tmp_path / "crm.sqlite3"
    demo.generate(path, deals=12, seed=3)
    return path
