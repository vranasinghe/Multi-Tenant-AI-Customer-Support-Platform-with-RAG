"""Versioned dashboard API (`/api/v1`): auth, account, organizations, invitations, chatbots."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import auth, chatbots, conversations, invitations, knowledge, me, orgs
from app.api.widget_install import manage

router = APIRouter()
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(orgs.router)
router.include_router(invitations.router)
router.include_router(chatbots.router)
router.include_router(knowledge.router)
router.include_router(conversations.router)


router.include_router(manage)
