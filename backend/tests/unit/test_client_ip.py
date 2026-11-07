"""Trusted-proxy client IP extraction: a table of connection peers and forwarding headers.

The Visitor's address is the right-most address in the chain (the connection's peer, then
``X-Forwarded-For`` read right to left) that isn't one of the configured trusted proxies.
CloudFront appends the viewer's address to ``X-Forwarded-For`` and the ALB appends CloudFront's,
so with both trusted the viewer's address is found; anything a client wrote further left is
never believed.
"""

from ipaddress import ip_network

import pytest

from app.embed.client_ip import client_ip, trusted_networks

# The deployment's proxies: the VPC (the ALB) and one CloudFront range.
TRUSTED = trusted_networks(["10.0.0.0/16", "130.176.0.0/17", "2001:db8::/32"])


@pytest.mark.parametrize(
    ("peer", "forwarded_for", "expected"),
    [
        # No proxy: the peer is the Visitor, whatever it claims.
        ("203.0.113.5", [], "203.0.113.5"),
        ("203.0.113.5", ["198.51.100.1"], "203.0.113.5"),
        ("203.0.113.5", ["10.0.0.9"], "203.0.113.5"),
        # Through the ALB alone.
        ("10.0.1.5", ["198.51.100.1"], "198.51.100.1"),
        # Through CloudFront then the ALB.
        ("10.0.1.5", ["198.51.100.1, 130.176.4.20"], "198.51.100.1"),
        # A client's own X-Forwarded-For is kept on the left by each proxy, and ignored.
        ("10.0.1.5", ["6.6.6.6, 198.51.100.1, 130.176.4.20"], "198.51.100.1"),
        ("10.0.1.5", ["10.0.0.1, 198.51.100.1"], "198.51.100.1"),
        # Several header lines are one list, in order.
        ("10.0.1.5", ["6.6.6.6", "198.51.100.1, 130.176.4.20"], "198.51.100.1"),
        # Spaces and empty entries are skipped.
        ("10.0.1.5", [" 198.51.100.1 ,, "], "198.51.100.1"),
        # A trusted peer that forwards nothing: the peer is all there is.
        ("10.0.1.5", [], "10.0.1.5"),
        ("10.0.1.5", [""], "10.0.1.5"),
        # Every address trusted: the left-most is the furthest known.
        ("10.0.1.5", ["10.0.3.3, 130.176.4.20"], "10.0.3.3"),
        # Garbage where an address should be stops the walk at the last address believed.
        ("10.0.1.5", ["198.51.100.1, not-an-ip"], "10.0.1.5"),
        ("10.0.1.5", ["198.51.100.1:5000"], "10.0.1.5"),
        # IPv6, written in any form, comes out in its short form.
        ("2001:db8::1", ["2001:0db8:0000:0000:0000:0000:0000:00ff, 2001:db8::2"], "2001:db8::ff"),
        ("2001:db8::1", ["2a00:1450::1"], "2a00:1450::1"),
        ("2a00:1450::1", ["198.51.100.1"], "2a00:1450::1"),
        # IPv4-mapped IPv6 from a dual-stack socket is the IPv4 address.
        ("::ffff:10.0.1.5", ["198.51.100.1"], "198.51.100.1"),
        ("::ffff:203.0.113.5", [], "203.0.113.5"),
        # No peer at all (not a real socket).
        (None, ["198.51.100.1"], "unknown"),
        ("not-an-ip", ["198.51.100.1"], "not-an-ip"),
    ],
)
def test_the_client_ip_is_the_first_untrusted_address_from_the_right(
    peer: str | None, forwarded_for: list[str], expected: str
) -> None:
    assert client_ip(peer, forwarded_for, TRUSTED) == expected


def test_with_no_trusted_proxies_the_peer_is_always_the_visitor() -> None:
    assert client_ip("10.0.1.5", ["198.51.100.1"], []) == "10.0.1.5"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ([], []),
        (["10.0.0.0/16"], [ip_network("10.0.0.0/16")]),
        (["10.0.0.7"], [ip_network("10.0.0.7/32")]),
        (["2001:db8::1"], [ip_network("2001:db8::1/128")]),
        ([" 10.0.0.0/8 ", ""], [ip_network("10.0.0.0/8")]),
    ],
)
def test_trusted_proxies_are_networks_or_single_addresses(
    configured: list[str], expected: list[object]
) -> None:
    assert trusted_networks(configured) == expected


def test_a_trusted_proxy_that_is_not_an_address_is_refused() -> None:
    with pytest.raises(ValueError, match=r"10\.0\.0\.0/33"):
        trusted_networks(["10.0.0.0/33"])
