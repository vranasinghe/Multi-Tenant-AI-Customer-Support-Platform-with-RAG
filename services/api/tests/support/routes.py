"""Route discovery that works with FastAPI's lazily included routers (``app.routes`` holds
``_IncludedRouter`` wrappers, not ``APIRoute`` objects)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute


@dataclass(frozen=True)
class RouteInfo:
    path: str
    methods: frozenset[str]
    dependant: Dependant
    path_params: tuple[str, ...]

    @property
    def sendable_methods(self) -> list[str]:
        return sorted(self.methods - {"HEAD", "OPTIONS"})


def iter_api_routes(app: FastAPI, *, prefix: str = "/api/v1/") -> Iterator[RouteInfo]:
    for route in app.routes:
        contexts: list[Any] = (
            list(route.effective_route_contexts())
            if hasattr(route, "effective_route_contexts")
            else [route]
        )
        for ctx in contexts:
            if not isinstance(getattr(ctx, "original_route", ctx), APIRoute):
                continue
            path = ctx.path
            if path.startswith(prefix) and ctx.dependant is not None:
                yield RouteInfo(
                    path=path,
                    methods=frozenset(ctx.methods),
                    dependant=ctx.dependant,
                    path_params=tuple(ctx.param_convertors),
                )


def fill_path(route: RouteInfo, **known: str) -> str:
    """Concrete URL (without the /api/v1 prefix) with unknown params set to random UUIDs."""
    import uuid

    path = route.path.removeprefix("/api/v1")
    for name in route.path_params:
        path = path.replace("{" + name + "}", known.get(name) or str(uuid.uuid4()))
    return path
