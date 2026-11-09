"""Structured output: ask for JSON, validate it with pydantic, and repair once if it doesn't fit.

Small local models get JSON almost right surprisingly often: a code fence
around it, a reasoning block before it, a missing field. The first two are
stripped here; the last is sent back to the model together with the
validation error, which fixes most of the rest.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from claim_replay.budget import estimate_tokens
from claim_replay.llm import ChatModel

T = TypeVar("T", bound=BaseModel)

_THINK = re.compile(r"<think>.*?</think>", re.S)


class StructuredOutputError(RuntimeError):
    """The model did not produce valid JSON for the schema, even after a repair attempt."""


def with_schema(system: str, schema: type[BaseModel]) -> str:
    """The system prompt plus the JSON schema the reply must follow."""
    spec = json.dumps(schema.model_json_schema(), separators=(",", ":"))
    return f"{system}\n\nReply with a single JSON object that follows this JSON schema:\n{spec}"


def prompt_tokens(system: str, schema: type[BaseModel]) -> int:
    return estimate_tokens(with_schema(system, schema))


def extract_json(text: str) -> str:
    """The outermost {...} in a reply, ignoring reasoning blocks and code fences."""
    text = _THINK.sub("", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in the reply")
    return text[start:end + 1]


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in exc.errors()[:8])
    return str(exc)


async def ask(model: ChatModel, system: str, user: str, schema: type[T], *, repairs: int = 1) -> T:
    """Get a reply that validates against `schema`, or raise StructuredOutputError."""
    full_system = with_schema(system, schema)
    reply = await model.complete(full_system, user, json=True)
    for attempt in range(repairs + 1):
        try:
            return schema.model_validate_json(extract_json(reply))
        except ValueError as exc:  # pydantic's ValidationError is a ValueError too
            if attempt == repairs:
                raise StructuredOutputError(_describe(exc)) from exc
            reply = await model.complete(
                full_system,
                f"{user}\n\n---\nYour previous reply:\n{reply}\n\nIt was rejected: {_describe(exc)}\n"
                "Send the corrected JSON object only.",
                json=True,
            )
    raise AssertionError("unreachable")
