"""Chatbot configuration catalog: the model allowlist and supported languages.

Config, not database, in the MVP (docs/ARCHITECTURE.md "Model registry"). The API validates every
chatbot write against this catalog, and the dashboard renders its pickers from the same data via
``GET /orgs/{org_id}/chatbot-options``, so the two never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    provider: str
    description: str
    context_window: int
    max_output_tokens: int
    tier: str


MODELS: tuple[ModelInfo, ...] = (
    ModelInfo(
        id="gpt-4.1-mini",
        label="GPT-4.1 mini",
        provider="openai",
        description="Fast and inexpensive. A good default for support answers.",
        context_window=1_047_576,
        max_output_tokens=4096,
        tier="standard",
    ),
    ModelInfo(
        id="gpt-4.1-nano",
        label="GPT-4.1 nano",
        provider="openai",
        description="Lowest latency and cost, for short factual answers.",
        context_window=1_047_576,
        max_output_tokens=2048,
        tier="standard",
    ),
    ModelInfo(
        id="gpt-4.1",
        label="GPT-4.1",
        provider="openai",
        description="Most capable. Better at nuanced, multi-step questions.",
        context_window=1_047_576,
        max_output_tokens=4096,
        tier="advanced",
    ),
    # Google Gemini through its OpenAI-compatible endpoint (LLM_BASE_URL=
    # https://generativelanguage.googleapis.com/v1beta/openai). Each id must also have an entry in
    # CHAT_MODEL_PRICES, otherwise conversations refuse to start for that model.
    ModelInfo(
        id="gemini-3.5-flash",
        label="Gemini 3.5 Flash",
        provider="google",
        description="Fast with strong answers. Good default on Gemini.",
        context_window=1_048_576,
        max_output_tokens=8192,
        tier="standard",
    ),
    ModelInfo(
        id="gemini-3.5-flash-lite",
        label="Gemini 3.5 Flash-Lite",
        provider="google",
        description="Lowest latency and cost, for short factual answers.",
        context_window=1_048_576,
        max_output_tokens=4096,
        tier="standard",
    ),
)

DEFAULT_MODEL = "gpt-4.1-mini"
MODELS_BY_ID: dict[str, ModelInfo] = {model.id: model for model in MODELS}

#: BCP-47 tags a chatbot can be pinned to (``language_mode = "fixed"``).
LANGUAGES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "sv": "Swedish",
    "pl": "Polish",
    "tr": "Turkish",
    "ar": "Arabic",
    "hi": "Hindi",
    "si": "Sinhala",
    "ta": "Tamil",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Simplified)",
}

TONES: tuple[str, ...] = ("professional", "friendly", "concise", "custom")
RESPONSE_LENGTHS: tuple[str, ...] = ("concise", "balanced", "detailed")
STATUSES: tuple[str, ...] = ("draft", "active", "paused", "archived")

MIN_OUTPUT_TOKENS = 64
