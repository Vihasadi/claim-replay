"""Async client for any OpenAI-compatible chat endpoint: OpenAI, Ollama, vLLM, LM Studio.

The rest of the package depends only on the `ChatModel` protocol, so tests
pass in a scripted fake and nothing else needs to know which server is used.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from openai import AsyncOpenAI

from claim_replay.config import LLMConfig


class ChatModel(Protocol):
    async def complete(self, system: str, user: str, *, json: bool = False) -> str: ...


class OpenAIChat:
    def __init__(self, cfg: LLMConfig):
        self.name = cfg.model
        self._cfg = cfg
        self._client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=cfg.timeout_s,
                                   max_retries=2)
        self._gate = asyncio.Semaphore(cfg.concurrency)

    async def complete(self, system: str, user: str, *, json: bool = False) -> str:
        extra = {"response_format": {"type": "json_object"}} if json else {}
        async with self._gate:
            response = await self._client.chat.completions.create(
                model=self._cfg.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=self._cfg.reply_tokens,
                temperature=0.2,
                **extra,
            )
        return response.choices[0].message.content or ""

    async def aclose(self) -> None:
        await self._client.close()
