from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pending_delivery_days = fields.Integer(
        string="Pending Deliveries Period (Days)",
        config_parameter="advanced_sales_shipping_management_vts.pending_delivery_days",
        default=90,
    )

    overdue_sale_days = fields.Integer(
    string="Overdue Quotations Period (Days)",
    config_parameter="advanced_sales_shipping_management_vts.overdue_sale_days",
    default=90,
    )