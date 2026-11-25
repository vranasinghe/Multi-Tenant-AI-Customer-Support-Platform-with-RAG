"""The signed-in user: profile, password, sessions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.cookies import set_session_cookie
from app.api.deps import AuthDep, DbDep, MailDep, MetaDep, ServicesDep
from app.api.serializers import org_role_out, user_out
from app.core.errors import not_found
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginResponse,
    SessionList,
    SessionOut,
    UpdateMeRequest,
    UserOut,
)
from app.services.identity import auth as auth_service
from app.services.identity import sessions
from app.services.tenancy.orgs import list_user_orgs

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def get_me(auth: AuthDep, db: DbDep) -> LoginResponse:
    orgs = await list_user_orgs(db, auth.user.id)
    return LoginResponse(
        user=user_out(auth.user), orgs=[org_role_out(org, role) for org, role in orgs]
    )


@router.patch("")
async def update_me(body: UpdateMeRequest, auth: AuthDep, db: DbDep) -> UserOut:
    if body.name is not None:
        auth.user.name = body.name
    if body.locale is not None:
        auth.user.locale = body.locale
    await db.commit()
    return user_out(auth.user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    auth: AuthDep,
    db: DbDep,
    svc: ServicesDep,
    mail: MailDep,
    meta: MetaDep,
) -> None:
    token = await auth_service.change_password(
        db,
        svc,
        mail,
        user=auth.user,
        current_session_id=auth.session_id,
        current_password=body.current_password,
        new_password=body.new_password,
        meta=meta,
    )
    set_session_cookie(response, token, svc.settings)


@router.get("/sessions")
async def list_my_sessions(auth: AuthDep, db: DbDep) -> SessionList:
    rows = await sessions.list_sessions(db, auth.user.id)
    return SessionList(
        data=[
            SessionOut(
                id=row.id,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                expires_at=row.expires_at,
                user_agent=row.user_agent,
                current=row.id == auth.session_id,
            )
            for row in rows
        ]
    )


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_other_sessions(auth: AuthDep, db: DbDep) -> None:
    """Sign out everywhere except this device."""
    await sessions.revoke_user_sessions(db, auth.user.id, except_session_id=auth.session_id)
    await db.commit()


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: uuid.UUID, auth: AuthDep, db: DbDep) -> None:
    if not await sessions.revoke_one(db, user_id=auth.user.id, session_id=session_id):
        raise not_found()
    await db.commit()
