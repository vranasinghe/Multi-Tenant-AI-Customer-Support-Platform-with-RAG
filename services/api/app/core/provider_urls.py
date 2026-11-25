"""Operator-only AI endpoint policy. Never include supplied URLs in exceptions."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


def provider_url(value: str, *, allow_loopback_http: bool = False) -> str:
    """Canonical ASCII HTTPS base URL; explicit development HTTP is literal loopback only.

    Deliberately reject encoded/dot-segment paths and noncanonical authorities rather than let
    URL parsers, proxies and providers disagree. This is not a public-IP/SSRF policy: endpoints
    are operator configuration, never tenant input. HTTPS private services remain supported.
    """
    message = "must be an HTTPS provider URL with a valid host/port and safe base path"
    if (
        not value
        or len(value) > 2048
        or not value.isascii()
        or any(ord(c) <= 32 or ord(c) == 127 for c in value)
        or any(c in value for c in "\\%?#")
    ):
        raise ValueError(message)
    try:
        parts = urlsplit(value)
        authority = parts.netloc
        host = parts.hostname
        address: ipaddress.IPv4Address | ipaddress.IPv6Address | None
        if parts.scheme not in {"http", "https"} or not host or "@" in authority:
            raise ValueError(message)
        if authority.startswith("["):
            closing = authority.index("]")
            address = ipaddress.IPv6Address(host)
            canonical_host = f"[{address.compressed}]"
            tail = authority[closing + 1 :]
        else:
            if authority.count(":") > 1:
                raise ValueError(message)
            tail = ":" + authority.split(":", 1)[1] if ":" in authority else ""
            try:
                address = ipaddress.IPv4Address(host)
                canonical_host = str(address)
            except ValueError:
                if (
                    len(host) > 253
                    or not re.fullmatch(r"[a-z0-9.-]+", host)
                    or not any(c.isalpha() for c in host)
                    or not any(c.isalpha() for c in host.split(".")[-1])
                    or any(
                        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                        for label in host.split(".")
                    )
                    or re.fullmatch(r"(?:0x[0-9a-f]+|[0-9.]+)", host)
                ):
                    raise ValueError(message) from None
                address = None
                canonical_host = host
        if tail and (
            not re.fullmatch(r":[1-9][0-9]{0,4}", tail)
            or parts.port is None
            or not 1 <= parts.port <= 65535
        ):
            raise ValueError(message)
        if parts.path and (
            not re.fullmatch(r"/[A-Za-z0-9/_.~-]*", parts.path)
            or "//" in parts.path
            or any(segment in {".", ".."} for segment in parts.path.split("/"))
        ):
            raise ValueError(message)
        if parts.scheme != "https" and not (
            allow_loopback_http
            and (
                host == "localhost"
                or (isinstance(address, ipaddress.IPv4Address) and address.is_loopback)
                or address == ipaddress.IPv6Address("::1")
            )
        ):
            raise ValueError(message)
        return f"{parts.scheme}://{canonical_host}{tail}{parts.path.rstrip('/')}"
    except (ValueError, IndexError):
        raise ValueError(message) from None
