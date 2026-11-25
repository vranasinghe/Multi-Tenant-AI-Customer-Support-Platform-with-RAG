"""Authorization matrix guard: no route may ship without an explicit access decision
(docs/SECURITY.md §4.2: "an automated test asserts that every router route has a permission
dependency")."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant

from app.api.deps import PERMISSION_ATTR, get_auth, get_tenant_context
from app.services.tenancy.policy import ALL_PERMISSIONS
from tests.support.routes import iter_api_routes

# Deliberately unauthenticated routes. Adding a route here is a reviewed security decision.
PUBLIC_ROUTES = {
    ("POST", "/api/v1/auth/signup"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/forgot-password"),
    ("POST", "/api/v1/auth/reset-password"),
    ("GET", "/api/v1/invitations/lookup"),
}


def _calls(dependant: Dependant) -> list[object]:
    found: list[object] = []
    if dependant.call is not None:
        found.append(dependant.call)
    for sub in dependant.dependencies:
        found.extend(_calls(sub))
    return found


def test_every_org_scoped_route_declares_exactly_one_known_permission(app: FastAPI) -> None:
    problems: list[str] = []
    routes = [r for r in iter_api_routes(app) if "/{org_id}" in r.path]
    assert len(routes) >= 10, f"route discovery broke: only {len(routes)} org-scoped routes"
    for route in routes:
        calls = _calls(route.dependant)
        permissions = [getattr(c, PERMISSION_ATTR) for c in calls if hasattr(c, PERMISSION_ATTR)]
        label = f"{route.sendable_methods} {route.path}"
        if len(permissions) != 1:
            problems.append(f"{label}: {len(permissions)} permission dependencies")
        elif permissions[0] not in ALL_PERMISSIONS:
            problems.append(f"{label}: unknown permission {permissions[0]!r}")
        if get_tenant_context not in calls:
            problems.append(f"{label}: no tenant context resolution")

    assert problems == []


def test_every_other_route_is_explicitly_public_or_requires_a_session(app: FastAPI) -> None:
    undeclared: list[str] = []
    routes = [r for r in iter_api_routes(app) if "/{org_id}" not in r.path]
    assert len(routes) >= 15, f"route discovery broke: only {len(routes)} other routes"
    for route in routes:
        needs_session = get_auth in _calls(route.dependant)
        for method in route.sendable_methods:
            public = (method, route.path) in PUBLIC_ROUTES
            if needs_session == public:
                undeclared.append(f"{method} {route.path}: session={needs_session} public={public}")

    assert undeclared == []
