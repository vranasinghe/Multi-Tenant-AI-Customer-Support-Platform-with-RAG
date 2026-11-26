"""Which peers may speak for a client through `X-Forwarded-For` / `X-Forwarded-Proto`.

Operator-only configuration for Uvicorn's proxy-header middleware (AUD-04). This module only
validates the list; Uvicorn does the header handling. The syntax is deliberately narrower than
`ipaddress` accepts: Uvicorn silently treats anything it cannot parse as a literal host name.
"""

from __future__ import annotations

import ipaddress
import re

# Anything broader is effectively "trust the internet". IPv6 allows large provider allocations.
_MIN_PREFIX = {4: 8, 6: 16}
_ENTRY = re.compile(r"[0-9A-Fa-f:.]+(/[1-9][0-9]*)?")


def _canonical(entry: str, position: int) -> str:
    problem = f"FORWARDED_ALLOW_IPS entry {position}"
    if not _ENTRY.fullmatch(entry):
        raise ValueError(
            f"{problem} must be a literal IP address or CIDR network (no wildcard, /0, "
            "host name, port, brackets, zone or netmask)"
        )
    try:
        network = ipaddress.ip_network(entry)  # strict: host bits must be zero
    except ValueError:
        raise ValueError(
            f"{problem} is not a valid IP address or network (host bits must be zero)"
        ) from None
    address = network.network_address
    if address.is_unspecified:
        raise ValueError(f"{problem} is the unspecified address, which names no proxy")
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        raise ValueError(f"{problem} is IPv4-mapped; write the IPv4 address itself")
    if network.prefixlen < _MIN_PREFIX[network.version]:
        raise ValueError(f"{problem} is too broad to be a proxy network")
    return str(network) if "/" in entry else str(address)


def parse_trusted_proxies(value: object) -> list[str]:
    """Canonical entries from a comma-separated string or list; blank means trust no proxy."""
    if isinstance(value, str):
        if not value.strip():
            return []
        value = value.split(",")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("FORWARDED_ALLOW_IPS must be a comma-separated list")
    return [_canonical(item.strip(), position) for position, item in enumerate(value, 1)]
