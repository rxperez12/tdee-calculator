import pytest

from tdee_calculator.security import allowed_hosts, is_cross_origin


@pytest.mark.parametrize(
    "method,host,origin,site,refused",
    [
        ("GET", "127.0.0.1:8000", None, "cross-site", False),
        ("HEAD", None, "null", "cross-site", False),
        ("OPTIONS", None, None, "cross-site", False),
        ("POST", "127.0.0.1:8000", None, "same-origin", False),
        ("POST", "127.0.0.1:8000", None, "none", False),
        ("POST", "127.0.0.1:8000", None, "same-site", True),
        ("POST", "127.0.0.1:8000", None, "cross-site", True),
        ("POST", "127.0.0.1:8000", None, "unexpected", True),
        ("POST", "127.0.0.1:8000", None, "", True),
        ("POST", "127.0.0.1:8000", "http://evil.example", "same-origin", False),
        ("POST", "127.0.0.1:8000", "http://127.0.0.1:8000", "cross-site", True),
        ("POST", "127.0.0.1:8000", "http://127.0.0.1:8000", None, False),
        ("POST", "localhost:8000", "http://localhost:8000", None, False),
        ("POST", "[::1]:8000", "http://[::1]:8000", None, False),
        ("POST", "127.0.0.1:8000", "http://evil.example:8000", None, True),
        ("POST", "127.0.0.1:8000", "http://127.0.0.1:9000", None, True),
        ("POST", "127.0.0.1:8000", "null", None, True),
        ("POST", "127.0.0.1:8000", "garbage", None, True),
        ("POST", "127.0.0.1:8000", "http://[", None, True),
        ("POST", "127.0.0.1:8000", "//127.0.0.1:8000", None, True),
        ("POST", "127.0.0.1:8000", "http://127.0.0.1:8000/path", None, True),
        ("POST", None, "http://127.0.0.1:8000", None, True),
        ("POST", "127.0.0.1:8000", "", None, True),
        ("POST", None, None, None, False),
        ("PUT", "127.0.0.1:8000", None, "cross-site", True),
        ("PATCH", "127.0.0.1:8000", None, "cross-site", True),
        ("DELETE", "127.0.0.1:8000", None, "cross-site", True),
    ],
)
def test_cross_origin_policy(method, host, origin, site, refused) -> None:
    assert is_cross_origin(method, host, origin, site) is refused


def test_allowed_hosts(config) -> None:
    assert set(allowed_hosts(config)) == {"localhost", "127.0.0.1", "[::1]"}
