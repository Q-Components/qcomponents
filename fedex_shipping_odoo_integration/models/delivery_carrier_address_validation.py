import logging

import requests

from odoo import fields, models, _

_logger = logging.getLogger(__name__)


class DeliveryCarrierFedexAddressValidation(models.Model):
    """FedEx Address Validation API support (adds methods/fields only)."""
    _inherit = "delivery.carrier"

    fedex_validate_address = fields.Boolean(
        string="Validate Address with FedEx", copy=False,
        help="When validating a delivery order, check the delivery address with the "
             "FedEx Address Validation API before the shipment is created.")
    fedex_auto_correct_address = fields.Boolean(
        string="Auto-apply minor corrections (ZIP+4 only)", copy=False,
        help="If FedEx only changes the ZIP+4, update the customer's ZIP silently "
             "instead of opening the wizard.")

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------
    def _fedex_av_build_payload(self, partner, ref):
        streets = [s for s in (partner.street, partner.street2) if s]
        return {
            "validateAddressControlParameters": {"includeResolutionTokens": True},
            "addressesToValidate": [{
                "clientReferenceId": ref or "odoo",
                "address": {
                    "streetLines": streets,
                    "city": partner.city or "",
                    "stateOrProvinceCode": partner.state_id.code or "",
                    "postalCode": partner.zip or "",
                    "countryCode": partner.country_id.code or "",
                },
            }],
        }

    def _fedex_av_post(self, payload):
        """POST to the address validation endpoint, using the token already
        stored on the company. On 401, refresh the token once and retry."""
        self.ensure_one()
        company = self.company_id or self.env.company
        url = "%s/address/v1/addresses/resolve" % (company.fedex_api_url or '').rstrip('/')
        if not company.fedex_access_token:
            company.sudo().generate_fedex_access_token()
        resp = None
        for attempt in (1, 2):
            resp = requests.post(
                url, json=payload, timeout=30,
                headers={
                    'Authorization': 'Bearer %s' % company.fedex_access_token,
                    'Content-Type': 'application/json',
                    'X-locale': 'en_US',
                })
            if resp.status_code == 401 and attempt == 1:
                _logger.info("FedEx address validation: token rejected, refreshing it")
                company.sudo().generate_fedex_access_token()
                continue
            break
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Response parsing
    # status: ok | minor | review | invalid | unsupported
    # ------------------------------------------------------------------
    def _fedex_av_parse(self, partner, resolved):
        attrs = resolved.get('attributes') or {}

        def flag(key):
            return str(attrs.get(key, 'false')).lower() == 'true'

        def norm(value):
            return " ".join((value or "").upper().split())

        messages = [m.get('message') or m.get('code') or ''
                    for m in (resolved.get('customerMessages') or [])]
        result = {
            'status': 'ok',
            'valid': False,
            'classification': resolved.get('classification', 'UNKNOWN'),
            'messages': messages,
            'suggested': None,
            'changes': {},
        }

        # 1. Country not covered by FedEx validation: cannot judge
        if not flag('CountrySupported'):
            result.update(status='unsupported', valid=True)
            messages.append(_("FedEx cannot validate addresses in this country."))
            return result

        # 2. Not resolved: no suggestion, explain why
        if not flag('Resolved'):
            result['status'] = 'invalid'
            if not flag('ValidlyFormed'):
                messages.append(_("The street address is not in a valid format."))
            elif flag('CityStateValidated') and not flag('StreetValidated'):
                messages.append(_(
                    "City, state and ZIP are valid, but this street was not found there. "
                    "Check the street, city and ZIP for typos."))
            elif not flag('CityStateValidated'):
                messages.append(_("City, state or ZIP could not be validated."))
            return result

        # 3. Resolved but suite problems
        if flag('SuiteRequiredButMissing'):
            messages.append(_("Suite/Apt number is required."))
        if flag('InvalidSuiteNumber'):
            messages.append(_("Suite/Apt number is invalid."))
        if flag('SuiteRequiredButMissing') or flag('InvalidSuiteNumber'):
            result['status'] = 'invalid'
            return result

        # 4. Resolved: build the suggestion and detect what changed
        city_tok = (resolved.get('cityToken') or [{}])[0]
        state_tok = resolved.get('stateOrProvinceCodeToken') or {}
        zip_tok = resolved.get('postalCodeToken') or {}
        parsed_zip = resolved.get('parsedPostalCode') or {}
        lines = resolved.get('streetLinesToken') or []
        zip_val = zip_tok.get('value') or ''
        zip_base = parsed_zip.get('base') or zip_val[:5]

        orig_lines = [norm(x) for x in (partner.street, partner.street2) if x]
        new_lines = [norm(x) for x in lines]

        changes = {
            'street': orig_lines != new_lines,
            'city': bool(city_tok.get('changed')),
            'state': bool(state_tok.get('changed')),
            'zip_plus4': bool(zip_tok.get('changed')),
            'zip_major': norm(partner.zip)[:5] != norm(zip_base),
        }
        major = (changes['street'] or changes['city']
                 or changes['state'] or changes['zip_major'])

        result.update(
            valid=True,
            status='review' if major else ('minor' if changes['zip_plus4'] else 'ok'),
            changes=changes,
            suggested={
                'street': lines[0] if lines else '',
                'street2': lines[1] if len(lines) > 1 else '',
                'city': city_tok.get('value'),
                'state_code': resolved.get('stateOrProvinceCode'),
                'zip': zip_val,
                'country_code': resolved.get('countryCode'),
            } if (major or changes['zip_plus4']) else None,
        )
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fedex_validate_partner_address(self, partner, ref=None):
        """Parsed result of the first address plus 'candidates': a de-duplicated
        list of every usable corrected address FedEx returned."""
        self.ensure_one()
        try:
            data = self._fedex_av_post(self._fedex_av_build_payload(partner, ref or 'odoo'))
            resolved_list = (data.get('output') or {}).get('resolvedAddresses') or []
            if not resolved_list:
                raise ValueError("Empty FedEx response")

            results = [self._fedex_av_parse(partner, r) for r in resolved_list]

            # Current address is fine / country not covered: nothing to show
            for r in results:
                if r['status'] in ('ok', 'unsupported'):
                    r['candidates'] = []
                    return r

            main = results[0]
            seen, candidates = set(), []
            for r in results:
                s = r.get('suggested')
                if s and r['valid']:
                    key = (s['street'], s['street2'], s['city'], s['state_code'], s['zip'])
                    if key not in seen:
                        seen.add(key)
                        candidates.append(s)
            main['candidates'] = candidates
            return main
        except Exception as e:
            # A validation problem must never block the delivery
            _logger.exception("FedEx address validation failed")
            return {
                'status': 'error', 'valid': True, 'classification': 'UNKNOWN',
                'messages': [_("Address validation unavailable: %s", e)],
                'suggested': None, 'changes': {}, 'candidates': [],
            }

    def _fedex_apply_suggested_address(self, partner, s):
        country = self.env['res.country'].search(
            [('code', '=', s.get('country_code'))], limit=1)
        state = self.env['res.country.state'].search(
            [('code', '=', s.get('state_code')),
             ('country_id', '=', country.id)], limit=1)
        old = ", ".join(filter(None, [partner.street, partner.street2, partner.city,
                                      partner.state_id.code, partner.zip]))
        partner = partner.sudo()
        partner.write({
            'street': s.get('street'),
            'street2': s.get('street2') or False,
            'city': s.get('city'),
            'state_id': state.id or partner.state_id.id,
            'zip': s.get('zip'),
            'country_id': country.id or partner.country_id.id,
        })
        partner.message_post(
            body=_("Address updated from FedEx address validation. Old address: %s", old))
