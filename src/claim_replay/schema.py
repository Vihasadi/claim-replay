"""The shape of a replay. The model's JSON is validated against these models.

Lists are capped after validation instead of rejected: a model that names
seven winning moves gave a usable answer, and the first ones are the ones it
ranked highest.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


def _cap(n: int):
    return AfterValidator(lambda items: items[:n])


class ObjectionHandled(BaseModel):
    objection: str = Field(description="What the buyer pushed back on, in one sentence.")
    response: str = Field(description="What the seller did or said in reply, concretely.")
    outcome: Literal["resolved", "partly_resolved", "unresolved"]


class Stakeholder(BaseModel):
    name: str
    title: str | None = None
    role_in_deal: str = Field(description="e.g. champion, economic buyer, blocker, evaluator.")


class Replay(BaseModel):
    summary: str = Field(description="Two or three sentences: who bought, why, and why from us.")
    turning_point: str = Field(description="The single moment the deal tipped our way, and why.")
    winning_moves: Annotated[list[str], _cap(6)] = Field(
        description="Concrete seller actions that moved the deal forward, most important first.")
    objections: Annotated[list[ObjectionHandled], _cap(6)] = Field(default_factory=list)
    stakeholders: Annotated[list[Stakeholder], _cap(6)] = Field(default_factory=list)
    competitor_notes: str | None = Field(
        default=None, description="How we beat the competing vendor or the status quo; null if never discussed.")


class PartNotes(BaseModel):
    """Notes on one part of a history too long to read in a single call."""

    events: Annotated[list[str], _cap(12)] = Field(description="What happened, in order, one line each.")
    objections: Annotated[list[ObjectionHandled], _cap(6)] = Field(default_factory=list)
    stakeholders: Annotated[list[Stakeholder], _cap(6)] = Field(default_factory=list)
