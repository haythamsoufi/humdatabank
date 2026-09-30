import ipaddress

import pytest

from app.utils.outbound_url import is_blocked_ip, parse_network_allowlist, validate_outbound_url


def _public(host, port=None):
    return (ipaddress.ip_address("93.184.216.34"),)


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "::1", "fe80::1", "0.0.0.0", "::ffff:127.0.0.1", "fc00::1"],
)
def test_blocked_ip_classes(ip):
    assert is_blocked_ip(ipaddress.ip_address(ip))


def test_public_ip_not_blocked():
    assert not is_blocked_ip(ipaddress.ip_address("93.184.216.34"))


def test_allowed_network_overrides_block():
    nets = parse_network_allowlist("10.0.0.0/8")
    assert not is_blocked_ip(ipaddress.ip_address("10.1.2.3"), nets)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.org/x",
        "http://example.org/x",
        "https://user:pw@example.org/x",
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/x",
        "https://8.8.8.8/x",
    ],
)
def test_rejected_urls(url):
    assert not validate_outbound_url(url, resolver=_public).ok


def test_public_https_host_accepted():
    res = validate_outbound_url("https://example.org/path", resolver=_public)
    assert res.ok and res.host == "example.org"


def test_dns_resolving_to_private_address_rejected():
    res = validate_outbound_url(
        "https://internal.example.org/", resolver=lambda h, p=None: (ipaddress.ip_address("10.0.0.7"),)
    )
    assert not res.ok


def test_allowlist_matches_exact_and_subdomain_only():
    kwargs = dict(allowed_hosts=["ifrc.org"], resolver=_public)
    assert validate_outbound_url("https://ifrc.org/a", **kwargs).ok
    assert validate_outbound_url("https://www.ifrc.org/a", **kwargs).ok
    assert not validate_outbound_url("https://evilifrc.org/a", **kwargs).ok
    assert not validate_outbound_url("https://ifrc.org.evil.com/a", **kwargs).ok


def test_empty_allowlist_denies_everything():
    assert not validate_outbound_url("https://ifrc.org/", allowed_hosts=[], resolver=_public).ok


def test_port_restriction():
    assert not validate_outbound_url("https://ifrc.org:8443/", allowed_ports=(443,), resolver=_public).ok
    assert validate_outbound_url("https://ifrc.org/", allowed_ports=(443,), resolver=_public).ok


def test_ifrc_fetch_url_delegates_to_shared_policy():
    from app.routes.ai_documents.helpers import _validate_ifrc_fetch_url

    ok, _ = _validate_ifrc_fetch_url("https://evil.example.com/a.pdf")
    assert not ok
    ok, _ = _validate_ifrc_fetch_url("http://www.ifrc.org/a.pdf")
    assert not ok
