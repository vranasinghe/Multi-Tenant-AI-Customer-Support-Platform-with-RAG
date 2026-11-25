"""Request/response models for organizations, members, invitations and audit logs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import EmailStr, Field, StringConstraints

from app.schemas.auth import Name, OutModel, StrictModel

AssignableRole = Literal["admin", "agent", "viewer"]  # never "owner": ownership is transferred


class OrgSettings(StrictModel):
    conversation_retention_days: Annotated[int, Field(ge=1, le=730)] | None = None
    default_language: Annotated[str, StringConstraints(min_length=2, max_length=10)] | None = None


class CreateOrgRequest(StrictModel):
    name: Name


class UpdateOrgRequest(StrictModel):
    name: Name | None = None
    settings: OrgSettings | None = None


class OrgOut(OutModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    role: str
    permissions: list[str]
    settings: dict[str, Any]
    created_at: datetime


class OrgList(OutModel):
    data: list[OrgOut]


class TransferOwnershipRequest(StrictModel):
    new_owner_user_id: uuid.UUID
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class MemberUser(OutModel):
    id: uuid.UUID
    name: str
    email: str
    email_verified: bool


class MemberOut(OutModel):
    id: uuid.UUID
    user: MemberUser
    role: str
    created_at: datetime


class MemberList(OutModel):
    data: list[MemberOut]


class UpdateMemberRequest(StrictModel):
    role: AssignableRole


class InviteRequest(StrictModel):
    email: EmailStr
    role: AssignableRole


class InvitationOut(OutModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class InvitationList(OutModel):
    data: list[InvitationOut]


class InvitationPreviewOut(OutModel):
    org_name: str
    inviter_name: str | None
    role: str
    email_hint: str


class AcceptInvitationRequest(StrictModel):
    token: Annotated[str, StringConstraints(min_length=20, max_length=128)]


class AuditActor(OutModel):
    id: uuid.UUID
    name: str


class AuditLogOut(OutModel):
    id: uuid.UUID
    action: str
    actor: AuditActor | None
    actor_type: str
    target_type: str | None
    target_id: uuid.UUID | None
    metadata: dict[str, Any]
    request_id: str | None
    created_at: datetime


class AuditLogList(OutModel):
    data: list[AuditLogOut]
    next_cursor: str | None
    has_more: bool
