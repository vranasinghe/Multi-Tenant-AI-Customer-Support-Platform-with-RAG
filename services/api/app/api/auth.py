"""Public auth endpoints: signup, login, logout, email verification, password recovery."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.cookies import SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.api.deps import AuthDep, DbDep, MailDep, MetaDep, ServicesDep
from app.api.serializers import org_role_out, user_out
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    OrgRoleOut,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    StatusResponse,
    TokenRequest,
)
from app.services.identity import auth as auth_service
from app.services.identity import sessions
from app.services.tenancy.orgs import list_user_orgs

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest,
    response: Response,
    db: DbDep,
    svc: ServicesDep,
    mail: MailDep,
    meta: MetaDep,
) -> SignupResponse:
    """Create a user, their first organization (as owner) and a session.

    An already-registered email gets the same response shape without a session, plus a
    notification email to the existing account, so signup cannot be used to probe for accounts.
    """
    result = await auth_service.signup(
        db,
        svc,
        mail,
        email=str(body.email),
        password=body.password,
        name=body.name,
        org_name=body.org_name,
        meta=meta,
    )
    if result.session_token and result.org:
        set_session_cookie(response, result.session_token, svc.settings)
        org = org_role_out(result.org, "owner")
    else:
        org = OrgRoleOut(id=result.decoy_org_id or result.user.id, name=body.org_name, role="owner")
    return SignupResponse(user=user_out(result.user), org=org)


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbDep,
    svc: ServicesDep,
    mail: MailDep,
    meta: MetaDep,
) -> LoginResponse:
    result = await auth_service.login(
        db,
        svc,
        mail,
        email=str(body.email),
        password=body.password,
        meta=meta,
        presented_session_token=request.cookies.get(SESSION_COOKIE),
    )
    set_session_cookie(response, result.session_token, svc.settings)
    orgs = await list_user_orgs(db, result.user.id)
    return LoginResponse(
        user=user_out(result.user), orgs=[org_role_out(org, role) for org, role in orgs]
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, auth: AuthDep, db: DbDep) -> None:
    await sessions.revoke_session_by_token(db, auth.session_token)
    await db.commit()
    clear_session_cookie(response)


@router.post("/verify-email")
async def verify_email(body: TokenRequest, db: DbDep) -> StatusResponse:
    await auth_service.verify_email(db, token=body.token)
    return StatusResponse(status="verified")


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    auth: AuthDep, db: DbDep, svc: ServicesDep, mail: MailDep
) -> StatusResponse:
    await auth_service.resend_verification(db, svc, mail, user=auth.user)
    return StatusResponse(status="accepted")


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: ForgotPasswordRequest, db: DbDep, svc: ServicesDep, mail: MailDep, meta: MetaDep
) -> StatusResponse:
    """Always 202: the response never reveals whether the email has an account."""
    await auth_service.forgot_password(db, svc, mail, email=str(body.email), meta=meta)
    return StatusResponse(status="accepted")


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest, db: DbDep, svc: ServicesDep, mail: MailDep
) -> StatusResponse:
    await auth_service.reset_password(db, svc, mail, token=body.token, new_password=body.password)
    return StatusResponse(status="password_reset")
