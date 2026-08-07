# -*- coding: utf-8 -*-
"""Stop seeding hardcoded "dummy" Claude models.

The live ``/v1/models`` fetch (now fixed to use the OAuth Bearer + anthropic-beta
headers and a browser TLS fingerprint, hitting /v1/models) is the source of
truth for the claude-oauth catalog. Clear the provider's seeded fallback list and
remove the stale seeded model rows so the catalog only ever reflects what the
live API returns on the next "Fetch Models".
"""


def migrate(cr, version):
    cr.execute("UPDATE ai_provider SET fallback_models = NULL WHERE code = 'claude-oauth'")
    cr.execute(
        """
        DELETE FROM ai_model
        WHERE provider_id IN (SELECT id FROM ai_provider WHERE code = 'claude-oauth')
          AND model_id IN ('claude-opus-4-1-20250805',
                           'claude-sonnet-4-5-20250929',
                           'claude-haiku-4-5-20251001')
        """
    )
