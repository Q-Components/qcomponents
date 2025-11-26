import logging
import ftplib
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class DynamicImportFTPSyncing(models.Model):
    _name = 'dynamic.import.ftp.syncing'
    _description = "FTP Syncing"

    name = fields.Char(
        string='Name'
    )
    is_verified = fields.Boolean(
        string='Verified ?'
    )
    ftp_url = fields.Char(
        string='URL',
        copy=False
    )
    ftp_port = fields.Char(
        string='Port',
        default='21',
        copy=False
    )
    ftp_username = fields.Char(
        string='Username',
        copy=False
    )
    ftp_password = fields.Char(
        string='Password',
        copy=False
    )
    cron_created = fields.Boolean(
        string="Cron Created",
        default=False,
        copy=False
    )
    store = fields.Selection(
        selection=[('import_dynamic_records', 'Import Dynamic Records')],
        string="Store"
    )
    import_file_path = fields.Char(
        string="File Import Path",
        default="/tmp"
    )
    import_type = fields.Selection(
        selection=[('Inventory', 'Inventory'), ('Other', 'Other')],
        default="Other",
        string="Which type of data import?"
    )
    inventory_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Inventory Location'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company"
    )
    dynamic_import_records_id = fields.Many2one(
        comodel_name="dynamic.import.records",
        string="Dynamic Import Record"
    )
    row_first_as_header = fields.Boolean(
        string="Use first row as a header?",
        default=True
    )
    ftp_delimiter = fields.Char(
        string="CSV File Delimiter"
    )
    split_records = fields.Boolean(
        string='Split the records of a file',
        copy=False,
        default=False,
        help='If a file is too large in size or contains too many lines, split its records to ensure smooth processing.'
    )

    def check_ftp_connection(self):
        """
        This method is used to connect FTP with using url, port, username & password.
        Author: DG
        """
        f = ftplib.FTP()
        f.connect(self.ftp_url, int(self.ftp_port), timeout=10)
        f.login(self.ftp_username, self.ftp_password)
        return f

    def action_check_ftp_connection(self):
        """
        This method is used to check connection through form view's button & based on it set value in is_verified.
        Author: DG
        """
        try:
            self.check_ftp_connection()
            title = _("Connection Test Succeeded!")
            message = _("Everything seems properly set up!")
            self.with_context({'is_check_connection_from_write': True}).write({'is_verified': True})
        except Exception as e:
            self.with_context({'is_check_connection_from_write': True}).write({'is_verified': False})
            title = _("Issue in Connection!")
            message = _(str(e))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'sticky': False
            }
        }

    @api.model_create_multi
    def create(self, vals_list):
        """
        This method is used to check connection at the time of creating record of FTP Syncing.
        Author: DG
        """
        res = super(DynamicImportFTPSyncing, self).create(vals_list)
        for rec in res:
            rec.action_check_ftp_connection()
        return res

    def write(self, vals):
        """
        This method is used to check connection at the time of write record of FTP Syncing.
        Author: DG
        """
        res = super(DynamicImportFTPSyncing, self).write(vals)
        if not self.env.context.get('is_check_connection_from_write'):
            for rec in self:
                rec.action_check_ftp_connection()
        return res

    def create_cron_job(self, cron_name, code_method, interval_number=10, interval_type='minutes'):
        self.env['ir.cron'].create({
            'name': cron_name,
            'model_id': self.env.ref('dynamic_import_records.model_dynamic_import_ftp_syncing').id,
            'state': 'code',
            'code': code_method,
            'interval_number': interval_number,
            'interval_type': interval_type,
            'active': False,
            'user_id': 1
        })

    def click_to_create_cron(self):
        if not self.store:
            raise ValidationError(_("PLease Select Store."))
        if hasattr(self, '{}_create_schedule_actions'.format(self.store)):
            getattr(self, '{}_create_schedule_actions'.format(self.store))()
        self.cron_created = True

    def import_dynamic_records_create_schedule_actions(self):
        if not self.env['ir.cron'].search(
                [('code', '=', "model.import_dynamic_records({})".format(self.id))]):
            cron_name = "FTP - [{}] import file fetch".format(self.name)
            code_method = "model.ftp_import_file({})".format(self.id)
            self.create_cron_job(cron_name, code_method, interval_number=2, interval_type='hours')

    def ftp_import_file(self, ftp_id):
        ftp_server_ids = self.browse(ftp_id)
        dynamic_import_record = ftp_server_ids.dynamic_import_records_id
        dynamic_import = self.env['dynamic.import.records.wizard']
        dynamic_import.action_submit_button(ftp_server_id=ftp_server_ids,
                                            matched_record_of_import_records=dynamic_import_record)

    def sync_inner_files(self, import_path, ftp):
        """
        This method is used to sync inner files from an Import path given in configuration.
        Author: DG
        """
        self.ensure_one()
        if not import_path:
            raise ValidationError("File Import Path is not set.")
        ftp.cwd(import_path)
        files = ftp.nlst()
        valid_extensions = {'.csv', '.xlsx'}
        return [file for file in files if
                file not in {'.', '..'} and any(file.endswith(ext) for ext in valid_extensions)]
