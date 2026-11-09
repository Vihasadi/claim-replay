"""Settings, read from environment variables and an optional `.env` file.

Nothing happens at import time: call `load_settings()` once in the entry
point and hand the result to whatever needs it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    """A required setting is missing or a value is invalid."""


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = "http://localhost:11434/v1"   # Ollama's OpenAI-compatible endpoint
    model: str = ""
    api_key: str = "unused"                       # local servers ignore it
    context_tokens: int = 32_000
    reply_tokens: int = 1_500
    concurrency: int = 4
    timeout_s: float = 180.0

    @property
    def prompt_budget(self) -> int:
        """Tokens a prompt may use. Token counts are estimates, so 10% is held back."""
        return int((self.context_tokens - self.reply_tokens) * 0.9)


@dataclass(frozen=True)
class Settings:
    crm_db: Path = Path("data/crm.sqlite3")
    replay_db: Path = Path("data/replays.sqlite3")
    llm: LLMConfig = field(default_factory=LLMConfig)


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _env_int(name: str, default: int, problems: list[str]) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError:
        problems.append(f"{name} must be a whole number (got {raw!r})")
        return default


def load_settings(env_file: Path | None = None, *, need_llm: bool = True) -> Settings:
    """Build Settings from the environment. Variables already set win over the .env file.

    Raises ConfigError naming every problem at once, so a bad config is fixed in one pass.
    """
    load_dotenv(env_file or Path(".env"), override=False)
    problems: list[str] = []
    llm = LLMConfig(
        base_url=_env("LLM_BASE_URL", LLMConfig.base_url),
        model=_env("LLM_MODEL", ""),
        api_key=_env("LLM_API_KEY", LLMConfig.api_key),
        context_tokens=_env_int("LLM_CONTEXT_TOKENS", LLMConfig.context_tokens, problems),
        reply_tokens=_env_int("LLM_REPLY_TOKENS", LLMConfig.reply_tokens, problems),
        concurrency=_env_int("LLM_CONCURRENCY", LLMConfig.concurrency, problems),
    )
    if need_llm and not llm.model:
        problems.append("LLM_MODEL is not set")
    if llm.concurrency < 1:
        problems.append("LLM_CONCURRENCY must be at least 1")
    if llm.prompt_budget < 2_000:
        problems.append("LLM_CONTEXT_TOKENS is too small for LLM_REPLY_TOKENS (need ~2k tokens of prompt room)")
    if problems:
        raise ConfigError("; ".join(problems))
    return Settings(
        crm_db=Path(_env("CRM_DB_PATH", str(Settings.crm_db))),
        replay_db=Path(_env("REPLAY_DB_PATH", str(Settings.replay_db))),
        llm=llm,
    )
