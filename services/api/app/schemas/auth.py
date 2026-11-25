"""Request/response models for auth and account endpoints.

Every request model forbids unknown fields (mass-assignment defence): a client can never smuggle
``org_id``, ``role``, ``status`` or similar through a body.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
# Cap login/reset password length so oversized input can't be used to burn Argon2 CPU.
SecretText = Annotated[str, StringConstraints(min_length=1, max_length=256)]
TokenText = Annotated[str, StringConstraints(min_length=20, max_length=128)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SignupRequest(StrictModel):
    email: EmailStr
    password: SecretText
    name: Name
    org_name: Name


class LoginRequest(StrictModel):
    email: EmailStr
    password: SecretText


class TokenRequest(StrictModel):
    token: TokenText


class ForgotPasswordRequest(StrictModel):
    email: EmailStr


class ResetPasswordRequest(StrictModel):
    token: TokenText
    password: SecretText


class ChangePasswordRequest(StrictModel):
    current_password: SecretText
    new_password: SecretText


class UpdateMeRequest(StrictModel):
    name: Name | None = None
    locale: Annotated[str, StringConstraints(min_length=2, max_length=10)] | None = None


class UserOut(OutModel):
    id: uuid.UUID
    email: str
    name: str
    email_verified: bool
    locale: str = "en"


class OrgRoleOut(OutModel):
    id: uuid.UUID
    name: str
    role: str


class SignupResponse(OutModel):
    user: UserOut
    org: OrgRoleOut


class LoginResponse(OutModel):
    user: UserOut
    orgs: list[OrgRoleOut]


class StatusResponse(OutModel):
    status: str


class SessionOut(OutModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    current: bool


class SessionList(OutModel):
    data: list[SessionOut]
