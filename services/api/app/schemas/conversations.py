"""Explicit bounded conversation input; no client-supplied roles, history or tenant identity."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints

from app.schemas.auth import OutModel, StrictModel
from app.schemas.chatbots import _no_control_chars

ConversationStatus = Literal["open", "resolved", "unresolved", "handed_off"]
HandoffStatus = Literal["requested", "acknowledged", "completed", "cancelled"]
UnansweredReason = Literal[
    "insufficient_evidence", "marked_unanswered", "ambiguous_query", "provider_failure"
]
ChannelFilter = Literal["playground", "widget"]
FeedbackFilter = Literal["positive", "negative"]
SatisfactionFilter = Literal["positive", "negative"]


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
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(_no_control_chars),
]
ContactText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_no_control_chars),
]


class SendMessage(StrictModel):
    content: Question
    context_messages: int | None = Field(default=None, ge=0, le=50)


class Feedback(StrictModel):
    rating: int = Field(ge=-1, le=1)


class SatisfactionBody(StrictModel):
    score: int = Field(ge=1, le=5)
    comment: ShortText | None = None


class StatusBody(StrictModel):
    status: Literal["open", "resolved", "unresolved"]


class HandoffRequestBody(StrictModel):
    reason: ShortText
    contact: ContactText | None = None


class HandoffUpdateBody(StrictModel):
    status: Literal["acknowledged", "completed", "cancelled"]


class MarkUnansweredBody(StrictModel):
    reason: Literal["marked_unanswered", "ambiguous_query"] = "marked_unanswered"


class ConversationSummary(OutModel):
    id: UUID
    chatbot_id: UUID
    chatbot_name: str
    channel: str
    status: str
    preview: str
    satisfaction_score: int | None
    handoff_status: str | None
    unanswered_count: int
    last_message_at: datetime
    created_at: datetime


class ConversationList(OutModel):
    data: list[ConversationSummary]
    next_cursor: str | None
    has_more: bool
    total: int


class ConversationEventOut(OutModel):
    id: UUID
    kind: str
    payload: dict[str, Any]
    actor_type: str
    created_at: datetime


class ConversationDetail(OutModel):
    id: UUID
    chatbot_id: UUID
    chatbot_name: str
    channel: str
    status: str
    preview: str
    satisfaction_score: int | None
    satisfaction_comment: str | None
    handoff_status: str | None
    handoff_reason: str | None
    handoff_contact: str | None
    created_at: datetime
    last_message_at: datetime
    messages: list[dict[str, Any]]
    events: list[ConversationEventOut]


class UnansweredGroup(OutModel):
    representative: str
    cluster_key: str
    count: int
    chatbot_id: UUID
    chatbot_name: str
    last_asked_at: datetime
    sample_conversation_ids: list[UUID]
    reason: str


class UnansweredList(OutModel):
    data: list[UnansweredGroup]


class KnowledgeGap(OutModel):
    cluster_key: str
    representative: str
    count: int
    chatbot_id: UUID
    chatbot_name: str
    last_asked_at: datetime
    reasons: dict[str, int]


class KnowledgeGapList(OutModel):
    data: list[KnowledgeGap]


class ExportCreate(StrictModel):
    chatbot_id: UUID | None = None
    channel: ChannelFilter | None = None
    from_at: datetime | None = None
    to_at: datetime | None = None
    status: ConversationStatus | None = None


class ExportOut(OutModel):
    id: UUID
    status: str
    row_count: int
    created_at: datetime
    expires_at: datetime
    download_path: str
