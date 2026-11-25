"""Explicit bounded conversation input; no client-supplied roles, history or tenant identity."""

from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from app.schemas.auth import StrictModel
from app.schemas.chatbots import _no_control_chars


def _valid_unicode(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("Must contain valid Unicode text") from None
    return value


Question = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    AfterValidator(_no_control_chars),
    AfterValidator(_valid_unicode),
]


class SendMessage(StrictModel):
    content: Question
    context_messages: int | None = Field(default=None, ge=0, le=50)


class Feedback(StrictModel):
    rating: int = Field(ge=-1, le=1)
