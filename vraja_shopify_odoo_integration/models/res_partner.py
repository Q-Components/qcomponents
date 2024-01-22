from odoo import models, fields


class SalesOrder(models.Model):
    _inherit = 'res.partner'

    shopify_customer_id = fields.Char(string="Shopify Customer ID",
                                      help="This is just a reference of shopify customer identifier", tracking=True)
    shopify_instance_id = fields.Many2one('shopify.instance.integration', string="Shopify Instance",
                                          help="This field show the instance details of shopify", tracking=True)
    shopify_address_id = fields.Char(string="Shopify Address ID", copy=False,
                                     help="This ID consider as a Shopify Customer Address ID", tracking=True)

    def create_child_customer(self, instance_id, customer_datas, customer_id):
        """This method was used if in customer response there are multiple address then we will create child customer
        address using this method
        @param : instance_id : Object of instance
                 customer_datas : json response of customer data
                 customer_id : object of main customer which is created in previous method
        """

        for address_data in customer_datas.get('addresses'):
            if not address_data.get('default'):
                country_id = self.env['res.country'].search([('name', '=', address_data.get('country'))])
                state_id = self.env['res.country.state'].search([('name', '=', address_data.get('province'))])
                customer_vals = {
                    'name': customer_id.name or '',
                    'street': address_data.get('address1', ''),
                    'street2': address_data.get('address2', ''),
                    'city': address_data.get('city', ''),
                    'zip': address_data.get('zip', ''),
                    'country_id': country_id and country_id.id or '',
                    'state_id': state_id and state_id.id or '',
                    'parent_id': customer_id.id,
                    'type': 'other',
                    'shopify_address_id': address_data.get('id', ''),
                    'shopify_instance_id': instance_id.id
                }
                existing_customer = self.env['res.partner'].search(
                    [('shopify_address_id', '=', address_data.get('id', ''))],
                    limit=1)
                if existing_customer:
                    existing_customer.write(customer_vals)
                else:
                    customer_id = self.env["res.partner"].create(customer_vals)
        return True

    def create_update_customer_shopify_to_odoo(self, instance_id, customer_line=False, so_customer_data=False,
                                               log_id=False):
        """This method used for create and update customer from shopify to odoo
           @param instance_id : object of instance,
                customer_line : object of customer queue line
                customer_data : json response of specific customer data
                so_customer_data : json response of customer data from sale order level
                log_id : object of log_id for create log line
           @Return : Updated or Created Customer ID / Customer Object
        """
        partner_obj = self.env["res.partner"]
        customer_data = customer_line and eval(customer_line.customer_data_to_process)
        customer_datas = so_customer_data or customer_data
        shopify_customer_id = customer_datas.get('id')

        customer_vals = {'name': "{0} {1}".format(customer_datas.get('first_name', '') or '',
                                                  customer_datas.get('last_name', '') or ''),
                         'shopify_customer_id': shopify_customer_id,
                         'email': customer_datas.get('email') or '',
                         'phone': customer_datas.get('phone') or '',
                         'shopify_instance_id': instance_id.id}

        for address_data in customer_datas.get('addresses'):
            if address_data.get('default'):
                country_id = self.env['res.country'].search([('name', '=', address_data.get('country'))])
                state_id = self.env['res.country.state'].search([('name', '=', address_data.get('province'))])
                customer_vals.update({
                    'street': address_data.get('address1', ''),
                    'street2': address_data.get('address2', ''),
                    'city': address_data.get('city', ''),
                    'zip': address_data.get('zip', ''),
                    'country_id': country_id and country_id.id or '',
                    'state_id': state_id and state_id.id or '',
                    'shopify_address_id': address_data.get('id', '')
                })
        existing_customer = self.env['res.partner'].search([('shopify_customer_id', '=', shopify_customer_id)],
                                                           limit=1)

        if existing_customer:
            existing_customer.write(customer_vals)
            customer_id = existing_customer
            customer_line.state = 'completed'
            msg = "Customer {0} Updated Successfully".format(customer_line.name)
            self.env['shopify.log.line'].generate_shopify_process_line('customer', 'import', instance_id,
                                                                       msg,
                                                                       False, customer_data, log_id,
                                                                       False)
        else:
            customer_id = partner_obj.create(customer_vals)
            customer_line.state = 'completed'
            msg = "Customer {0} Created Successfully".format(customer_line.name)
            self.env['shopify.log.line'].generate_shopify_process_line('customer', 'import', instance_id,
                                                                       msg,
                                                                       False, customer_data, log_id,
                                                                       False)
        self.create_child_customer(instance_id, customer_datas,
                                   customer_id)  # this method used for create child customer
        customer_line.res_partner_id = customer_id.id
        self._cr.commit()
        return customer_id
