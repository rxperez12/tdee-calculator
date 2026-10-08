from urllib.parse import urlsplit

from tdee_calculator.config import Config

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def is_cross_origin(
    method: str, host: str | None, origin: str | None, sec_fetch_site: str | None
) -> bool:
    if method in SAFE_METHODS:
        return False
    if sec_fetch_site is not None:
        return sec_fetch_site not in {"same-origin", "none"}
    if origin is None:
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return True
    return (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.netloc != host
        or bool(parsed.path or parsed.query or parsed.fragment)
    )


def allowed_hosts(config: Config) -> list[str]:
    return list(dict.fromkeys((*LOCAL_HOSTS, config.host)))
