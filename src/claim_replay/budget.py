"""Token estimates, and fitting text into a prompt budget.

The estimate is deliberately simple and provider-neutral: about 3.5
characters per token for English business prose, rounded up. It is
conservative for most tokenizers, and `LLMConfig.prompt_budget` keeps
another 10% in reserve. Because the estimate is a pure function of length,
clipping can compute the exact cut in one step instead of measuring and
retrying.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

CHARS_PER_TOKEN = 3.5
CUT_MARK = "\n[... trimmed to fit ...]\n"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def clip(text: str, max_tokens: int, *, head_share: float = 0.65) -> str:
    """Shorten `text` to `max_tokens` by cutting out its middle.

    The start (how the deal opened) and the end (how it closed) are usually
    the parts that matter, so both are kept: `head_share` of the room goes
    to the start, the rest to the end.
    """
    if estimate_tokens(text) <= max_tokens:
        return text
    room = int(max_tokens * CHARS_PER_TOKEN) - len(CUT_MARK)
    if room <= 0:
        return CUT_MARK.strip()
    head = int(room * head_share)
    tail = room - head
    return text[:head] + CUT_MARK + (text[-tail:] if tail else "")


def pack(blocks: Sequence[str], max_tokens: int, *, separator: str = "\n\n") -> list[str]:
    """Join consecutive blocks into as few chunks as possible, each within `max_tokens`.

    Order is kept and a block is never split across chunks; a block that is
    too big on its own is clipped and becomes its own chunk. Returns at least
    one chunk.
    """
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if estimate_tokens(block) > max_tokens:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(clip(block, max_tokens))
            continue
        candidate = f"{current}{separator}{block}" if current else block
        if estimate_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            chunks.append(current)
            current = block
    if current or not chunks:
        chunks.append(current)
    return chunks
