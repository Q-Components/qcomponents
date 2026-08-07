# -*- coding: utf-8 -*-
"""Plain-Python connector core (no Odoo ORM dependencies).

One transport per ``api_mode`` owning the data path (build request -> send ->
normalize response), plus credential resolution (auth.py / oauth.py) and a
small HTTP client.
"""
from .types import NormalizedResponse, ToolCall, Usage
from .transport_base import get_transport, Transport

__all__ = [
    'NormalizedResponse', 'ToolCall', 'Usage',
    'get_transport', 'Transport',
]
