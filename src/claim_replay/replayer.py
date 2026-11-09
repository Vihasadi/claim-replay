"""Turns one deal record into a Replay.

Short histories go to the model in a single call. Long ones are read
map-reduce style: the activities are packed into parts that each fit the
budget, every part is summarized into notes (in parallel), and a final call
writes the replay from the notes. Activities are never split mid-way, and
nothing is silently dropped: an activity too long on its own is clipped
with a visible marker.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from claim_replay import prompts
from claim_replay.budget import clip, estimate_tokens, pack
from claim_replay.crm import DealRecord
from claim_replay.llm import ChatModel
from claim_replay.schema import PartNotes, Replay
from claim_replay.structured import ask, prompt_tokens

_SLACK = 64  # labels and blank lines added around the sections


@dataclass(frozen=True)
class ReplayResult:
    replay: Replay
    parts: int  # 1 when the history fit in one call


class Replayer:
    def __init__(self, model: ChatModel, prompt_budget: int):
        self._model = model
        self._budget = prompt_budget

    async def replay(self, record: DealRecord) -> ReplayResult:
        header = clip(record.header(), self._budget // 4)
        blocks = [a.render() for a in record.activities]
        history = "\n\n".join(blocks) or "(no activities recorded)"

        room = self._budget - prompt_tokens(prompts.REPLAY_SYSTEM, Replay) - estimate_tokens(header) - _SLACK
        if estimate_tokens(history) <= room:
            replay = await ask(self._model, prompts.REPLAY_SYSTEM, f"{header}\n\nHISTORY\n{history}", Replay)
            return ReplayResult(replay, parts=1)

        part_room = self._budget - prompt_tokens(prompts.PART_SYSTEM, PartNotes) - estimate_tokens(header) - _SLACK
        parts = pack(blocks, part_room)
        notes = await asyncio.gather(*(
            ask(self._model, prompts.PART_SYSTEM, f"{header}\n\nPART {i} OF {len(parts)}\n{part}", PartNotes)
            for i, part in enumerate(parts, start=1)
        ))
        combined = clip("\n\n".join(_render_notes(i, n) for i, n in enumerate(notes, start=1)), room)
        replay = await ask(
            self._model, prompts.REPLAY_SYSTEM, f"{header}\n\n{prompts.COMBINE_PREAMBLE}\n\n{combined}", Replay
        )
        return ReplayResult(replay, parts=len(parts))


def _render_notes(index: int, notes: PartNotes) -> str:
    lines = [f"NOTES, PART {index}"]
    lines += [f"- {event}" for event in notes.events]
    lines += [f"- Objection: {o.objection} | Response: {o.response} | {o.outcome}" for o in notes.objections]
    lines += [f"- Person: {s.name} ({s.title or '?'}), {s.role_in_deal}" for s in notes.stakeholders]
    return "\n".join(lines)
