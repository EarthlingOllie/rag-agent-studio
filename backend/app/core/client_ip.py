"""A request's client IP address, for per-IP limits (widget rate limits, sign-in throttling),
believing forwarding headers only from the configured trusted proxies (``TRUSTED_PROXIES``).

This is the one place forwarding headers are believed: the API server runs uvicorn with its own
proxy-header handling off (``app/serve.py``), so the connection peer reaching the app is the real
one and a client can't choose where the walk starts.

In AWS a Visitor's request reaches the API through CloudFront and then the ALB. CloudFront
appends the viewer's address to ``X-Forwarded-For`` and the ALB appends CloudFront's, so the
API's connection peer is the ALB. Walking the chain from the right (the peer, then each
``X-Forwarded-For`` entry right to left), every address that is a trusted proxy was written by a
proxy we believe; the first one that isn't is the Visitor. Anything further left was written by
the client and is ignored, so a client can't pose as someone else to dodge a limit. With no
trusted proxies (``docker compose``, tests) the peer is the client.
"""

from collections.abc import Iterable, Sequence
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network

from starlette.requests import Request

Network = IPv4Network | IPv6Network

UNKNOWN = "unknown"


def trusted_networks(configured: Iterable[str]) -> list[Network]:
    """The trusted proxies as networks: each entry is a network (``10.0.0.0/16``) or a single
    address; blank entries are skipped. Raises ``ValueError`` naming an entry that is neither."""
    networks: list[Network] = []
    for entry in configured:
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ip_network(entry, strict=False))
        except ValueError:
            raise ValueError(f"{entry!r} isn't an IP address or network.") from None
    return networks


def _address(text: str) -> IPv4Address | IPv6Address | None:
    try:
        found = ip_address(text.strip())
    except ValueError:
        return None
    if isinstance(found, IPv6Address) and found.ipv4_mapped is not None:
        return found.ipv4_mapped
    return found


def client_ip(peer: str | None, forwarded_for: Sequence[str], trusted: Sequence[Network]) -> str:
    """The Visitor's address: the right-most address in the chain that isn't a trusted proxy.

    ``peer`` is the connection's remote address and ``forwarded_for`` the ``X-Forwarded-For``
    header lines in the order received. If every address is trusted the left-most is the
    furthest known. An entry that isn't an address stops the walk at the last address believed.
    """
    if peer is None:
        return UNKNOWN
    current = _address(peer)
    if current is None:
        return peer
    entries = [e for line in forwarded_for for e in line.split(",") if e.strip()]
    while any(current in network for network in trusted) and entries:
        previous = _address(entries.pop())
        if previous is None:
            break
        current = previous
    return str(current)


def request_ip(request: Request) -> str:
    """The client's address for this request, through the app's trusted proxies."""
    peer = None if request.client is None else request.client.host
    trusted: Sequence[Network] = request.app.state.settings.trusted_proxies
    return client_ip(peer, request.headers.getlist("x-forwarded-for"), trusted)
