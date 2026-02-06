# location_checker/controllers/main.py

from odoo import http
from odoo.http import request
import logging
import json

_logger = logging.getLogger(__name__)

class LocationCheckerController(http.Controller):
    @http.route('/get_user_location', type='json', auth='public')
    def get_user_location(self, **kwargs):
        """
        Endpoint to validate user's location against restricted countries and states.
        
        :param kwargs: Dictionary containing 'country' and 'region' from the user's data.
        :return: JSON response indicating if the user's location is restricted and a custom message.
        """
        try:
            # Fetch not allowed countries and states from system configuration
            config_params = request.env['ir.config_parameter'].sudo()
            not_allowed_country_ids = config_params.get_param(
                'geoportal_access_control.not_allowed_country_ids', default='[]'
            )
            not_allowed_state_ids = config_params.get_param(
                'geoportal_access_control.not_allowed_state_ids', default='[]'
            )
            custom_msg = config_params.get_param(
                'geoportal_access_control.custom_msg', 
                default='This site is not available in your region.'
            )

            # Convert string IDs to actual country codes and state names
            not_allowed_country_codes = request.env['res.country'].sudo().search([
                ('id', 'in', eval(not_allowed_country_ids))
            ]).mapped('code')

            not_allowed_state_names = request.env['res.country.state'].sudo().search([
                ('id', 'in', eval(not_allowed_state_ids))
            ]).mapped('name')

            # Check if the user's country or region is restricted
            user_country = kwargs.get('country')
            user_region = kwargs.get('region')
            not_allowed = (user_country in not_allowed_country_codes or user_region in not_allowed_state_names) and not request.env.user._is_internal()

            # Logging for debugging purposes
            _logger.debug('Restricted country codes: %s', not_allowed_country_codes)
            _logger.debug('Restricted state names: %s', not_allowed_state_names)
            _logger.debug('User country: %s, User region: %s, Access restricted: %s', 
                          user_country, user_region, not_allowed)

            # Return the restriction status along with the custom message
            return json.dumps({
                'not_allowed': not_allowed,
                'custom_msg': custom_msg
            })

        except Exception as e:
            # Handle unexpected errors gracefully and log them
            _logger.error('Unexpected error: %s', e)
            return json.dumps({'error': 'An unexpected error occurred while checking your location.'})
