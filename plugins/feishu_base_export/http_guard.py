"""Allow only official Feishu HTTPS hosts. Redirects are refused, not followed."""

from __future__ import annotations

import ipaddress
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

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


class RedirectRefused(RuntimeError):
    pass


class _RefuseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RedirectRefused("redirect refused")


def guarded_request(method: str, url: str, user_token: str, body, *, limit: int = 32 * 1024 * 1024):
    safe = parse_official_https(url)
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(safe, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    if user_token:
        request.add_header("Authorization", f"Bearer {user_token}")
    opener = build_opener(_RefuseRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            payload = response.read(limit + 1)
    except RedirectRefused:
        raise
    except HTTPError as exc:
        payload = exc.read(4096) if exc.fp is not None else b""
        return _Response(exc.code, payload)
    if len(payload) > limit:
        raise ValueError("response too large")
    return _Response(status, payload)


class _Response:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body
