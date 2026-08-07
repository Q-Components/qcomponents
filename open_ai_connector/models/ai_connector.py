# -*- coding: utf-8 -*-
"""ai.connector — the unified chat() service method.

This is the unified "AI connector method": given a provider, a model
and OpenAI-format messages, resolve credentials, pick the transport for the
provider's api_mode, send the request and return a normalized response. Supports
tools, vision and streaming.
"""
import logging
import re
import time

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)
_MAX_LOG_BODY = 20000


class AiConnector(models.AbstractModel):
    _name = 'ai.connector'
    _description = 'AI Connector Service'

    # ── public API ─────────────────────────────────────────────────────
    @api.model
    def chat(self, provider, model, messages, tools=None, tool_choice=None,
             temperature=None, max_tokens=None, stream=False, credential=None,
             extra=None, log=True, timeout=120.0):
        """Call a model and return a normalized response.

        :param provider: ai.provider record or its code string.
        :param model: model id string.
        :param messages: OpenAI-format messages (content may be a multimodal list).
        :param tools/tool_choice: OpenAI tool schemas + choice.
        :param stream: when True, returns a generator of chunk dicts; the last
            chunk is ``{'done': True, 'content', 'finish_reason', 'usage', ...}``.
        :returns: dict (NormalizedResponse.to_dict) or a generator if stream.
        """
        self._check_access()
        self._apply_outbound_policy()
        provider_rec = self._resolve_provider(provider)
        if not provider_rec.is_wired:
            raise UserError(_(
                "Provider '%s' (%s/%s) is not wired in this connector.",
                provider_rec.code, provider_rec.api_mode, provider_rec.auth_type))
        cred_rec = self._resolve_credential(provider_rec, credential)
        ctx = self._build_ctx(provider_rec, cred_rec, model, messages, tools,
                              tool_choice, temperature, max_tokens, stream, extra, timeout)
        transport = self._get_transport(provider_rec.api_mode)

        if stream:
            return self._chat_stream(transport, ctx, provider_rec, cred_rec, model, log)
        return self._chat_once(transport, ctx, provider_rec, cred_rec, model, log)

    @api.model
    def chat_text(self, provider, model, messages, **kwargs):
        """Convenience wrapper returning just the assistant text."""
        kwargs['stream'] = False
        result = self.chat(provider, model, messages, **kwargs)
        return result.get('content') or ''

    # ── media generation (image / video) ────────────────────────────────
    @api.model
    def generate_image(self, provider, model, prompt, credential=None, extra=None,
                       timeout=120.0, log=True, image=None, mode='generate'):
        """Generate or remix image(s) via the OpenAI-style image endpoints.

        Reference backend: xAI ``grok-imagine-image`` (also fits OpenAI's image
        API). When *image* is given and *mode* is ``edit``/``remix``, the existing
        image is edited (image-to-image) via the provider's edit path — gated on
        the provider's ``supports_image_edit`` flag. Each result is materialized
        into an ``ir.attachment`` (provider URLs are often ephemeral). Returns
        ``{'images': [{'attachment_id','mimetype','b64','url'}], 'model'}``.
        """
        from ..tools import media_gen
        from ..tools.http_client import AiHttpError
        self._check_access()
        self._apply_outbound_policy()
        provider_rec = self._resolve_provider(provider)
        cred_rec = self._resolve_credential(provider_rec, credential)
        # The ChatGPT/Codex backend generates images through the /responses
        # image_generation tool (SSE), NOT /images/generations — branch to it.
        is_codex = (provider_rec.code == 'openai-codex'
                    or 'chatgpt.com/backend-api/codex' in (provider_rec.base_url or ''))
        is_edit = bool(image) and mode in ('edit', 'remix')
        if is_edit and not provider_rec.supports_image_edit:
            raise UserError(_(
                "Remix (image-to-image) isn't supported for %s. Use Generate, or "
                "pick a provider that supports image editing.", provider_rec.code))
        model = model or ('gpt-image-2-medium' if is_codex else media_gen.DEFAULT_IMAGE_MODEL)
        proxy = self._media_proxy(provider_rec, cred_rec)
        started = time.monotonic()

        def _do(headers, base_url):
            if is_codex:
                from ..tools import codex_responses
                return codex_responses.generate_image_codex(
                    base_url, headers, model, prompt,
                    source_image=image if is_edit else None, proxy_url=proxy,
                    extra=extra, timeout=max(timeout, 300.0))
            if is_edit:
                from ..tools import media_edit
                from ..tools.codex_responses import _codex_image_size
                aspect = (extra or {}).get('aspect_ratio')
                size = _codex_image_size(aspect) if aspect else None
                return media_edit.edit_image(base_url, headers, model, prompt, image,
                                             size=size, proxy_url=proxy, extra=extra,
                                             timeout=timeout)
            return media_gen.generate_image(base_url, headers, model, prompt,
                                            proxy_url=proxy, extra=extra, timeout=timeout)
        try:
            result = self._media_request(provider_rec, cred_rec, _do)
        except AiHttpError as exc:
            self._write_media_log(provider_rec, cred_rec, model, prompt, status='error',
                                  error=str(exc),
                                  duration_ms=int((time.monotonic() - started) * 1000), log=log)
            raise UserError(_("Image generation failed: %s", exc))
        images = []
        for img in (result.get('images') or []):
            mat = self._materialize_media(provider_rec, img.get('b64_json'), img.get('url'),
                                          img.get('mime_type') or 'image/png',
                                          prefix='image', proxy=proxy)
            if mat:
                images.append(mat)
        self._write_media_log(provider_rec, cred_rec, model, prompt, status='ok',
                              response='%d image(s)' % len(images),
                              duration_ms=int((time.monotonic() - started) * 1000), log=log)
        if not images:
            raise UserError(_("The provider returned no image."))
        return {'images': images, 'model': model}

    @api.model
    def generate_video(self, provider, model, prompt, credential=None, image_url=None,
                       extra=None, timeout=120.0, poll_timeout=180.0, poll_interval=5.0,
                       log=True):
        """Generate a video via the async ``/videos/generations`` job endpoint.

        Submits the job, polls ``/videos/{id}`` until ``done`` (bounded by
        *poll_timeout*), then materializes the result as an ``ir.attachment``.
        Returns ``{'video_url','attachment','model','status'}``. The poll blocks
        the calling thread — fine for the Playground; the gateway would need an
        async variant for long renders.
        """
        from ..tools import media_gen
        from ..tools.http_client import AiHttpError
        self._check_access()
        self._apply_outbound_policy()
        provider_rec = self._resolve_provider(provider)
        cred_rec = self._resolve_credential(provider_rec, credential)
        model = model or media_gen.DEFAULT_VIDEO_MODEL
        proxy = self._media_proxy(provider_rec, cred_rec)
        started = time.monotonic()

        def _submit(headers, base_url):
            rid = media_gen.submit_video(base_url, headers, model, prompt,
                                         image_url=image_url, proxy_url=proxy,
                                         extra=extra, timeout=timeout)
            return rid, headers, base_url
        try:
            request_id, headers, base_url = self._media_request(provider_rec, cred_rec, _submit)
            if not request_id:
                raise UserError(_("Video submission returned no request id."))
            body, status = {}, 'queued'
            deadline = time.monotonic() + poll_timeout
            while time.monotonic() < deadline:
                time.sleep(poll_interval)
                body = media_gen.poll_video(base_url, headers, request_id, proxy_url=proxy)
                done, status = media_gen.video_done(body)
                if done:
                    break
        except AiHttpError as exc:
            self._write_media_log(provider_rec, cred_rec, model, prompt, status='error',
                                  error=str(exc),
                                  duration_ms=int((time.monotonic() - started) * 1000), log=log)
            raise UserError(_("Video generation failed: %s", exc))
        if status != 'done':
            self._write_media_log(provider_rec, cred_rec, model, prompt, status='error',
                                  error='status=%s' % status,
                                  duration_ms=int((time.monotonic() - started) * 1000), log=log)
            raise UserError(_(
                "Video generation didn't finish in time (status: %s). Try again or "
                "raise the timeout.", status))
        video_url = media_gen.extract_video_url(body)
        attachment = self._materialize_media(provider_rec, None, video_url, 'video/mp4',
                                             prefix='video', proxy=proxy) if video_url else None
        self._write_media_log(provider_rec, cred_rec, model, prompt, status='ok',
                              response=video_url or 'video',
                              duration_ms=int((time.monotonic() - started) * 1000), log=log)
        return {'video_url': video_url, 'attachment': attachment, 'model': model, 'status': status}

    def _media_proxy(self, provider_rec, cred_rec):
        from ..tools import auth
        return auth.resolve(provider_rec._to_dict(), cred_rec._as_cred_dict())['proxy_url']

    def _media_request(self, provider_rec, cred_rec, do):
        """Resolve auth, run *do(headers, base_url)*; on an auth failure force an
        OAuth refresh and retry once (xAI tokens must be fresh —
        proactive refresh plus a reactive force_refresh backstop)."""
        from ..tools import auth
        from ..tools.http_client import AiHttpError

        def _headers_base():
            resolved = auth.resolve(provider_rec._to_dict(), cred_rec._as_cred_dict())
            headers = dict(resolved['headers'])
            headers.setdefault('Content-Type', 'application/json')
            headers.setdefault('Accept', 'application/json')
            headers.setdefault('User-Agent', 'OdooAIConnector/19.0')
            base_url = resolved['base_url'] or provider_rec.base_url
            return headers, base_url

        cred_rec._ensure_oauth_fresh()
        headers, base_url = _headers_base()
        try:
            return do(headers, base_url)
        except AiHttpError as exc:
            if self._is_auth_error(exc) and cred_rec.sudo().oauth_refresh_token:
                self._force_refresh_oauth(cred_rec)
                headers, base_url = _headers_base()
                return do(headers, base_url)
            raise

    @staticmethod
    def _is_auth_error(exc):
        if getattr(exc, 'status_code', None) in (401, 403):
            return True
        msg = str(exc).lower()
        return any(s in msg for s in ('could not be validated', 'unauthor',
                                      'invalid_grant', 'invalid token', 'expired'))

    def _force_refresh_oauth(self, cred_rec):
        from ..tools import oauth
        fresh = oauth.refresh(cred_rec.sudo()._as_cred_dict())
        if fresh.get('oauth_access_token'):
            cred_rec.sudo()._apply_token_updates(fresh)

    def _materialize_media(self, provider_rec, b64, url, mimetype, *, prefix, proxy):
        """Store generated media as an ir.attachment. b64 wins; else download url."""
        import base64
        from ..tools import http_client
        data_b64 = b64 or None
        if not data_b64 and url:
            content, ctype = http_client.get_bytes(url, timeout=180.0, proxy_url=proxy)
            data_b64 = base64.b64encode(content).decode()
            if ctype:
                mimetype = ctype.split(';')[0].strip() or mimetype
        if not data_b64:
            return None
        ext = ((mimetype or 'application/octet-stream').split('/')[-1] or 'bin').split('+')[0]
        att = self.env['ir.attachment'].sudo().create({
            'name': '%s_%s.%s' % (prefix, provider_rec.code, ext),
            'datas': data_b64, 'mimetype': mimetype,
            'res_model': 'ai.connector', 'res_id': 0,
        })
        return {'attachment_id': att.id, 'mimetype': mimetype, 'b64': data_b64, 'url': url}

    def _write_media_log(self, provider_rec, cred_rec, model, prompt, *, status,
                         duration_ms, response=None, error=None, log=True):
        if not log:
            return
        try:
            self.env['ai.completion.log'].sudo().create({
                'provider_id': provider_rec.id,
                'credential_id': cred_rec.id,
                'model': model,
                'request_json': self._truncate(prompt or ''),
                'response_text': self._truncate(response or error or ''),
                'duration_ms': duration_ms,
                'status': status,
                'error': error or False,
                'user_id': self.env.uid,
            })
        except Exception:  # noqa: BLE001 - logging must never break a request
            _logger.exception("Failed to write ai.completion.log (media)")

    # ── internals ──────────────────────────────────────────────────────
    def _check_access(self):
        if self.env.su:
            return
        if not self.env.user.has_group('open_ai_connector.group_ai_user'):
            raise AccessError(_("You are not allowed to use the AI Connector."))

    @api.model
    def _apply_outbound_policy(self):
        """Load the configurable SSRF policy from settings into the HTTP layer.

        Called before every outbound-triggering operation (chat, model fetch,
        OAuth) so the guard reflects current config on this thread. Safe
        defaults (metadata/link-local always blocked) apply even if unset.

        When an allowlist IS set, it's unioned with the module's OWN configured
        provider endpoints (base/models/OAuth hosts of providers you have
        credentials for) — the allowlist is meant to block arbitrary/internal
        hosts, not your own providers' inference or login endpoints. Otherwise a
        restrictive allowlist silently breaks OAuth/model-fetch.
        """
        from ..tools import http_client
        icp = self.env['ir.config_parameter'].sudo()
        block_private = icp.get_param(
            'open_ai_connector.block_private_endpoints', 'False') in ('True', 'true', '1')
        raw = icp.get_param('open_ai_connector.outbound_host_allowlist', '') or ''
        allowlist = [h for h in re.split(r'[\s,]+', raw) if h]
        if allowlist:
            allowlist = sorted(set(allowlist) | self._provider_endpoint_hosts())
        http_client.set_outbound_policy(block_private=block_private, allowlist=allowlist or None)

    @api.model
    def _provider_endpoint_hosts(self):
        """Every host the connector's own models + authentication legitimately use.

        Collected from the FULL provider catalog (not just providers you have a
        credential for) so an admin allowlist never blocks the connector's own
        model/inference or OAuth/login endpoints — it only adds/restricts truly
        external hosts. Covers each provider's base/models/OAuth-authorize/token/
        device/discovery URLs, every credential's per-record overrides (which win
        at runtime), and the transport-hardcoded Gemini Cloud Code endpoints.
        These are all trusted, seed- or manager-configured targets.
        """
        from urllib.parse import urlparse
        hosts = set()

        def _add(url):
            if not url:
                return
            try:
                parsed = urlparse(url if '://' in url else 'https://' + url)
            except (ValueError, TypeError):
                return
            # Only real HTTP(S) endpoints — skips internal-scheme markers like
            # gemini-cli's 'cloudcode-pa://google' (the real hosts are added below).
            if (parsed.scheme or '').lower() not in ('http', 'https'):
                return
            host = (parsed.hostname or '').lower().rstrip('.')
            if host and host.isascii():
                hosts.add(host)

        prov_fields = ('base_url', 'models_url', 'oauth_auth_url', 'oauth_token_url',
                       'oauth_device_authorization_url', 'oauth_discovery_url')
        for prov in self.env['ai.provider'].sudo().search([]):
            for fname in prov_fields:
                _add(prov[fname])
        # Credential-level overrides WIN at runtime (see _as_cred_dict: the OAuth
        # host is cred.oauth_token_url OR provider's). Collect them too — covers
        # custom/Azure-Foundry providers, regional/rotated token hosts, and the
        # xAI OIDC-discovered endpoints the wizard persists onto the credential.
        cred_fields = ('base_url', 'oauth_auth_url', 'oauth_token_url',
                       'oauth_device_authorization_url')
        for cred in self.env['ai.credential'].sudo().search([]):
            for fname in cred_fields:
                _add(cred[fname])
        # Gemini Cloud Code talks to fixed Google endpoints not held in any field.
        from ..tools import gemini_cloudcode as gcc
        for url in [gcc.CODE_ASSIST_ENDPOINT] + list(gcc._FALLBACK_ENDPOINTS):
            _add(url)
        return hosts

    @api.model
    def _resolve_provider(self, provider):
        if isinstance(provider, models.BaseModel):
            return provider
        rec = self.env['ai.provider']._resolve(provider)
        if not rec:
            raise UserError(_("Unknown AI provider: %s", provider))
        return rec

    @api.model
    def _resolve_credential(self, provider_rec, credential):
        if credential:
            if isinstance(credential, models.BaseModel):
                cred = credential
            else:
                cred = self.env['ai.credential'].browse(int(credential))
            if not cred.exists():
                raise UserError(_("Credential not found."))
            # Enforce the CALLER's ACL + record rules (incl. multi-company)
            # before we sudo-read the secret — otherwise any AI user could pass
            # an arbitrary credential id over RPC and borrow a key they were
            # never granted. Internal sudo callers (env.su) skip the check.
            if not self.env.su:
                cred.check_access('read')
            if cred.provider_id != provider_rec:
                raise UserError(_(
                    "The selected credential does not belong to provider '%s'.",
                    provider_rec.code))
            return cred.sudo()
        # No explicit credential: pick the provider's default. Search in the
        # caller's env so record rules apply (a user only gets credentials they
        # may access); sudo only the resulting record for the secret read.
        Cred = self.env['ai.credential']
        domain = [('provider_id', '=', provider_rec.id), ('active', '=', True),
                  ('company_id', 'in', [self.env.company.id, False])]
        cred = Cred.search(domain + [('is_default', '=', True)], limit=1) \
            or Cred.search(domain, limit=1)
        if not cred:
            raise UserError(_("No credential configured for provider '%s'.", provider_rec.code))
        return cred.sudo()

    def _build_ctx(self, provider_rec, cred_rec, model, messages, tools, tool_choice,
                   temperature, max_tokens, stream, extra, timeout):
        from ..tools import auth
        from ..tools.transport_base import RequestContext
        cred_rec._ensure_oauth_fresh()
        provider_dict = provider_rec._to_dict()
        cred_dict = cred_rec._as_cred_dict()
        resolved = auth.resolve(provider_dict, cred_dict)
        extra = dict(extra or {})
        if provider_rec.auth_type == 'aws_sdk':
            extra.setdefault('aws_region', cred_dict.get('aws_region'))
        if provider_rec.api_mode == 'gemini_cloudcode':
            # The Code Assist envelope needs a GCP project. The OAuth bearer was
            # just resolved into the headers — reuse it to discover/cache the
            # project so the transport can build a valid request.
            token = (resolved['headers'].get('Authorization') or '')[len('Bearer '):]
            extra['gemini_project_id'] = cred_rec._ensure_gemini_project(token, timeout=timeout)
        return RequestContext(
            model=model, messages=messages, tools=tools, tool_choice=tool_choice,
            temperature=temperature, max_tokens=max_tokens, stream=stream, extra=extra,
            provider=provider_dict, headers=resolved['headers'],
            base_url=resolved['base_url'], proxy_url=resolved['proxy_url'],
            boto3_session=resolved['boto3_session'], timeout=timeout)

    @api.model
    def _get_transport(self, api_mode):
        from ..tools.transport_base import get_transport
        transport = get_transport(api_mode)
        if transport is None:
            raise UserError(_("No transport implemented for api_mode '%s'.", api_mode))
        return transport

    def _chat_once(self, transport, ctx, provider_rec, cred_rec, model, log):
        from ..tools.http_client import AiHttpError
        started = time.monotonic()
        try:
            nr = transport.complete(ctx)
        except AiHttpError as exc:
            self._write_log(provider_rec, cred_rec, model, ctx, None,
                            status='error', error=str(exc),
                            duration_ms=int((time.monotonic() - started) * 1000), log=log)
            raise UserError(_("AI request failed: %s", exc))
        result = nr.to_dict()
        self._write_log(provider_rec, cred_rec, model, ctx, nr, status='ok',
                        duration_ms=int((time.monotonic() - started) * 1000), log=log)
        return result

    def _chat_stream(self, transport, ctx, provider_rec, cred_rec, model, log):
        from ..tools.http_client import AiHttpError
        started = time.monotonic()
        # Bind to a fresh cursor-independent reference so the generator can log.
        connector = self

        def _gen():
            final = {}
            try:
                for chunk in transport.stream(ctx):
                    if chunk.get('done'):
                        final = chunk
                    yield chunk
            except AiHttpError as exc:
                connector._write_log(provider_rec, cred_rec, model, ctx, None,
                                     status='error', error=str(exc),
                                     duration_ms=int((time.monotonic() - started) * 1000),
                                     log=log)
                raise
            connector._write_log_from_final(provider_rec, cred_rec, model, ctx, final,
                                            duration_ms=int((time.monotonic() - started) * 1000),
                                            log=log)
        return _gen()

    # ── logging ────────────────────────────────────────────────────────
    def _write_log(self, provider_rec, cred_rec, model, ctx, nr, *, status,
                   duration_ms, error=None, log=True):
        if not log:
            return
        try:
            usage = nr.usage if nr else None
            self.env['ai.completion.log'].sudo().create({
                'provider_id': provider_rec.id,
                'credential_id': cred_rec.id,
                'model': model,
                'request_json': self._truncate(self._dump(ctx.messages)),
                'response_text': self._truncate(nr.content if nr else (error or '')),
                'finish_reason': nr.finish_reason if nr else False,
                'prompt_tokens': usage.prompt_tokens if usage else 0,
                'completion_tokens': usage.completion_tokens if usage else 0,
                'total_tokens': usage.total_tokens if usage else 0,
                'duration_ms': duration_ms,
                'status': status,
                'error': error or False,
                'user_id': self.env.uid,
            })
        except Exception:  # noqa: BLE001 - logging must never break a request
            _logger.exception("Failed to write ai.completion.log")

    def _write_log_from_final(self, provider_rec, cred_rec, model, ctx, final,
                              *, duration_ms, log=True):
        if not log:
            return
        usage = final.get('usage') or {}
        try:
            self.env['ai.completion.log'].sudo().create({
                'provider_id': provider_rec.id,
                'credential_id': cred_rec.id,
                'model': model,
                'request_json': self._truncate(self._dump(ctx.messages)),
                'response_text': self._truncate(final.get('content') or ''),
                'finish_reason': final.get('finish_reason') or False,
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'total_tokens': usage.get('total_tokens', 0),
                'duration_ms': duration_ms,
                'status': 'ok',
                'user_id': self.env.uid,
            })
        except Exception:  # noqa: BLE001
            _logger.exception("Failed to write ai.completion.log (stream)")

    @staticmethod
    def _dump(obj):
        import json
        try:
            return json.dumps(obj, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(obj)

    @staticmethod
    def _truncate(text):
        text = text or ''
        return text if len(text) <= _MAX_LOG_BODY else text[:_MAX_LOG_BODY] + ' …[truncated]'
