from urllib.parse import urlsplit, urlunsplit


class InvalidUrl(ValueError):
    pass


def normalize_url(raw: str) -> str:
    value = raw.strip()
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise InvalidUrl from error
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        raise InvalidUrl

    host = parts.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += f":{parts.password}"
        userinfo += "@"
    netloc = f"{userinfo}{host}"
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((scheme, netloc, parts.path, parts.query, ""))
