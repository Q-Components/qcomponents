# -*- coding: utf-8 -*-
"""One-shot local loopback OAuth callback server.

Several CLI OAuth clients (OpenAI Codex, Claude Code, Grok CLI, Gemini CLI)
register a fixed **loopback** redirect URI — e.g. ``http://localhost:1455/auth/
callback``. Their authorization server will only redirect there, so to capture
the ``?code=…&state=…`` automatically (instead of asking the user to copy-paste
the redirected URL) we briefly listen on that exact loopback host/port.

Design notes for the Odoo context:
- The browser and Odoo must share the host (a self-hosted, single-machine
  Odoo — the common case for these CLI logins). If they don't, binding still
  succeeds but the redirect never reaches us; the wizard's paste-back flow is
  the always-available fallback.
- Requires Odoo in **threaded mode** (``workers = 0``, the default): the
  captured result lives in this process's memory and the polling request must
  hit the same process. With multiple worker processes only the worker that
  bound the socket sees the result — paste-back remains the fallback there.
- The listener thread does pure socket I/O and never touches the ORM/cursor.
- Results are keyed by the expected ``state`` so a stray request can't inject
  a code for a different flow.
"""
from __future__ import annotations

import http.server
import logging
import threading
import time
from urllib.parse import urlparse, parse_qs

_logger = logging.getLogger(__name__)

_lock = threading.Lock()
_results: dict = {}    # state -> {'code','state','error','error_description'}
_servers: dict = {}    # state -> http.server.HTTPServer (so we can cancel)

_SUCCESS_HTML = (
    b"<!doctype html><html><head><meta charset='utf-8'><title>Authorized</title>"
    b"<style>body{font-family:system-ui;margin:4rem auto;max-width:30rem;text-align:center}"
    b"h2{color:#0a7}</style></head><body><h2>&#10003; Authorization received</h2>"
    b"<p>You can close this tab and return to Odoo.</p></body></html>"
)
_WAIT_HTML = b"<!doctype html><html><body>Waiting for the OAuth redirect&hellip;</body></html>"


def _make_handler(expected_state, expected_path):
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            parsed = urlparse(self.path)
            if expected_path and parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(_WAIT_HTML)
                return
            qs = parse_qs(parsed.query, keep_blank_values=False)
            got = {k: (qs[k][0] if qs.get(k) else None)
                   for k in ('code', 'state', 'error', 'error_description')}
            if got.get('code') or got.get('error'):
                with _lock:
                    _results[expected_state] = got
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML)

        def log_message(self, *args):  # silence default stderr logging
            return
    return _Handler


def start(state, host, port, path, timeout=300):
    """Bind a one-shot listener on (host, port). Returns True if listening.

    Returns False (caller falls back to paste-back) if the address can't be
    bound — port already in use, not permitted, etc.
    """
    try:
        httpd = http.server.HTTPServer((host, int(port)), _make_handler(state, path))
    except OSError as exc:
        _logger.info("OAuth loopback bind %s:%s failed (%s) — using paste-back.",
                     host, port, exc)
        return False
    httpd.timeout = 1.0
    with _lock:
        _results.pop(state, None)
        _servers[state] = httpd
    deadline = time.monotonic() + timeout

    def _serve():
        try:
            while time.monotonic() < deadline:
                with _lock:
                    if state in _results:
                        break
                httpd.handle_request()  # blocks up to httpd.timeout for one request
        finally:
            try:
                httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            with _lock:
                _servers.pop(state, None)

    threading.Thread(target=_serve, name='ai-oauth-loopback', daemon=True).start()
    return True


def result(state):
    """Return the captured callback dict for *state*, or None if not yet seen."""
    with _lock:
        return _results.get(state)


def cancel(state):
    """Stop listening and drop any captured result for *state*."""
    with _lock:
        httpd = _servers.pop(state, None)
        _results.pop(state, None)
    if httpd is not None:
        try:
            httpd.server_close()
        except Exception:  # noqa: BLE001
            pass


def is_loopback(host):
    """True for hosts safe to bind a local listener on."""
    return (host or '').lower() in ('localhost', '127.0.0.1', '::1', '0.0.0.0')
