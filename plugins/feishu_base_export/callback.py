"""Loopback OAuth callback. The authorization code never enters chat or logs."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from plugins.feishu_base_export.config import loopback_host, redirect_class
from plugins.feishu_base_export.oauth_flow import OAuthError, exchange_code, user_open_id
from plugins.feishu_base_export.service import save_issued

logger = logging.getLogger(__name__)
_OK = "授权成功，请回到飞书私聊。"
_NO = "授权失败"
_SERVERS: list[ThreadingHTTPServer] = []


def describe_setup(config) -> dict:
    """Report readiness. This function does not bind a socket."""
    kind = redirect_class(config.redirect_uri, config.listen_port)
    problems = config.callback_problems()
    return {
        "ok": True,
        "status": "dry-run",
        "listening": False,
        "missing": problems,
        "listen_host": config.listen_host,
        "oauth_local_ready": kind == "local" and not problems,
        "oauth_remote_ready": kind == "remote" and not problems,
        "auth_ready": False,
    }


def handle_callback(query: dict, *, deps, now: float) -> tuple[int, str]:
    code = str(query.get("code") or "")
    state = str(query.get("state") or "")
    if not code or not state:
        _log("missing")
        return 400, _NO
    with _lock(state):
        pending = deps.states.peek(state, now=now)
        record = deps.states.consume(state, now=now) if pending is not None else None
    if record is None:
        _log("expired_or_replay")
        return 400, _NO
    try:
        issued = exchange_code(deps.transport, deps.config, code=code, verifier=record.verifier)
        got = user_open_id(deps.transport, deps.config, issued["access_token"])
    except OAuthError:
        _log("exchange")
        return 400, _NO
    if got != record.open_id:
        _log("open_id_mismatch")
        return 400, _NO
    previous = deps.now
    deps.now = now
    try:
        save_issued(record.open_id, issued, deps)
    finally:
        deps.now = previous
    _log("ok")
    return 200, _OK


def start_loopback(config, deps, *, port: int | None = None) -> ThreadingHTTPServer | None:
    if not loopback_host(config.listen_host):
        return None
    bind_port = config.listen_port if port is None else port
    if bind_port != 0 and not 1 <= bind_port <= 65535:
        return None
    path = urlsplit(config.redirect_uri).path or "/"
    handler = _handler(deps, path)
    try:
        server = ThreadingHTTPServer((config.listen_host, bind_port), handler)
    except OSError:
        return None
    thread = threading.Thread(target=server.serve_forever, name="feishu-oauth-callback", daemon=True)
    thread.start()
    _SERVERS.append(server)
    return server


def stop_loopback(server: ThreadingHTTPServer | None) -> None:
    if server is None:
        return
    server.shutdown()
    server.server_close()


def maybe_start() -> None:
    """Start only when every callback setting is present. Never opens a public port."""
    from plugins.feishu_base_export.config import production_config
    from plugins.feishu_base_export.dpapi import DpapiUnavailable
    from plugins.feishu_base_export.tool import active_deps

    try:
        config = production_config()
        if config.callback_problems():
            return
        start_loopback(config, active_deps())
    except DpapiUnavailable:
        logger.info("feishu oauth listener not started: Windows DPAPI is required to store tokens")
    except Exception:
        logger.info("feishu oauth listener not started")


def _handler(deps, path: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != path:
                self._send(404, _NO)
                return
            query = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
            status, body = handle_callback(query, deps=deps, now=deps.now)
            self._send(status, body)

        def log_message(self, fmt, *args):
            return

        def _send(self, status: int, body: str):
            raw = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def _log(reason: str) -> None:
    logger.info("feishu oauth callback %s", reason)


_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()


def _lock(state: str) -> threading.Lock:
    with _GUARD:
        return _LOCKS.setdefault(state, threading.Lock())
