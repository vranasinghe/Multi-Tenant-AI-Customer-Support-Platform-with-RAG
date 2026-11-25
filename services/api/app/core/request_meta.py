"""Coarse request metadata for sessions and audit rows (docs/SECURITY.md §13: no full IPs)."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request


def ip_prefix(address: str | None) -> str | None:
    """/24 for IPv4, /48 for IPv6; None when the address is missing or not an IP."""
    if not address:
        return None
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    length = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{length}", strict=False))


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    ip_prefix: str | None
    user_agent: str | None
    request_id: str | None

    @classmethod
    def from_request(cls, request: Request) -> RequestMeta:
        host = request.client.host if request.client else None
        agent = request.headers.get("user-agent")
        return cls(
            ip=host,
            ip_prefix=ip_prefix(host),
            user_agent=agent[:256] if agent else None,
            request_id=getattr(request.state, "request_id", None),
        )
