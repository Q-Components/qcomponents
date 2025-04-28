from odoo import models,fields
import logging
import email
import json
from email.header import decode_header
from odoo.addons.iap.tools.iap_tools import iap_jsonrpc

_logger = logging.getLogger(__name__)


class EmailLLM(models.Model):
    _name = 'email.llm'
    _description = 'Email LLM Integration'
    _rec_name = 'email_sender_name'
    _order = 'create_date desc'

    email_sender_name = fields.Char(
        string='customer_name',
        help="Email and Sender Name",
        copy=False
    )
    email_body = fields.Text(
        string='Email',
        copy=False
    )
    gpt_response = fields.Text(
        string='GPT Response',
        copy=False
    )
    matched_product_data = fields.Text(
        string='Matched Product Info',
        copy=False
    )
    llm_error_value = fields.Char(
        string="Error",
        copy=False
    )
    generated_sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string="Related Quotation",
        copy=False
    )

    def decode_utf8(self, text):
        """Decode header into utf-8"""
        decoded_parts = decode_header(text)
        return "".join(
            part.decode(encoding or "utf-8") if isinstance(part, bytes) else part
            for part, encoding in decoded_parts
        )

    def get_email_body(self, msg):
        """Fetch the body content from email"""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" not in content_disposition:
                    if content_type == "text/plain":
                        return part.get_payload(decode=True).decode()  # Return plain text
                    elif content_type == "text/html":
                        return part.get_payload(decode=True).decode()  # Return HTML content
        else:
            return msg.get_payload(decode=True).decode()

    def send_to_gpt(self, email_body):
        try:
            ir_config = self.env['ir.config_parameter'].sudo()
            olg_api_endpoint = ir_config.get_param('web_editor.olg_api_endpoint', 'https://olg.api.odoo.com')

            prompt = email_body
            after_prompt = """Instructions:  
You are an advanced AI assistant specialized in Odoo systems. I am a supplier with a database in Odoo, and your task is to process customer emails related to product inquiries. 
1. Identify whether the email is related to a product inquiry:
- If the email is not related to a product inquiry, return '0'. Do not provide any other response or explanation.
- If the email is related to a product inquiry, proceed with the following steps.
2. Extract Product Information:
- Identify the product(s) mentioned in the email, including similar terms or synonyms (e.g., 'Desk' for 'Table', 'Couch' for 'Sofa').
- List all relevant product names and their synonyms for the identified products. Including synonyms is mandatory.
3. Identify Customer Intent:
- Determine the customer’s intent for each product. Common intents include:
- Pricing: Is the customer asking for a price?
- Stock: Is the customer asking about availability or quantity?
- Delivery: Is the customer asking about delivery time or terms?
- Return Policy: Is the customer asking about returns or refunds?
Include all relevant intent keywords for each product.
4. Map to Odoo Technical Fields:
- For each identified intent, provide the exact technical field names in Odoo (e.g., list_price, sale_delay, return_policy_custom). Use real database field names, not UI labels.
5. Output:
- Return the extracted information in a clean, properly structured JSON format that is immediately usable for code parsing.
- Ensure the JSON is production-ready, meaning it is formatted correctly and free from unnecessary explanations, labels, or markdown.
Example Output:
{
  "products": [
    {
      "name": "chair",
      "similar_terms": ["seat","stool"],
      "intent_keywords": ["pricing","stock","delivery","return_policy"],
      "related_odoo_fields": ["list_price","qty_available","sale_delay","return_policy_custom"]
    }
  ]
}
This format should be returned without any additional text or explanation. Just the JSON as shown.
"""
            if after_prompt:
                prompt = "Email:" + prompt + "\n" + after_prompt

            response = iap_jsonrpc(
                f"{olg_api_endpoint}/api/olg/1/chat",
                params={
                    'prompt': prompt,
                    'conversation_history': []
                },
                timeout=30
            )

            if response.get('status') == 'success':
                if response['content'] == '0':
                    return
                else:
                    return response['content']
            elif response.get('status') == 'error_prompt_too_long':
                message = "Sorry, your prompt is too long. Try to say it in fewer words."
                self.llm_error_value = message
                _logger.info(message)
                return
            else:
                message = "Unexpected GPT response."
                self.llm_error_value = message
                _logger.info(message)
                return

        except Exception as e:
            message = f"Error while calling GPT: {e}"
            self.llm_error_value = message
            _logger.info(message)
            return

    def process_gpt_product_matches(self):
        """Process GPT response and match products from Odoo"""
        for record in self:
            try:
                if not record.gpt_response:
                    continue

                gpt_data = json.loads(record.gpt_response)
                products_info = []

                for prod in gpt_data.get('products', []):
                    terms = [prod.get('name')] + prod.get('similar_terms', [])
                    related_fields = prod.get('related_odoo_fields', [])

                    domain = ['|'] * (len(terms) - 1) + [('name', 'ilike', term) for term in terms]
                    matched_products = self.env['product.product'].search(domain)

                    for product in matched_products:
                        product_data = {
                            'product_id': product.id,
                            'name': product.display_name,
                        }

                        for field in related_fields:
                            if hasattr(product, field):     # Only include field if it exists
                                product_data[field] = getattr(product, field)

                        products_info.append(product_data)

                # Save structured data as JSON
                record.matched_product_data = json.dumps(products_info, indent=2)

            except Exception as e:
                message = f"Failed to process GPT product matches: {e}"
                record.llm_error_value = message
                _logger.info(message)

    def create_quotation_from_matched_products(self):
        """Find and match products in Odoo and Create Quotation"""
        matched_data = json.loads(self.matched_product_data or "[]")
        if not matched_data:
            message = "No matched product data found."
            self.llm_error_value = message
            _logger.info(message)
            return

        name, email_addr = email.utils.parseaddr(self.email_sender_name)

        # Search for partner by email
        partner = self.env['res.partner'].search([
            ('email', '=', email_addr)
        ], limit=1)

        # If not found, create a new individual partner
        if not partner:
            partner = self.env['res.partner'].create({
                'name': name,
                'email': email_addr,
                'is_company': False,
            })
            _logger.info(f"Created new partner: '{partner.name}' with Email : '{partner.email}'.")

        if not partner:
            message = "Failed to create new partner."
            self.llm_error_value = message
            _logger.warning(message)
            return

        order_lines = []

        for prod in matched_data:
            order_lines.append((0, 0, {
                'product_id': prod.get('product_id'),
                'product_uom_qty': 1
            }))

        sale_order = self.env['sale.order'].create({
            'name': '/',
            'partner_id': partner.id,
            'order_line': order_lines,
            'client_order_ref': email_addr,
        })
        if sale_order:
            self.generated_sale_order_id = sale_order.id
            _logger.info(f"Quotation Created Successfully for {self.email_sender_name}.")

    def action_view_sale_order(self):
        for record in self:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': record.generated_sale_order_id.id,
                'view_mode': 'form',
                'views': [(self.env.ref('sale.view_order_form').id, 'form')],
                'target': 'current',
            }