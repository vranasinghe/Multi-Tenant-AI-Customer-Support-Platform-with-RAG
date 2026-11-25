"""Transactional email content. Plain text, links only to the web app (never to the API)."""

from __future__ import annotations

from app.integrations.email import EmailMessage

PRODUCT = "Support Platform"


def verify_email(*, to: str, name: str, web_base_url: str, token: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject=f"Verify your email for {PRODUCT}",
        text=(
            f"Hi {name},\n\nConfirm your email address to finish setting up your account:\n\n"
            f"{web_base_url}/verify-email?token={token}\n\n"
            "The link expires in 48 hours. If you didn't create an account, ignore this email.\n"
        ),
    )


def account_exists(*, to: str, name: str, web_base_url: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject=f"Someone tried to sign up with your email on {PRODUCT}",
        text=(
            f"Hi {name},\n\nSomeone tried to create an account with your email address, which "
            "already has one. If it was you, sign in or reset your password:\n\n"
            f"{web_base_url}/login\n\nIf it wasn't you, no action is needed.\n"
        ),
    )


def reset_password(*, to: str, name: str, web_base_url: str, token: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject=f"Reset your {PRODUCT} password",
        text=(
            f"Hi {name},\n\nUse this link to choose a new password:\n\n"
            f"{web_base_url}/reset-password?token={token}\n\n"
            "The link expires in 30 minutes and works once. If you didn't ask for it, "
            "ignore this email; your password stays unchanged.\n"
        ),
    )


def password_changed(*, to: str, name: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject=f"Your {PRODUCT} password was changed",
        text=(
            f"Hi {name},\n\nYour password was just changed and all other sessions were signed "
            "out. If this wasn't you, reset your password immediately.\n"
        ),
    )


def account_locked(*, to: str, name: str, minutes: int) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject=f"Too many failed sign-in attempts on {PRODUCT}",
        text=(
            f"Hi {name},\n\nWe temporarily blocked sign-ins to your account for {minutes} "
            "minutes after repeated failed attempts. If this wasn't you, reset your password.\n"
        ),
    )


def invitation(
    *, to: str, org_name: str, inviter_name: str, role: str, web_base_url: str, token: str
) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject=f"{inviter_name} invited you to {org_name} on {PRODUCT}",
        text=(
            f"{inviter_name} invited you to join {org_name} as {role}.\n\n"
            f"Accept the invitation:\n\n{web_base_url}/invite?token={token}\n\n"
            "Sign in or create an account with this email address. The link expires in 7 days.\n"
        ),
    )
