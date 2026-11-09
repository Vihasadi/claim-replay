"""Command line.

    claim-replay demo-data            # write an invented CRM to data/crm.sqlite3
    claim-replay run [--limit N]      # replay won deals that are new or changed
    claim-replay run --force          # replay every won deal again
    claim-replay show DEAL_ID         # print a stored replay
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from claim_replay import demo
from claim_replay.config import ConfigError, Settings, load_settings
from claim_replay.crm import CRM
from claim_replay.llm import OpenAIChat
from claim_replay.pipeline import run
from claim_replay.store import ReplayStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claim-replay", description="Learn how each won deal was won.")
    parser.add_argument("--env-file", type=Path, help="path to a .env file (default: ./.env)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    data = sub.add_parser("demo-data", help="create an invented CRM for trying the pipeline")
    data.add_argument("--deals", type=int, default=40)
    data.add_argument("--seed", type=int, default=7)

    go = sub.add_parser("run", help="replay won deals that are new or changed since the last run")
    go.add_argument("--limit", type=int, help="replay at most this many deals")
    go.add_argument("--force", action="store_true", help="ignore fingerprints and redo every won deal")

    show = sub.add_parser("show", help="print the stored replay for one deal")
    show.add_argument("deal_id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    for noisy in ("httpx", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        settings = load_settings(args.env_file, need_llm=args.command == "run")
    except ConfigError as exc:
        print(f"Configuration error: {exc}\nSee .env.example.", file=sys.stderr)
        return 2

    if args.command == "demo-data":
        demo.generate(settings.crm_db, deals=args.deals, seed=args.seed)
        print(f"Wrote {args.deals} invented deals to {settings.crm_db}")
        return 0
    if args.command == "show":
        replay = ReplayStore(settings.replay_db).get(args.deal_id)
        if replay is None:
            print(f"No replay for deal {args.deal_id}", file=sys.stderr)
            return 1
        print(replay.model_dump_json(indent=2))
        return 0
    return asyncio.run(_run(settings, args.limit, args.force))


async def _run(settings: Settings, limit: int | None, force: bool) -> int:
    model = OpenAIChat(settings.llm)
    try:
        stats = await run(CRM(settings.crm_db), ReplayStore(settings.replay_db), model,
                          model_name=settings.llm.model, prompt_budget=settings.llm.prompt_budget,
                          limit=limit, force=force)
    finally:
        await model.aclose()
    print(f"won deals: {stats.won} | up to date: {stats.up_to_date} | replayed: {stats.replayed} | "
          f"failed: {stats.failed} | {stats.seconds}s")
    return 1 if stats.failed and not stats.replayed else 0


if __name__ == "__main__":
    sys.exit(main())
