# -*- coding: utf-8 -*-
"""DNS pinning to close the SSRF resolve-vs-connect TOCTOU (DNS rebinding).

The guard validates a host by resolving it, but ``requests``/``urllib3`` resolve
it again independently at connect time — a short-TTL attacker domain can pass the
guard then rebind to 169.254.169.254 / loopback for the real connection. We close
that by resolving + vetting ONCE and then pinning that hostname to the approved
IP for the duration of the request: the connect-time lookup returns the same
vetted IP, while TLS SNI / Host / certificate validation still use the hostname.

Implementation: a transparent, idempotent wrapper around ``socket.getaddrinfo``.
With no pins set (the default for all other code in the process) it is a pure
passthrough — only hosts we explicitly pin inside a request window are affected,
and pins are thread-local and always cleared in a ``finally``.
"""
import socket
import threading

_orig_getaddrinfo = socket.getaddrinfo
_pins = threading.local()


def _patched_getaddrinfo(host, *args, **kwargs):
    table = getattr(_pins, 'table', None)
    if table:
        ip = table.get(host)
        if ip:
            # Resolve the literal pinned IP (trivial, returns proper structures).
            return _orig_getaddrinfo(ip, *args, **kwargs)
    return _orig_getaddrinfo(host, *args, **kwargs)


# Install once, process-wide, idempotently. Transparent unless a pin is set.
if not getattr(socket, '_ai_connector_dns_patched', False):
    socket.getaddrinfo = _patched_getaddrinfo
    socket._ai_connector_dns_patched = True


def set_pin(host, ip):
    table = getattr(_pins, 'table', None)
    if table is None:
        table = {}
        _pins.table = table
    table[host] = ip


def clear_pins():
    _pins.table = {}
