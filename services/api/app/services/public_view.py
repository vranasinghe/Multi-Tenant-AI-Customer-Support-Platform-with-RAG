"""What a website visitor may see of a stored conversation (WIDGET-PRIV-01).

Explicit allowlists: a field added to the internal message or citation shape stays private until
it is added here. Storage, accounting and the dashboard keep the full records.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from app.schemas.chatbots import WidgetSettings

#: Failure causes are operational detail; a visitor only needs to know the answer did not finish.
PUBLIC_ERROR_CODE = "answer_failed"


def _public_link(uri: str) -> str:
    """The source's address only if it is a plain https link; file names and ids stay private."""
    try:
        parts = urlsplit(uri)
        if parts.scheme == "https" and parts.hostname and not parts.username and not parts.password:
            return uri
    except ValueError:
        pass
    return ""


def public_citation(citation: dict[str, Any]) -> dict[str, Any]:
    """The citation number, its label and a public link. Not the document or chunk behind it."""
    return {
        "id": citation["id"],
        "title": citation["title"],
        "uri": _public_link(str(citation.get("uri") or "")),
    }


def public_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message["id"],
        "role": message["role"],
        "content": message["content"],
        "status": message["status"],
        "feedback": message.get("feedback"),
        "citations": [public_citation(c) for c in message["citations"]],
    }


def public_event(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """The public form of one server-sent event of a streamed answer."""
    if name == "meta":
        return {"message_id": payload["message_id"]}
    if name == "delta":
        return {"text": payload["text"]}
    if name == "error":
        return {"code": PUBLIC_ERROR_CODE, "message": payload["message"]}
    if name == "done":
        return public_message(payload)
    raise ValueError(f"no public form for event {name!r}")


def public_branding(settings: dict[str, Any]) -> dict[str, Any]:
    return {key: settings[key] for key in WidgetSettings.model_fields if key in settings}
