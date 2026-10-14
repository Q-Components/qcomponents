import logging
import re

import requests

from odoo import fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Common USPS-style abbreviations. UPS returns the standardized form
# (ROAD -> RD), so both sides are normalised with this map before comparing,
# otherwise every abbreviation would be reported as a real change.
_ABBREVIATIONS = {
    'ROAD': 'RD', 'STREET': 'ST', 'AVENUE': 'AVE', 'BOULEVARD': 'BLVD',
    'DRIVE': 'DR', 'LANE': 'LN', 'COURT': 'CT', 'PLACE': 'PL',
    'CIRCLE': 'CIR', 'HIGHWAY': 'HWY', 'PARKWAY': 'PKWY', 'TERRACE': 'TER',
    'TRAIL': 'TRL', 'SQUARE': 'SQ', 'SUITE': 'STE', 'APARTMENT': 'APT',
    'FLOOR': 'FL', 'BUILDING': 'BLDG', 'NORTH': 'N', 'SOUTH': 'S',
    'EAST': 'E', 'WEST': 'W', 'NORTHEAST': 'NE', 'NORTHWEST': 'NW',
    'SOUTHEAST': 'SE', 'SOUTHWEST': 'SW',
}


def _norm(value):
    return " ".join((value or "").upper().split())


def _norm_street(value):
    """Upper-case, strip punctuation, unify abbreviations."""
    words = re.sub(r'[^A-Z0-9 ]', ' ', (value or '').upper()).split()
    return " ".join(_ABBREVIATIONS.get(w, w) for w in words)


def _as_list(value):
    if value in (None, ''):
        return []
    return value if isinstance(value, list) else [value]


class UpsAddressValidationError(Exception):
    """UPS (or the connection to it) returned an error. The message is meant
    to be shown to the user in the address wizard."""


class DeliveryCarrierUpsAddressValidation(models.Model):
    """UPS Address Validation (XAV) API support."""
    _inherit = "delivery.carrier"

    ups_validate_address = fields.Boolean(
        string="Validate Address with UPS", copy=False,
        help="When validating a delivery order, check the delivery address with the "
             "UPS Address Validation API before the shipment is created.")
    ups_auto_correct_address = fields.Boolean(
        string="Auto-apply minor corrections", copy=False,
        help="If UPS only changes the ZIP+4 or standard abbreviations (ROAD -> RD), "
             "update the customer's address silently instead of opening the wizard.")
    ups_av_max_candidates = fields.Integer(
        string="Max Suggestions", default=5, copy=False,
        help="Maximum number of suggested addresses requested from UPS (1-15).")

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------
    def _ups_av_build_payload(self, partner):
        zip_code = (partner.zip or '').strip()
        digits = re.sub(r'\D', '', zip_code)
        primary, extended = zip_code, ''
        if partner.country_id.code in ('US', 'PR') and len(digits) == 9:
            primary, extended = digits[:5], digits[5:]
        elif '-' in zip_code:
            primary, extended = [p.strip() for p in zip_code.split('-', 1)]
        key = {
            "ConsigneeName": (partner.name or '')[:35],
            "AddressLine": [s[:35] for s in (partner.street, partner.street2) if s],
            "PoliticalDivision2": partner.city or '',
            "PoliticalDivision1": partner.state_id.code or '',
            "PostcodePrimaryLow": primary,
            "CountryCode": partner.country_id.code or '',
        }
        if extended:
            key["PostcodeExtendedLow"] = extended
        return {"XAVRequest": {"AddressKeyFormat": key}}

    @staticmethod
    def _ups_av_errors_from_json(data):
        """UPS REST errors look like {"response": {"errors": [{"code", "message"}]}};
        older SOAP-style faults are handled as a fallback."""
        errors = []
        if not isinstance(data, dict):
            return errors
        node = data.get('response') if isinstance(data.get('response'), dict) else data
        for err in _as_list(node.get('errors')):
            if isinstance(err, dict):
                msg = err.get('message') or err.get('description') or ''
                code = err.get('code')
                errors.append("%s (code %s)" % (msg, code) if code else msg)
        if not errors:
            try:
                detail = data['Fault']['detail']['Errors']['ErrorDetail']
                for err in _as_list(detail):
                    prim = err.get('PrimaryErrorCode') or {}
                    errors.append("%s (code %s)" % (prim.get('Description'), prim.get('Code')))
            except (KeyError, TypeError, AttributeError):
                pass
        return [e for e in errors if e]

    def _ups_av_post(self, payload):
        """POST to UPS XAV. On 401 refresh the token once and retry.
        Raises UpsAddressValidationError with a readable message on any failure."""
        self.ensure_one()
        company = self.company_id or self.env.company
        size = min(max(self.ups_av_max_candidates or 10, 1), 15)
        # request option 1 = address validation
        url = "%s/api/addressvalidation/v2/1?maximumcandidatelistsize=%s" % (
            (company.ups_api_url or '').rstrip('/'), size)
        resp = None
        try:
            if not company.ups_api_token:
                company.sudo().ups_generate_token()
            for attempt in (1, 2):
                resp = requests.post(
                    url, json=payload, timeout=30,
                    headers={
                        'Authorization': 'Bearer %s' % company.ups_api_token,
                        'Content-Type': 'application/json',
                        'transId': 'odoo-av',
                        'transactionSrc': 'odoo',
                    })
                if resp.status_code == 401 and attempt == 1:
                    _logger.info("UPS address validation: token rejected, refreshing it")
                    company.sudo().ups_generate_token()
                    continue
                break
        except requests.RequestException as e:
            raise UpsAddressValidationError(_("Could not reach UPS: %s", e)) from e
        except ValidationError as e:
            raise UpsAddressValidationError(_("Could not get a UPS access token: %s", e)) from e

        _logger.info("UPS address validation response: %s", resp.text)
        try:
            data = resp.json()
        except ValueError:
            data = None
        if not resp.ok:
            errors = self._ups_av_errors_from_json(data)
            raise UpsAddressValidationError(_(
                "UPS returned an error: %s",
                "; ".join(errors) or "HTTP %s %s" % (resp.status_code, (resp.text or '')[:200])))
        if not isinstance(data, dict):
            raise UpsAddressValidationError(_("UPS returned an unreadable response."))
        return data

    # ------------------------------------------------------------------
    # Response parsing
    # status: ok | minor | review | invalid | unsupported | error
    # ------------------------------------------------------------------
    @staticmethod
    def _ups_av_candidate_to_dict(cand):
        key = cand.get('AddressKeyFormat') or {}
        lines = [str(x) for x in _as_list(key.get('AddressLine'))]
        zip_main = key.get('PostcodePrimaryLow') or ''
        zip_ext = key.get('PostcodeExtendedLow') or ''
        return {
            'street': lines[0] if lines else '',
            'street2': lines[1] if len(lines) > 1 else '',
            'city': key.get('PoliticalDivision2') or '',
            'state_code': key.get('PoliticalDivision1') or '',
            'zip': "%s-%s" % (zip_main, zip_ext) if zip_ext else zip_main,
            'country_code': key.get('CountryCode') or '',
            'classification': (cand.get('AddressClassification') or {}).get('Description') or '',
        }

    def _ups_av_diff(self, partner, s):
        orig_street = _norm_street(" ".join(filter(None, [partner.street, partner.street2])))
        new_street = _norm_street(" ".join(filter(None, [s['street'], s['street2']])))
        orig_raw = _norm(" ".join(filter(None, [partner.street, partner.street2])))
        new_raw = _norm(" ".join(filter(None, [s['street'], s['street2']])))
        orig_zip = re.sub(r'\D', '', partner.zip or '')
        new_zip = re.sub(r'\D', '', s['zip'] or '')
        return {
            'street': orig_street != new_street,
            'street_abbr': orig_street == new_street and orig_raw != new_raw,
            'city': _norm(partner.city) != _norm(s['city']),
            'state': _norm(partner.state_id.code) != _norm(s['state_code']),
            'zip_major': orig_zip[:5] != new_zip[:5],
            'zip_plus4': orig_zip[:5] == new_zip[:5] and orig_zip != new_zip,
        }

    def _ups_av_parse(self, partner, data):
        resp = data.get('XAVResponse') or {}
        messages = []
        result = {
            'status': 'ok', 'valid': False,
            'classification': (resp.get('AddressClassification') or {}).get('Description') or 'Unknown',
            'messages': messages, 'suggested': None, 'changes': {}, 'candidates': [],
        }

        candidates = [self._ups_av_candidate_to_dict(c) for c in _as_list(resp.get('Candidate'))]

        if 'NoCandidatesIndicator' in resp or not candidates:
            result['status'] = 'invalid'
            zip_code = (partner.zip or '').strip()
            checked = ", ".join(filter(None, [
                partner.street, partner.street2, partner.city,
                " ".join(filter(None, [partner.state_id.code, zip_code]))]))
            messages.append(_("UPS found no matching address for: %s", checked))
            if (partner.country_id.code == 'US'
                    and not re.match(r'^\d{5}(-?\d{4})?$', zip_code)):
                messages.append(_(
                    "ZIP code '%s' is not a valid US ZIP code (5 digits, optionally +4).",
                    zip_code or '-'))
            company = self.company_id or self.env.company
            if ('wwwcie' in (company.ups_api_url or '')
                    and partner.state_id.code not in ('CA', 'NY')):
                # UPS test environment (CIE) only returns results for CA and NY
                messages.append(_(
                    "You are connected to the UPS test environment (wwwcie.ups.com), "
                    "which only validates addresses in California (CA) and New York (NY). "
                    "Other states are validated only with the production UPS API URL."))
            else:
                messages.append(_(
                    "Check the street, city, state and ZIP. "
                    "A wrong state or ZIP is the most common cause."))
            return result

        # Pick the closest candidate to decide the overall status
        diffs = [self._ups_av_diff(partner, c) for c in candidates]

        def severity(d):
            if d['street'] or d['city'] or d['state'] or d['zip_major']:
                return 2
            return 1 if (d['street_abbr'] or d['zip_plus4']) else 0

        levels = [severity(d) for d in diffs]
        best = min(levels)
        if best == 0:
            result.update(status='ok', valid=True)
            return result

        if 'AmbiguousAddressIndicator' in resp:
            messages.append(_("The address is ambiguous. Please choose the correct one."))
        result.update(
            valid=True,
            status='minor' if best == 1 else 'review',
            candidates=candidates,
            suggested=candidates[levels.index(best)],
            changes=diffs[levels.index(best)],
        )
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @staticmethod
    def _ups_av_error_result(message):
        return {
            'status': 'error', 'valid': True, 'classification': 'Unknown',
            'messages': [message], 'suggested': None, 'changes': {}, 'candidates': [],
        }

    def ups_validate_partner_address(self, partner):
        """Never raises: any problem is returned as status 'error' with a message
        that the wizard shows, and the user can still continue."""
        self.ensure_one()
        try:
            data = self._ups_av_post(self._ups_av_build_payload(partner))
            xav = data.get('XAVResponse')
            if not isinstance(xav, dict):
                errors = self._ups_av_errors_from_json(data)
                raise UpsAddressValidationError(_(
                    "UPS returned an error: %s", "; ".join(errors) or str(data)[:200]))
            status = (xav.get('Response') or {}).get('ResponseStatus') or {}
            if status.get('Code') not in (None, '1'):
                raise UpsAddressValidationError(_(
                    "UPS returned an error: %s", status.get('Description') or status.get('Code')))
            return self._ups_av_parse(partner, data)
        except UpsAddressValidationError as e:
            _logger.warning("UPS address validation error: %s", e)
            return self._ups_av_error_result(str(e))
        except Exception as e:
            _logger.exception("UPS address validation failed")
            return self._ups_av_error_result(_("Address validation unavailable: %s", e))

    def _ups_apply_suggested_address(self, partner, s):
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
            body=_("Address updated from UPS address validation. Old address: %s", old))
