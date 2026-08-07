# -*- coding: utf-8 -*-
"""Image editing / remix over the OpenAI-compatible ``/images/edits`` endpoint.

Image-to-image: takes an existing image + a text prompt and returns an edited
image. Used by ``ai.connector.generate_image(mode='edit')`` for OpenAI-compatible
providers. The ChatGPT/Codex backend uses a SEPARATE path (a ``/responses`` call
with an ``input_image`` part) — see ``codex_responses.generate_image_codex``.
"""
from __future__ import annotations

import base64

from . import http_client


def _to_bytes(image):
    """Accept raw base64 (str/bytes), a ``data:`` URL, or raw image bytes -> raw bytes.

    Odoo ``fields.Image`` reads back as base64-ASCII *bytes* (att.datas =
    base64.b64encode(...)), so a naive ``isinstance(bytes)`` passthrough would
    upload the base64 text instead of the decoded image. Sniff a few image magic
    numbers so a genuinely-binary payload still passes through undecoded.
    """
    if isinstance(image, (bytes, bytearray, memoryview)):
        raw = bytes(image)
        head = raw[:4]
        if head[:2] == b'\xff\xd8' or head == b'\x89PNG' or head[:4] in (b'GIF8', b'RIFF') \
                or head[:2] == b'BM':
            return raw
        image = raw.decode('ascii', 'ignore')
    s = image or ''
    if s.startswith('data:'):
        s = s.split(',', 1)[-1]
    return base64.b64decode(s)


def edit_image(base_url, headers, model, prompt, image, *, size=None,
               proxy_url=None, extra=None, timeout=180.0) -> dict:
    """Edit/remix an image. Returns ``{'images': [{b64_json,url,mime_type}], 'raw'}``
    (same shape as ``media_gen.generate_image`` so the model layer materializes it
    uniformly)."""
    url = (base_url or '').strip().rstrip('/') + '/images/edits'
    data = {'model': model, 'prompt': prompt}
    if size:
        data['size'] = size
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is not None and k not in ('n', 'aspect_ratio'):
                data[k] = v
    files = {'image': ('image.png', _to_bytes(image), 'image/png')}
    resp = http_client.post_multipart(url, headers=headers, data=data, files=files,
                                      timeout=timeout, proxy_url=proxy_url)
    images = []
    for item in (resp.get('data') or []):
        if isinstance(item, dict):
            images.append({
                'b64_json': item.get('b64_json'),
                'url': item.get('url'),
                'mime_type': item.get('mime_type') or item.get('mimeType') or 'image/png',
            })
    return {'images': images, 'raw': resp}
