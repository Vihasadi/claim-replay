"""One run: find won deals whose replay is missing or out of date, and replay them.

A deal is redone only when its fingerprint changed (a new activity, an
edited note, a corrected amount), so re-running is cheap and safe. Deals
are replayed concurrently, and each result is saved as soon as it is ready:
a crash halfway through loses nothing that was already finished. One deal
failing never stops the others; it is logged and retried on the next run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from claim_replay import prompts
from claim_replay.crm import CRM, DealRecord
from claim_replay.llm import ChatModel
from claim_replay.replayer import Replayer
from claim_replay.store import ReplayStore

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    won: int = 0
    up_to_date: int = 0
    replayed: int = 0
    failed: int = 0
    seconds: float = 0.0


async def run(
    crm: CRM,
    store: ReplayStore,
    model: ChatModel,
    *,
    model_name: str,
    prompt_budget: int,
    limit: int | None = None,
    force: bool = False,
) -> RunStats:
    started = time.perf_counter()
    stats = RunStats()
    done = {} if force else store.fingerprints()

    todo: list[DealRecord] = []
    for deal_id in crm.won_deal_ids():
        stats.won += 1
        if limit is not None and len(todo) >= limit:
            continue
        record = crm.load(deal_id)
        if record is None:
            continue
        if done.get(deal_id) == record.fingerprint():
            stats.up_to_date += 1
        else:
            todo.append(record)

    replayer = Replayer(model, prompt_budget)

    async def replay_one(record: DealRecord) -> None:
        deal_id = record.deal.id
        try:
            result = await replayer.replay(record)
        except Exception as exc:  # noqa: BLE001 - one bad deal must not stop the run
            stats.failed += 1
            # Only the id and error type are logged: deal text can hold customer details.
            logger.warning("deal %s failed: %s", deal_id, type(exc).__name__)
            return
        store.save(record, result.replay, parts=result.parts, model=model_name,
                   prompt_version=prompts.PROMPT_VERSION)
        stats.replayed += 1
        logger.info("deal %s replayed (%d part%s)", deal_id, result.parts, "" if result.parts == 1 else "s")

    await asyncio.gather(*(replay_one(r) for r in todo))
    stats.seconds = round(time.perf_counter() - started, 1)
    logger.info("run finished: %s", stats)
    return stats
