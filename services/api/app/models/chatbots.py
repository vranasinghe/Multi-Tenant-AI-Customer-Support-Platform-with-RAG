"""Chatbot configuration (tenant table, RLS-protected; see migration 0003)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_id
from app.models import Base
from app.models.identity import utcnow


class Chatbot(Base):
    __tablename__ = "chatbots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="draft")
    public_key: Mapped[str] = mapped_column(Text, unique=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(Text, default="professional")
    response_length: Mapped[str] = mapped_column(Text, default="balanced")
    welcome_message: Mapped[str] = mapped_column(Text, default="")
    fallback_message: Mapped[str] = mapped_column(Text, default="")
    language_mode: Mapped[str] = mapped_column(Text, default="auto")
    language: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    temperature: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.20"))
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=600)
    strict_grounding: Mapped[bool] = mapped_column(Boolean, default=True)
    show_sources: Mapped[bool] = mapped_column(Boolean, default=True)
    retrieval_top_k: Mapped[int] = mapped_column(Integer, default=6)
    widget_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    widget_retention_days: Mapped[int] = mapped_column(Integer, default=7)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
