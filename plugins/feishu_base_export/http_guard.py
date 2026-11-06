"""Allow only official Feishu HTTPS hosts. Callers must not follow redirects."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

OFFICIAL_HOSTS = frozenset({"open.feishu.cn", "open.larksuite.com"})


class UrlRejected(ValueError):
    pass


def parse_official_https(url: str, *, allowed_hosts=OFFICIAL_HOSTS) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UrlRejected("scheme")
    if parts.username or parts.password:
        raise UrlRejected("userinfo")
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in allowed_hosts:
        raise UrlRejected("host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UrlRejected("ip-literal")
    if parts.port not in (None, 443):
        raise UrlRejected("port")
    segments = [segment for segment in parts.path.split("/") if segment != ""]
    if any(segment == ".." for segment in segments):
        raise UrlRejected("path")
    path = "/" + "/".join(segments) if segments else "/"
    query = f"?{parts.query}" if parts.query else ""
    return f"https://{host}{path}{query}"
