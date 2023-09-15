from odoo import http, models, fields, api, _
from odoo.http import request
from odoo.addons.website.models.ir_http import sitemap_qs2dom
from odoo.osv.expression import FALSE_DOMAIN
import logging
logger = logging.getLogger(__name__)

class website(models.Model):
    _inherit = "website"

    def sale_product_domain(self):
        domain = [
            ("sale_ok", "=", True),
            '|',
            ('website_ids', 'in', (self.id)),
            ('website_ids', '=', False)]
        return domain

    def _enumerate_pages(self, query_string=None, force=False):
        """ Available pages in the website/CMS. This is mostly used for links
            generation and can be overridden by modules setting up new HTML
            controllers for dynamic pages (e.g. blog).
            By default, returns template views marked as pages.
            :param str query_string: a (user-provided) string, fetches pages
                                     matching the string
            :returns: a list of mappings with two keys: ``name`` is the displayable
                      name of the resource (page), ``url`` is the absolute URL
                      of the same.
            :rtype: list({name: str, url: str})
        """
        router = http.root.get_db_router(request.db)
        # Force enumeration to be performed as public user
        url_set = set()

        sitemap_endpoint_done = set()

        for rule in router.iter_rules():
            if 'sitemap' in rule.endpoint.routing and rule.endpoint.routing['sitemap'] is not True:
                print(rule.endpoint.routing)
                if rule.endpoint in sitemap_endpoint_done:
                    continue
                sitemap_endpoint_done.add(rule.endpoint)

                func = rule.endpoint.routing['sitemap']
                if func is False:
                    continue
                for loc in func(self.env, rule, query_string):
                    temp = True
                    try:
                        split_val = loc['loc'].split('-')
                        if len(split_val) > 1 and '/shop/category/' in split_val[:1][0]:
                            # ,'|',('website_ids','=',False),('website_ids','in',self.id)
                            ecateg = self.env['product.public.category'].search([('id','=',int(split_val[len(split_val)-1:][0]))])
                            print(ecateg.name)
                            ecateg
                            while ecateg:
                                if ecateg.website_ids:
                                    if self in ecateg.website_ids:
                                        ecateg = False
                                    else:
                                        temp = ecateg = False
                                else:
                                    ecateg = ecateg.parent_id
                            # if ecateg:
                            #     temp = False
                    except:
                        pass
                    if temp:
                        yield loc
                continue

            if not self.rule_is_enumerable(rule):
                continue

            if 'sitemap' not in rule.endpoint.routing:
                logger.warning('No Sitemap value provided for controller %s (%s)' %
                               (rule.endpoint.method, ','.join(rule.endpoint.routing['routes'])))

            converters = rule._converters or {}
            if query_string and not converters and (query_string not in rule.build({}, append_unknown=False)[1]):
                continue

            values = [{}]
            # converters with a domain are processed after the other ones
            convitems = sorted(
                converters.items(),
                key=lambda x: (hasattr(x[1], 'domain') and (x[1].domain != '[]'), rule._trace.index((True, x[0]))))

            for (i, (name, converter)) in enumerate(convitems):
                if 'website_ids' in self.env[converter.model]._fields and (not converter.domain or converter.domain == '[]'):
                    converter.domain = "[('website_ids', 'in', (False, current_website_id))]"
                elif 'website_id' in self.env[converter.model]._fields and (not converter.domain or converter.domain == '[]'):
                    converter.domain = "[('website_id', 'in', (False, current_website_id))]"

                newval = []
                for val in values:
                    query = i == len(convitems) - 1 and query_string
                    if query:
                        r = "".join([x[1] for x in rule._trace[1:] if not x[0]])  # remove model converter from route
                        query = sitemap_qs2dom(query, r, self.env[converter.model]._rec_name)
                        if query == FALSE_DOMAIN:
                            continue

                    for rec in converter.generate(uid=self.env.uid, dom=query, args=val):
                        newval.append(val.copy())
                        newval[-1].update({name: rec})
                values = newval

            for value in values:
                domain_part, url = rule.build(value, append_unknown=False)
                if not query_string or query_string.lower() in url.lower():
                    page = {'loc': url}
                    if url in url_set:
                        continue
                    url_set.add(url)

                    yield page

        # '/' already has a http.route & is in the routing_map so it will already have an entry in the xml
        domain = [('url', '!=', '/')]
        if not force:
            domain += [('website_indexed', '=', True), ('visibility', '=', False)]
            # is_visible
            domain += [
                ('website_published', '=', True), ('visibility', '=', False),
                '|', ('date_publish', '=', False), ('date_publish', '<=', fields.Datetime.now())
            ]

        if query_string:
            domain += [('url', 'like', query_string)]

        pages = self._get_website_pages(domain)

        for page in pages:
            record = {'loc': page['url'], 'id': page['id'], 'name': page['name']}
            if page.view_id and page.view_id.priority != 16:
                record['priority'] = min(round(page.view_id.priority / 32.0, 1), 1)
            if page['write_date']:
                record['lastmod'] = page['write_date'].date()
            yield record