# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import Warning
from odoo import models, fields, exceptions, api, _
import io
import tempfile
import binascii
import urllib.request
import logging
_logger = logging.getLogger(__name__)

try:
    import csv
except ImportError:
    _logger.debug('Cannot `import csv`.')
try:
    import xlwt
except ImportError:
    _logger.debug('Cannot `import xlwt`.')
try:
    import base64
except ImportError:
    _logger.debug('Cannot `import base64`.')
# for xls 
try:
    import xlrd
except ImportError:
    _logger.debug('Cannot `import xlrd`.')


class gen_inv_2(models.Model):
    _name = "generate.inv"

    product_counter_main = fields.Integer("Counter")

    @api.model
    def default_get(self, fields):
        res = super(gen_inv_2, self).default_get(fields)
        inv_id = self.env['generate.inv'].sudo().search([],order="id desc",limit=1)
        if inv_id:
            res.update({
                'product_counter_main' : inv_id.product_counter_main
                })
        else:
            res.update({
                'product_counter_main' : ''
                })
        return res


def is_integer(n):
    try:
        float(n)
    except ValueError:
        return False
    else:
        return float(n).is_integer()


class gen_inv(models.TransientModel):
    _name = "gen.inv"

    file = fields.Binary('File')
    inv_name = fields.Char('Inventory Name')
    location_ids = fields.Many2many('stock.location','rel_location_wizard',string= "Location")
    import_option = fields.Selection([('csv', 'CSV File'),('xls', 'XLS File')],string='Select',default='csv')
    import_prod_option = fields.Selection([('barcode', 'Barcode'),('code', 'Code'),('name', 'Name')],string='Import Product By ',default='code')
    location_id_option = fields.Boolean(string="Allow to Import Location on inventory line from file")
    is_validate_inventory = fields.Boolean(string="Validate Inventory")


    def pre_process_url(self, raw_url):
        if ' ' not in raw_url[-1]:
            raw_url = raw_url.replace(' ', '%20')
            return raw_url
        elif ' ' in raw_url[-1]:
            raw_url = raw_url[:-1]
            raw_url = raw_url.replace(' ', '%20')
            return raw_url

    def import_csv(self):

        stock_line_obj = self.env['stock.inventory.line']
        product_obj = self.env['product.product']
        inventory_obj = self.env['stock.inventory']
        location_obj = self.env['stock.location']
        category_obj = self.env['product.category']
        attachment_obj = self.env['ir.attachment']
        stock_lot_obj = self.env['stock.production.lot']

        """Load Inventory data from the CSV file."""
        if self.import_option == 'csv':            
            data = base64.b64decode(self.file)
            try:
                file_input = io.StringIO(data.decode("utf-8"))
            except UnicodeError:
                raise Warning('Invalid CSV file!')

            ctx = self._context
            keys=['name', 'x_studio_alternate_number','x_studio_manufacturer',
            'x_studio_date_code_1', 'product_qty','location_id',
            'parent_location_id', 'x_studio_origin_code','x_studio_condition_1',
            'x_studio_package', 'description_sale','categ_id',
            'x_studio_country_of_origin', 'type','x_studio_manufacturer',
            'x_studio_category', 'list_price','barcode',
            'x_studio_rohs', 'standard_price','image_1920',
            'file_1', 'file_2','website_published','lot']

            stloc_obj = self.env['stock.location']
            inventory_obj = self.env['stock.inventory']
            product_obj = self.env['product.product']
            stock_line_obj = self.env['stock.inventory.line']
            stock_lot_obj = self.env['stock.production.lot']
            csv_data = base64.b64decode(self.file)
            data_file = io.StringIO(csv_data.decode("utf-8"))
            data_file.seek(0)
            file_reader = []
            csv_reader = csv.reader(data_file, delimiter=',')
            flag = 0

            generate_inv = self.env['generate.inv']
            counter_product = 0.0

            try:
                file_reader.extend(csv_reader)
            except Exception:
                raise exceptions.Warning(_("Invalid CSV file!"))

            values = {}
            inventory_id = inventory_obj.create({
                'name':self.inv_name,
                'prefill_counted_quantity' : 'counted'
            })
            inventory_id.action_start()
            
            for i in range(len(file_reader)):
                if i!= 0:
                    val = {}
                    try:
                        field = list(map(str, file_reader[i]))
                    except ValueError:
                        raise exceptions.Warning(_("Don't Use Character only, Use numbers too..!!"))
                    
                    values = dict(zip(keys, field))

                    if len(values) != 0:
                        product_id = product_obj.search([('name','=',values.get('name'))],limit=1)

                        product_values = {}

                        product_values.update({
                            'name' : str(values.get('name')),
                            'x_studio_alternate_number' : str(values.get('x_studio_alternate_number')),
                            'x_studio_manufacturer' : str(values.get('x_studio_manufacturer')), 
                            'x_studio_date_code_1' : str(values.get('x_studio_date_code_1')),
                            'x_studio_origin_code' : str(values.get('x_studio_origin_code')),
                            'x_studio_condition_1' : str(values.get('x_studio_condition_1')), 
                            'x_studio_package' : str(values.get('x_studio_package')),
                            'description_sale' : str(values.get('description_sale')), 
                            'description' : str(values.get('description')),
                            'x_studio_country_of_origin' : str(values.get('x_studio_country_of_origin')),
                            'type' : str(values.get('type')) or 'product',
                            'x_studio_category' : str(values.get('x_studio_category')), 
                            'list_price' : values.get('list_price') or 0.00, 
                            'barcode' : str(values.get('barcode')),
                            'x_studio_rohs' : str(values.get('x_studio_rohs')), 
                            'standard_price' : values.get('standard_price') or 0.00,
                            'website_published' : True
                        })

                        if values.get('image_1920') != '':
                            try:
                                imgurl_1 = values.get('image_1920')
                                imgurl_1 = self.pre_process_url(imgurl_1)
                                try:
                                    f1 = base64.encodestring(urllib.request.urlopen(urllib.request.Request(imgurl_1, None, headers={'User-Agent': 'Mozilla/5.0'})).read())
                                except ValueError:
                                    raise Warning(_('Invalid Image URL'))
                            except ValueError:  # invalid URL
                                with open(values.get('image_1920'), "rb") as image_file:
                                    f1 = base64.b64encode(image_file.read())
                        else:
                            f1 = False

                        if values.get('file_1') != '':
                            try:
                                imgurl_2 = values.get('file_1')
                                imgurl_2 = self.pre_process_url(imgurl_2)
                                try:    
                                    f2 = base64.encodestring(urllib.request.urlopen(urllib.request.Request(imgurl_2, None, headers={'User-Agent': 'Mozilla/5.0'})).read())
                                except ValueError:
                                    raise Warning(_('Invalid Image URL'))
                            except ValueError:  # invalid URL
                                with open(values.get('file_1'), "rb") as image_file:
                                    f2 = base64.b64encode(image_file.read())
                        else:
                            f2 = False

                        if values.get('file_2') != '':
                            try:
                                imgurl_3 = values.get('file_2')
                                imgurl_3 = self.pre_process_url(imgurl_3)
                                try:
                                    f3 = base64.encodestring(urllib.request.urlopen(urllib.request.Request(imgurl_3, None, headers={'User-Agent': 'Mozilla/5.0'})).read())
                                except ValueError:
                                    raise Warning(_('Invalid Image URL'))
                            except ValueError:  # invalid URL
                                with open(values.get('file_2'), "rb") as image_file:
                                    f3 = base64.b64encode(image_file.read())
                        else:
                            f3 = False

                        if f1:
                            product_values.update({
                                'image_1920' : f1
                            })

                        categ_id = False
                        location_id = False
                        parent_location_id = False
                        if values.get('categ_id'):
                            categ_id = category_obj.search([('name','=',values.get('categ_id'))],limit=1)
                            if categ_id:
                                product_values.update({
                                    'categ_id' : categ_id.id
                                })

                        if not product_id:
                            product_id = product_obj.create(product_values)
                        else:
                            # if product found
                            product_id = product_id
                            product_id.write(product_values)

                        attachment_list = []

                        if f2:
                            file_name = values.get('file_1').split('/')[-1:]
                            prod_temp_id_bi = product_id.product_tmpl_id.id
                            vals = {
                                'product_tmpl_id':prod_temp_id_bi,
                                'name':file_name,
                                'image_1920':f2
                            }
                            record = self.env['product.image'].create(vals)


                        if f3:
                            file_name = values.get('file_2').split('/')[-1:]
                            prod_temp_id_bi = product_id.product_tmpl_id.id
                            vals = {
                                'product_tmpl_id' : prod_temp_id_bi,
                                'name' : file_name,
                                'image_1920' : f3
                            }
                            record = self.env['product.image'].create(vals)

                        # Inventory Valuation
                        if values.get('location_id'):
                            if is_integer(values.get('location_id')):
                                location = values.get('location_id').split('.')
                                location_name = str(location[0])
                            else:
                                location_name = values.get('location_id')

                            if location_name.isnumeric():
                                location_name = str(location_name)
                            else:
                                location_name = str(values.get('location_id'))

                            location_id = location_obj.search([('name','=',location_name)])

                            if not location_id:
                                raise Warning(_('\'{}\' Location is not available.'.format(location_name)))

                        main_parent_loc = location_obj.search([('name','=','ELP')],limit=1)

                        if not main_parent_loc:
                            raise Warning(_('\'ELP\' Location is not available.'))

                        if values.get('parent_location_id'):
                            if is_integer(values.get('parent_location_id')):
                                parent_location = values.get('parent_location_id').split('.')
                                parent_location_name = str(location[0])
                            else:
                                parent_location_name = values.get('parent_location_id')
                            
                            if parent_location_name.isnumeric():
                                parent_location_name = str(parent_location_name)
                            else:
                                parent_location_name = str(values.get('parent_location_id'))

                            parent_location_id = location_obj.search([('name','=',parent_location_name),('location_id','=',main_parent_loc.id)])

                            if not parent_location_id:
                                raise Warning(_('\'{}\' Parent Location is not available.'.format(parent_location_name)))

                        if product_id:
                            product_uom_id= product_id.uom_id

                            lot_id = False

                            if values.get('lot'):
                                lot_id = stock_lot_obj.search([
                                    ('product_id','=',product_id.id),
                                    ('name','=',values.get('lot'))
                                ])

                                if not lot_id:
                                    lot = stock_lot_obj.create({
                                        'name': values.get('lot'),
                                        'product_id': product_id.id,
                                        # 'life_date': date_string,
                                        'company_id' : self.env.user.company_id.id
                                    })
                                    lot_id = lot

                            if lot_id:
                                lot_id = lot_id.id
                                product_id.write({
                                    'tracking' : 'lot'
                                    })

                            

                            inventory_id.write({'product_ids' :[(4,product_id.id)] })
                            search_line = self.env['stock.inventory.line'].search([
                                ('product_id','=',product_id.id),
                                ('inventory_id','=',inventory_id.id),
                                ('location_id','=',location_id.id)
                            ])

                            if search_line:
                                for inventory_line in search_line :
                                    inventory_line.write({
                                        'product_qty' : values.get('product_qty') or 0.0,
                                        'prod_lot_id':lot_id
                                    })
                            else:
                                stock_line_id = self.env['stock.inventory.line'].create({
                                    'product_id' : product_id.id,
                                    'inventory_id' : inventory_id.id,
                                    'location_id' : location_id.id,
                                    'product_uom_id' : product_uom_id.id ,
                                    'product_qty': values.get('product_qty') or 0.0,
                                    'prod_lot_id':lot_id
                                })

                                stock_line_id._onchange_quantity_context()

                            flag =1
                            counter_product += 1
                        else:
                            raise Warning(_('Something Went Wrong. !!!!'))

            g_inv_id = generate_inv.sudo().create({
                'product_counter_main' : int(counter_product)
            })

            if self.is_validate_inventory == True:
                inventory_id.action_validate()

            if flag ==1:
                return  {
                        'name': _('Success'),
                        'view_type': 'form',
                        'view_mode': 'form',
                        'res_model': 'generate.inv',
                        'view_id': self.env.ref('import_inventory.success_import_wizard').id,
                        'type': 'ir.actions.act_window',
                        'target': 'new'
                        }
            else:
                return True 

        else:

            fp = tempfile.NamedTemporaryFile(delete= False,suffix=".xlsx")
            fp.write(binascii.a2b_base64(self.file))
            fp.seek(0)

            values = {}

            workbook = xlrd.open_workbook(fp.name)
            sheet = workbook.sheet_by_index(0)

            inventory_id = inventory_obj.create({
                'name':self.inv_name,
                'prefill_counted_quantity' : 'counted',
            })

            inventory_id.action_start()

            flag = 0
            generate_inv = self.env['generate.inv']
            counter_product = 0.0

            for row_no in range(sheet.nrows):
                val = {}
                if row_no <= 0:
                    fields = map(lambda row:row.value.encode('utf-8'), \
                        sheet.row(row_no))
                else:
                    line = list(map(lambda row:isinstance(row.value, bytes) \
                        and row.value.encode('utf-8') \
                        or str(row.value), sheet.row(row_no)))

                    if line:
                        values.update({
                            'name' : line[0], 
                            'x_studio_alternate_number' : line[1],
                            'x_studio_manufacturer' : line[2], 
                            'x_studio_date_code_1' : line[3],
                            'product_qty' : line[4], 'location_id' : line[5],
                            'parent_location_id' : line[6], 
                            'x_studio_origin_code' : line[7],
                            'x_studio_condition_1' : line[8], 
                            'x_studio_package' : line[9],
                            'description_sale' : line[10], 
                            'description' : line[11],
                            'x_studio_country_of_origin' : line[12], 
                            'type' : line[13],
                            'categ_id' : line[14], 
                            'x_studio_category' : line[15],
                            'list_price' : line[16], 
                            'barcode' : line[17],
                            'x_studio_rohs' : line[18], 
                            'standard_price' : line[19],
                            'image_1920' : line[20], 'file_1' : line[21],
                            'file_2' : line[22], 
                            'website_published': line[23],
                            'lot' : line[24],
                        })

                        product_id = product_obj.search([('name','=',values.get('name'))],limit=1)


                        product_values = {}
                        product_values.update({
                            'name' : str(values.get('name')),
                            'x_studio_alternate_number' : str(values.get('x_studio_alternate_number')),
                            'x_studio_manufacturer' : str(values.get('x_studio_manufacturer')), 
                            'x_studio_date_code_1' : str(values.get('x_studio_date_code_1')),
                            'x_studio_origin_code' : str(values.get('x_studio_origin_code')),
                            'x_studio_condition_1' : str(values.get('x_studio_condition_1')), 
                            'x_studio_package' : str(values.get('x_studio_package')),
                            'description_sale' : str(values.get('description_sale')), 
                            'description' : str(values.get('description')),
                            'x_studio_country_of_origin' : str(values.get('x_studio_country_of_origin')),
                            'type' : str(values.get('type')) or 'product',
                            'x_studio_category' : str(values.get('x_studio_category')), 
                            'list_price' : values.get('list_price') or 0.00, 
                            'barcode' : str(values.get('barcode')),
                            'x_studio_rohs' : str(values.get('x_studio_rohs')), 
                            'standard_price' : values.get('standard_price') or 0.00,
                            'website_published' : True,
                        })

                        
                        if values.get('image_1920') != '':
                            try:
                                imgurl_1 = values.get('image_1920')
                                imgurl_1 = self.pre_process_url(imgurl_1)
                                try:
                                    f1 = base64.encodestring(urllib.request.urlopen(urllib.request.Request(imgurl_1, None, headers={'User-Agent': 'Mozilla/5.0'})).read())
                                except ValueError:
                                    raise Warning(_('Invalid Image URL'))
                            except ValueError:  # invalid URL
                                with open(values.get('image_1920'), "rb") as image_file:
                                    f1 = base64.b64encode(image_file.read())
                        else:
                            f1 = False


                        if values.get('file_1') != '':
                            try:
                                imgurl_2 = values.get('file_1')
                                imgurl_2 = self.pre_process_url(imgurl_2)
                                try:    
                                    f2 = base64.encodestring(urllib.request.urlopen(urllib.request.Request(imgurl_2, None, headers={'User-Agent': 'Mozilla/5.0'})).read())
                                except ValueError:
                                    raise Warning(_('Invalid Image URL'))
                            except ValueError:  # invalid URL
                                with open(values.get('file_1'), "rb") as image_file:
                                    f2 = base64.b64encode(image_file.read())
                        else:
                            f2 = False


                        if values.get('file_2') != '':
                            try:
                                imgurl_3 = values.get('file_2')
                                imgurl_3 = self.pre_process_url(imgurl_3)
                                try:
                                    f3 = base64.encodestring(urllib.request.urlopen(urllib.request.Request(imgurl_3, None, headers={'User-Agent': 'Mozilla/5.0'})).read())
                                except ValueError:
                                    raise Warning(_('Invalid Image URL'))
                            except ValueError:  # invalid URL
                                with open(values.get('file_2'), "rb") as image_file:
                                    f3 = base64.b64encode(image_file.read())
                        else:
                            f3 = False

                        if f1:
                            product_values.update({
                                'image_1920' : f1
                            })

                        categ_id = False
                        location_id = False
                        parent_location_id = False
                        if values.get('categ_id'):
                            categ_id = category_obj.search([('name','=',values.get('categ_id'))],limit=1)
                            if categ_id:
                                product_values.update({
                                    'categ_id' : categ_id.id
                                })

                        if not product_id:
                            product_id = product_obj.create(product_values)
                        else:
                            # if product found
                            product_id = product_id
                            product_id.write(product_values)

                        attachment_list = []

                        if f2:
                            file_name = values.get('file_1').split('/')[-1:]
                            prod_temp_id_bi = product_id.product_tmpl_id.id
                            vals = {
                                'product_tmpl_id':prod_temp_id_bi,
                                'name':file_name,
                                'image_1920':f2
                            }
                            record = self.env['product.image'].create(vals)


                        if f3:
                            file_name = values.get('file_2').split('/')[-1:]
                            prod_temp_id_bi = product_id.product_tmpl_id.id
                            vals = {
                                'product_tmpl_id' : prod_temp_id_bi,
                                'name' : file_name,
                                'image_1920' : f3
                            }
                            record = self.env['product.image'].create(vals)

                        # Inventory Valuation
                        if values.get('location_id'):
                            if is_integer(values.get('location_id')):
                                location = values.get('location_id').split('.')
                                location_name = str(location[0])
                            else:
                                location_name = values.get('location_id')

                            if location_name.isnumeric():
                                location_name = str(location_name)
                            else:
                                location_name = str(values.get('location_id'))

                            location_id = location_obj.search([('name','=',location_name)])

                            if not location_id:
                                raise Warning(_('\'{}\' Location is not available.'.format(location_name)))

                        main_parent_loc = location_obj.search([('name','=','ELP')],limit=1)

                        if not main_parent_loc:
                            raise Warning(_('\'ELP\' Location is not available.'))

                        if values.get('parent_location_id'):
                            if is_integer(values.get('parent_location_id')):
                                parent_location = values.get('parent_location_id').split('.')
                                parent_location_name = str(location[0])
                            else:
                                parent_location_name = values.get('parent_location_id')
                            
                            if parent_location_name.isnumeric():
                                parent_location_name = str(parent_location_name)
                            else:
                                parent_location_name = str(values.get('parent_location_id'))

                            parent_location_id = location_obj.search([('name','=',parent_location_name),('location_id','=',main_parent_loc.id)])

                            if not parent_location_id:
                                raise Warning(_('\'{}\' Parent Location is not available.'.format(parent_location_name)))

                        if product_id:
                            product_uom_id= product_id.uom_id

                            lot_id = False

                            if values.get('lot'):
                                lot_id = stock_lot_obj.search([
                                    ('product_id','=',product_id.id),
                                    ('name','=',values.get('lot'))
                                ])

                                if not lot_id:
                                    lot = stock_lot_obj.create({
                                        'name': values.get('lot'),
                                        'product_id': product_id.id,
                                        # 'life_date': date_string,
                                        'company_id' : self.env.user.company_id.id
                                    })
                                    lot_id = lot

                            if lot_id:
                                lot_id = lot_id.id
                                product_id.write({
                                    'tracking' : 'lot'
                                })

                            inventory_id.write({'product_ids' :[(4,product_id.id)] })
                            search_line = self.env['stock.inventory.line'].search([
                                ('product_id','=',product_id.id),
                                ('inventory_id','=',inventory_id.id),
                                ('location_id','=',location_id.id)
                            ])

                            if search_line:
                                for inventory_line in search_line :
                                    inventory_line.write({
                                        'product_qty' : values.get('product_qty') or 0.0,
                                        'prod_lot_id' : lot_id
                                    })
                            else:

                                stock_line_id = self.env['stock.inventory.line'].create({
                                    'product_id' : product_id.id,
                                    'inventory_id' : inventory_id.id,
                                    'location_id' : location_id.id,
                                    'product_uom_id' : product_uom_id.id ,
                                    'product_qty': values.get('product_qty') or 0.0,
                                    'prod_lot_id' : lot_id
                                })

                                stock_line_id._onchange_quantity_context()

                            flag =1
                            counter_product += 1
                        else:
                            raise Warning(_('Something Went Wrong. !!!!'))

            if self.is_validate_inventory == True:
                inventory_id.action_validate()

            g_inv_id = generate_inv.sudo().create({
                'product_counter_main' : int(counter_product)
            })

            if flag ==1:
                return  {
                        'name': _('Success'),
                        'view_type': 'form',
                        'view_mode': 'form',
                        'res_model': 'generate.inv',
                        'view_id': self.env.ref('import_inventory.success_import_wizard').id,
                        'type': 'ir.actions.act_window',
                        'target': 'new'
                        }
            else:
                return True
            
