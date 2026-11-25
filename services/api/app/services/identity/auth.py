"""Authentication use cases: signup, login, email verification, password recovery and change.

Anti-enumeration (docs/SECURITY.md §3): signup for an existing email, login failures and
forgot-password return the same responses regardless of whether the account exists, and the
Argon2 work is performed in every branch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApiError, invalid_token, validation_error
from app.core.logging import get_logger
from app.core.rate_limit import Limit
from app.core.security import PasswordPolicyError, validate_password_policy
from app.models.identity import User, utcnow
from app.services import notifications
from app.services.identity import sessions, tokens
from app.services.tenancy.orgs import create_organization

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.request_meta import RequestMeta
    from app.models.tenancy import Organization
    from app.services.container import AppServices, MailQueue

log = get_logger(__name__)


def invalid_credentials() -> ApiError:
    return ApiError(
        401, "invalid_credentials", "Invalid email or password", detail="Check your details."
    )


def _check_policy(password: str, email: str, field: str = "password") -> None:
    try:
        validate_password_policy(password, email=email)
    except PasswordPolicyError as exc:
        raise validation_error(field, str(exc), "weak_password") from exc


async def _find_user(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


@dataclass(frozen=True)
class SignupResult:
    user: User
    org: Organization | None  # None => decoy response for an already-registered email
    session_token: str | None
    decoy_org_id: uuid.UUID | None = None
    decoy_org_name: str | None = None


async def signup(
    db: AsyncSession,
    svc: AppServices,
    mail: MailQueue,
    *,
    email: str,
    password: str,
    name: str,
    org_name: str,
    meta: RequestMeta,
) -> SignupResult:
    settings = svc.settings
    await svc.limiter.check(
        meta.ip or "unknown",
        Limit("signup_ip", settings.rate_limit_signup_per_hour, 3600),
    )
    _check_policy(password, email)
    # Hash before looking the email up so both branches burn the same CPU time.
    password_hash = await svc.passwords.hash(password)

    existing = await _find_user(db, email)
    if existing is not None:
        mail.send(
            notifications.account_exists(
                to=existing.email, name=existing.name, web_base_url=settings.web_base_url
            )
        )
        log.info("auth.signup_existing_email", user_id=str(existing.id))
        return SignupResult(
            user=User(id=uuid.uuid4(), email=email, name=name, locale="en"),
            org=None,
            session_token=None,
            decoy_org_id=uuid.uuid4(),
            decoy_org_name=org_name,
        )

    user = User(email=email, name=name, password_hash=password_hash)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # Lost a race with a concurrent signup for the same email: behave as "existing".
        await db.rollback()
        return SignupResult(
            user=User(id=uuid.uuid4(), email=email, name=name, locale="en"),
            org=None,
            session_token=None,
            decoy_org_id=uuid.uuid4(),
            decoy_org_name=org_name,
        )
    org, _ = await create_organization(db, creator=user, name=org_name, meta=meta)
    verify_token = await tokens.issue_email_token(
        db,
        user_id=user.id,
        purpose="verify_email",
        ttl=timedelta(hours=settings.verify_token_ttl_hours),
    )
    session_token = await sessions.create_session(db, user_id=user.id, settings=settings, meta=meta)
    await db.commit()
    mail.send(
        notifications.verify_email(
            to=user.email, name=user.name, web_base_url=settings.web_base_url, token=verify_token
        )
    )
    log.info("auth.signup", user_id=str(user.id))
    return SignupResult(user=user, org=org, session_token=session_token)


@dataclass(frozen=True)
class LoginResult:
    user: User
    session_token: str


async def login(
    db: AsyncSession,
    svc: AppServices,
    mail: MailQueue,
    *,
    email: str,
    password: str,
    meta: RequestMeta,
    presented_session_token: str | None,
) -> LoginResult:
    s = svc.settings
    await svc.limiter.check(
        meta.ip or "unknown",
        Limit("login_ip_min", s.rate_limit_login_ip_per_minute, 60),
        Limit("login_ip_hour", s.rate_limit_login_ip_per_hour, 3600),
    )
    await svc.limiter.check(
        email,
        Limit("login_email_min", s.rate_limit_login_email_per_minute, 60),
        Limit("login_email_hour", s.rate_limit_login_email_per_hour, 3600),
    )
    await svc.login_guard.assert_unlocked(email)

    user = await _find_user(db, email)
    active = user if user is not None and user.status == "active" else None
    verified = await svc.passwords.verify(active.password_hash if active else None, password)
    if not verified or active is None:
        locked = await svc.login_guard.record_failure(email)
        log.warning(
            "security.login_failed",
            user_id=str(user.id) if user else None,
            locked=locked,
            ip_prefix=meta.ip_prefix,
        )
        if locked and user is not None:
            mail.send(
                notifications.account_locked(
                    to=user.email, name=user.name, minutes=s.login_lockout_minutes
                )
            )
        raise invalid_credentials()

    await svc.login_guard.clear(email)
    if active.password_hash and svc.passwords.needs_rehash(active.password_hash):
        active.password_hash = await svc.passwords.hash(password)
    active.last_login_at = utcnow()
    if presented_session_token:  # session-fixation defence: never reuse a pre-login session
        await sessions.revoke_session_by_token(db, presented_session_token)
    token = await sessions.create_session(db, user_id=active.id, settings=s, meta=meta)
    await db.commit()
    log.info("auth.login", user_id=str(active.id))
    return LoginResult(user=active, session_token=token)


async def verify_email(db: AsyncSession, *, token: str) -> None:
    user_id = await tokens.consume_email_token(db, token=token, purpose="verify_email")
    if user_id is None:
        raise invalid_token()
    await db.execute(
        update(User)
        .where(User.id == user_id, User.email_verified_at.is_(None))
        .values(email_verified_at=func.now())
    )
    await db.commit()
    log.info("auth.email_verified", user_id=str(user_id))


async def resend_verification(
    db: AsyncSession, svc: AppServices, mail: MailQueue, *, user: User
) -> None:
    s = svc.settings
    await svc.limiter.check(
        str(user.id), Limit("verify_resend", s.rate_limit_email_action_per_email_hour, 3600)
    )
    if user.email_verified_at is not None:
        return
    token = await tokens.issue_email_token(
        db,
        user_id=user.id,
        purpose="verify_email",
        ttl=timedelta(hours=s.verify_token_ttl_hours),
    )
    await db.commit()
    mail.send(
        notifications.verify_email(
            to=user.email, name=user.name, web_base_url=s.web_base_url, token=token
        )
    )


async def forgot_password(
    db: AsyncSession, svc: AppServices, mail: MailQueue, *, email: str, meta: RequestMeta
) -> None:
    s = svc.settings
    await svc.limiter.check(
        email, Limit("forgot_email", s.rate_limit_email_action_per_email_hour, 3600)
    )
    await svc.limiter.check(
        meta.ip or "unknown", Limit("forgot_ip", s.rate_limit_email_action_per_ip_hour, 3600)
    )
    user = await _find_user(db, email)
    if user is None or user.status != "active":
        return  # same response, no email, no token
    token = await tokens.issue_email_token(
        db,
        user_id=user.id,
        purpose="reset_password",
        ttl=timedelta(minutes=s.reset_token_ttl_minutes),
    )
    await db.commit()
    mail.send(
        notifications.reset_password(
            to=user.email, name=user.name, web_base_url=s.web_base_url, token=token
        )
    )
    log.info("security.password_reset_requested", user_id=str(user.id))


async def reset_password(
    db: AsyncSession, svc: AppServices, mail: MailQueue, *, token: str, new_password: str
) -> None:
    user_id = await tokens.consume_email_token(db, token=token, purpose="reset_password")
    if user_id is None:
        raise invalid_token()
    user = await db.get(User, user_id)
    if user is None or user.status != "active":
        raise invalid_token()
    # Policy failures raise before commit, so the spent token is rolled back and stays usable.
    _check_policy(new_password, user.email)
    user.password_hash = await svc.passwords.hash(new_password)
    if user.email_verified_at is None:  # the emailed link proves control of the address
        user.email_verified_at = utcnow()
    await sessions.revoke_user_sessions(db, user.id)
    await db.commit()
    await svc.login_guard.clear(user.email)
    mail.send(notifications.password_changed(to=user.email, name=user.name))
    log.warning("security.password_reset_completed", user_id=str(user.id))


async def change_password(
    db: AsyncSession,
    svc: AppServices,
    mail: MailQueue,
    *,
    user: User,
    current_session_id: uuid.UUID,
    current_password: str,
    new_password: str,
    meta: RequestMeta,
) -> str:
    """Returns a fresh session token; every other session is revoked (and the old token rotated)."""
    await svc.limiter.check(
        str(user.id), Limit("change_password", svc.settings.rate_limit_login_email_per_minute, 60)
    )
    if not await svc.passwords.verify(user.password_hash, current_password):
        raise ApiError(
            400,
            "invalid_credentials",
            "Current password is incorrect",
            detail="Check it and retry.",
        )
    _check_policy(new_password, user.email, "new_password")
    user.password_hash = await svc.passwords.hash(new_password)
    await sessions.revoke_user_sessions(db, user.id)
    token = await sessions.create_session(db, user_id=user.id, settings=svc.settings, meta=meta)
    await db.commit()
    mail.send(notifications.password_changed(to=user.email, name=user.name))
    log.warning("security.password_changed", user_id=str(user.id), kept=str(current_session_id))
    return token
