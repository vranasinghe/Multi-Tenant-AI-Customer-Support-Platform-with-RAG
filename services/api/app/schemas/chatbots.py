"""Request/response models for chatbots.

Request models forbid unknown fields, so a body can never carry ``org_id``, ``public_key``,
``created_by`` or timestamps. Field-level limits mirror the CHECK constraints in migration 0003;
cross-field rules that depend on the catalog (model limits, fixed language) live in
``app.services.chatbots.service`` because a PATCH must be validated against the merged result.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints, field_validator

from app.schemas.auth import OutModel, StrictModel

# Control characters other than tab/newline/carriage return are rejected: NUL can't be stored in
# Postgres text, and the rest only ever show up in pasted junk or injection attempts.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _no_control_chars(value: str) -> str:
    if _CONTROL.search(value):
        msg = "Must not contain control characters"
        raise ValueError(msg)
    return value


def _hex_color(value: str) -> str:
    if not _HEX_COLOR.match(value):
        msg = "Must be a hex color like #4F46E5"
        raise ValueError(msg)
    return value.upper()


def _https_url(value: str) -> str:
    lowered = value.lower()
    if not lowered.startswith("https://") or len(value) > 2048 or any(c.isspace() for c in value):
        msg = "Must be an https:// URL"
        raise ValueError(msg)
    return value


ChatbotName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_no_control_chars),
]
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_no_control_chars)
]
Instructions = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=4000),
    AfterValidator(_no_control_chars),
]
LauncherLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=40), AfterValidator(_no_control_chars)
]
HexColor = Annotated[str, AfterValidator(_hex_color)]
HttpsUrl = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_https_url)]
LanguageTag = Annotated[str, StringConstraints(min_length=2, max_length=10)]
ModelId = Annotated[str, StringConstraints(min_length=1, max_length=64)]

Status = Literal["draft", "active", "paused", "archived"]
Tone = Literal["professional", "friendly", "concise", "custom"]
ResponseLength = Literal["concise", "balanced", "detailed"]
LanguageMode = Literal["auto", "fixed"]
Position = Literal["bottom-right", "bottom-left"]
Temperature = Annotated[float, Field(ge=0, le=1)]
MaxOutputTokens = Annotated[int, Field(ge=64, le=4096)]
TopK = Annotated[int, Field(ge=1, le=12)]

DEFAULT_PRIMARY_COLOR = "#4F46E5"
DEFAULT_ACCENT_COLOR = "#FFFFFF"


class WidgetSettings(StrictModel):
    primary_color: HexColor = DEFAULT_PRIMARY_COLOR
    accent_color: HexColor = DEFAULT_ACCENT_COLOR
    avatar_url: HttpsUrl | None = None
    position: Position = "bottom-right"
    launcher_label: LauncherLabel = "Chat with us"
    show_branding: bool = True


class WidgetSettingsPatch(StrictModel):
    primary_color: HexColor | None = None
    accent_color: HexColor | None = None
    avatar_url: HttpsUrl | None = None  # explicit null clears the avatar
    position: Position | None = None
    launcher_label: LauncherLabel | None = None
    show_branding: bool | None = None

    @field_validator("primary_color", "accent_color", "position", "launcher_label", "show_branding")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Only `avatar_url` may be cleared; for the rest `null` would mean "unset a required
        # value", so it is rejected rather than silently ignored.
        if value is None:
            msg = "Must not be null"
            raise ValueError(msg)
        return value


class CreateChatbotRequest(StrictModel):
    name: ChatbotName
    description: ShortText = ""
    status: Literal["draft", "active"] = "draft"
    instructions: Instructions = ""
    tone: Tone = "professional"
    response_length: ResponseLength = "balanced"
    welcome_message: ShortText = "Hi! How can I help you today?"
    fallback_message: ShortText = (
        "I'm not sure about that. Could you rephrase, or contact our support team?"
    )
    language_mode: LanguageMode = "auto"
    language: LanguageTag | None = None
    model: ModelId | None = None  # default model from the registry
    temperature: Temperature = 0.2
    max_output_tokens: MaxOutputTokens = 600
    strict_grounding: bool = True
    show_sources: bool = True
    retrieval_top_k: TopK = 6
    widget_settings: WidgetSettings = Field(default_factory=WidgetSettings)


class UpdateChatbotRequest(StrictModel):
    """JSON Merge Patch: omitted = unchanged. Only ``language`` may be set to null."""

    name: ChatbotName | None = None
    description: ShortText | None = None
    status: Status | None = None
    instructions: Instructions | None = None
    tone: Tone | None = None
    response_length: ResponseLength | None = None
    welcome_message: ShortText | None = None
    fallback_message: ShortText | None = None
    language_mode: LanguageMode | None = None
    language: LanguageTag | None = None
    model: ModelId | None = None
    temperature: Temperature | None = None
    max_output_tokens: MaxOutputTokens | None = None
    strict_grounding: bool | None = None
    show_sources: bool | None = None
    retrieval_top_k: TopK | None = None
    widget_settings: WidgetSettingsPatch | None = None

    @field_validator(
        "name",
        "description",
        "status",
        "instructions",
        "tone",
        "response_length",
        "welcome_message",
        "fallback_message",
        "language_mode",
        "model",
        "temperature",
        "max_output_tokens",
        "strict_grounding",
        "show_sources",
        "retrieval_top_k",
        "widget_settings",
    )
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            msg = "Must not be null"
            raise ValueError(msg)
        return value


class ChatbotCreator(OutModel):
    id: uuid.UUID
    name: str


class ChatbotOut(OutModel):
    id: uuid.UUID
    name: str
    description: str
    status: str
    public_key: str
    instructions: str
    tone: str
    response_length: str
    welcome_message: str
    fallback_message: str
    language_mode: str
    language: str | None
    model: str
    temperature: float
    max_output_tokens: int
    strict_grounding: bool
    show_sources: bool
    retrieval_top_k: int
    widget_settings: WidgetSettings
    created_by: ChatbotCreator | None
    created_at: datetime
    updated_at: datetime


class ChatbotList(OutModel):
    data: list[ChatbotOut]
    limit: int  # the organization's chatbot allowance (static plan until billing ships)


class ModelOut(OutModel):
    id: str
    label: str
    provider: str
    description: str
    max_output_tokens: int
    tier: str
    default: bool


class LanguageOut(OutModel):
    code: str
    label: str


class ChatbotOptions(OutModel):
    models: list[ModelOut]
    languages: list[LanguageOut]
    tones: list[str]
    response_lengths: list[str]
    statuses: list[str]
    chatbot_limit: int
