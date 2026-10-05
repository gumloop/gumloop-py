"""OpenRouter Decisions models, named as in ``openrouter.components`` 1.3.14;
the pinned ``openrouter`` predates them."""

from __future__ import annotations

from typing import Annotated
from typing import Any
from typing import Literal

from openrouter.components import ProviderPreferences
from pydantic import BaseModel
from pydantic import Field

Json = str | dict[str, Any] | list[Any]


class DecisionsNoulQuestionCriteria(BaseModel):
    true: Json | None = None
    false: Json | None = None


class DecisionsNoulQuestion(BaseModel):
    type: Literal["noul"]
    instructions: Json
    criteria: DecisionsNoulQuestionCriteria | None = None


class DecisionsChoiceQuestion(BaseModel):
    type: Literal["choice"]
    instructions: Json
    criteria: dict[str, Json | None]


class DecisionsScoreQuestion(BaseModel):
    type: Literal["score"]
    instructions: Json
    criteria: list[Json]


DecisionsQuestion = Annotated[
    DecisionsNoulQuestion | DecisionsChoiceQuestion | DecisionsScoreQuestion,
    Field(discriminator="type"),
]


class TraceConfig(BaseModel):
    trace_id: str | None = None
    trace_name: str | None = None
    span_name: str | None = None
    generation_name: str | None = None
    parent_span_id: str | None = None


class DecisionsRequest(BaseModel):
    model: str
    state: Json
    questions: dict[str, DecisionsQuestion]
    provider: ProviderPreferences | None = None
    session_id: str | None = Field(default=None, max_length=256)
    trace: TraceConfig | None = None
    user: str | None = None


class DecisionsNoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float


class DecisionsChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    confidence: float | None = None
    probabilities: dict[str, float] | None = None


class DecisionsScoreAnswer(BaseModel):
    type: Literal["score"]
    score: float
    confidence: float | None = None
    legend: dict[str, Json] | None = None
    probabilities: dict[str, float] | None = None


DecisionsAnswer = Annotated[
    DecisionsNoulAnswer | DecisionsChoiceAnswer | DecisionsScoreAnswer,
    Field(discriminator="type"),
]


class DecisionsResponseUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost: float | None = None


class DecisionsResponse(BaseModel):
    answers: dict[str, DecisionsAnswer]
    model: str
    usage: DecisionsResponseUsage
    id: str | None = None
    provider: str | None = None
