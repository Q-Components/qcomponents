# -*- coding: utf-8 -*-

import json
import logging
from odoo import http

_logger = logging.getLogger(__name__)


class WebHook(http.Controller):

    @http.route('/update/bigcommerce/quantity', type='json', auth="none", methods=['POST'])
    def update_bigcommerce_quantity_webhook(self, **kw):
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n Hello calling >>>>>>>%s'%(kw))
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n new >>>>>>>%s %s'%(http.request.httprequest.args, dir(http.request.httprequest)))
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n data >>>>>>>%s'%(http.request.httprequest.data))
        _logger.warning('>>>>>>>>>>>>>>> \n \n \n values >>>>>>>%s'%(http.request.httprequest.values))
        
        # return json.dumps([])
