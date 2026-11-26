"""Ingestion error taxonomy.

``IngestionError`` is permanent: retrying the same input cannot help, so the document is marked
failed with a stable ``code`` and a user-safe message. ``TransientIngestionError`` may succeed
later (provider rate limit, storage hiccup) and is retried with exponential backoff.

Messages are written for end users: they never include document content, stack traces, internal
hostnames or storage keys.
"""

from __future__ import annotations

USER_MESSAGES: dict[str, str] = {
    "unsupported_type": "This file type isn't supported. Upload a PDF, DOCX or TXT file.",
    "corrupt": "The file is damaged or couldn't be read.",
    "encrypted": "The file is password-protected. Remove the password and upload it again.",
    "no_text": "No readable text was found. Scanned documents need OCR first.",
    "too_large": "The file is too large to process.",
    "too_many_pages": "The document has more pages than are allowed.",
    "duplicate_content": "A document with the same content already exists for this chatbot.",
    "embedding_failed": "Indexing failed: the embedding service was unavailable. Retry later.",
    "storage_error": "The stored file couldn't be read. Retry, or upload it again.",
    "blocked_destination": "This address isn't allowed. Only public websites can be crawled.",
    "fetch_failed": "The page couldn't be fetched.",
    "robots_disallowed": "The site's robots.txt doesn't allow crawling this page.",
    "low_content": "The page has too little text to be useful.",
    "parse_timeout": "The file took too long to read. Split or simplify it, then retry.",
    "parse_resource_limit": (
        "The file needs more resources to read than are allowed. Split or simplify it, then retry."
    ),
    "parse_invalid_output": "The file couldn't be read. Retry, or contact support.",
    "task_timeout": "Processing took too long. Retry later, or split the document.",
    "internal_error": "Something went wrong while processing. Retry, or contact support.",
}


class IngestionError(Exception):
    """A permanent failure with a stable code."""

    retryable = False

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail

    @property
    def user_message(self) -> str:
        return USER_MESSAGES.get(self.code, USER_MESSAGES["internal_error"])


class TransientIngestionError(IngestionError):
    retryable = True
