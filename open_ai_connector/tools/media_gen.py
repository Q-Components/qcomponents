# -*- coding: utf-8 -*-
"""Image / video generation over the OpenAI-style media endpoints.

Covers xAI Grok Imagine image + video generation.
These are a SEPARATE API surface from chat (NOT generateContent / messages):

  * Image — sync ``POST {base}/images/generations``  body ``{model, prompt, ...}``
    → ``{data: [{url | b64_json, mime_type}]}``.
  * Video — async ``POST {base}/videos/generations``  body ``{model, prompt, ...}``
    → ``{request_id}``; then poll ``GET {base}/videos/{request_id}`` until
    ``status == 'done'`` → ``{video: {url, duration}}``.

xAI Grok Imagine is the reference backend (``grok-imagine-image`` /
``grok-imagine-video``); the OpenAI-style shape also fits OpenAI's image API.
xAI image URLs are EPHEMERAL (``imgen.x.ai/xai-tmp-*`` 404 within minutes), so
callers must download the bytes immediately — see ``ai.connector`` which stores
them as an ``ir.attachment``.

Auth is the provider's resolved Bearer header. CRITICAL: OAuth media calls need
a FRESH token — the model layer refreshes proactively and retries with a forced
refresh on a 401.
"""
from __future__ import annotations

from . import http_client

DEFAULT_IMAGE_MODEL = 'grok-imagine-image'
DEFAULT_VIDEO_MODEL = 'grok-imagine-video'

# Generic size vocab (used by AI Image Studio) -> xAI Grok Imagine aspect_ratio.
# xAI expects ratios like '1:1'/'16:9'/'9:16', not the generic words; pass any
# already-ratio value through unchanged.
_ASPECT_TO_XAI = {'square': '1:1', 'landscape': '16:9', 'portrait': '9:16'}

# Terminal video-job states (besides 'done').
_VIDEO_FAILED_STATES = {'failed', 'error', 'expired', 'cancelled'}


def _norm_base(base_url: str) -> str:
    return (base_url or '').strip().rstrip('/')


def generate_image(base_url, headers, model, prompt, *, proxy_url=None,
                   extra=None, timeout=120.0) -> dict:
    """Sync image generation. Returns ``{'images': [{b64_json,url,mime_type}], 'raw'}``."""
    url = _norm_base(base_url) + '/images/generations'
    body = {'model': model or DEFAULT_IMAGE_MODEL, 'prompt': prompt}
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is None:
                continue
            if k == 'aspect_ratio':
                v = _ASPECT_TO_XAI.get(str(v).lower(), v)
            body[k] = v
    resp = http_client.post_json(url, headers=headers, json_body=body,
                                 timeout=timeout, proxy_url=proxy_url, max_retries=0)
    images = []
    for item in (resp.get('data') or []):
        if not isinstance(item, dict):
            continue
        images.append({
            'b64_json': item.get('b64_json'),
            'url': item.get('url'),
            'mime_type': item.get('mime_type') or item.get('mimeType') or 'image/png',
        })
    return {'images': images, 'raw': resp}


def submit_video(base_url, headers, model, prompt, *, image_url=None,
                 proxy_url=None, extra=None, timeout=120.0) -> str:
    """Submit a video job; returns its ``request_id``."""
    url = _norm_base(base_url) + '/videos/generations'
    body = {'model': model or DEFAULT_VIDEO_MODEL, 'prompt': prompt}
    if image_url:
        body['image'] = {'url': image_url}
    if isinstance(extra, dict):
        body.update({k: v for k, v in extra.items() if v is not None})
    resp = http_client.post_json(url, headers=headers, json_body=body,
                                 timeout=timeout, proxy_url=proxy_url, max_retries=0)
    return resp.get('request_id') or resp.get('id') or ''


def poll_video(base_url, headers, request_id, *, proxy_url=None, timeout=20.0) -> dict:
    """Poll a video job once. Returns the raw job body (with ``status``)."""
    url = _norm_base(base_url) + '/videos/' + str(request_id)
    return http_client.get_json(url, headers=headers, timeout=timeout, proxy_url=proxy_url)


def video_done(body: dict) -> tuple[bool, str]:
    """(finished?, status) for a polled video body."""
    status = str((body or {}).get('status') or '').lower()
    if status == 'done':
        return True, status
    if status in _VIDEO_FAILED_STATES:
        return True, status
    return False, status or 'queued'


def extract_video_url(body: dict) -> str:
    video = (body or {}).get('video') or {}
    if isinstance(video, dict):
        return video.get('url') or ''
    return ''
