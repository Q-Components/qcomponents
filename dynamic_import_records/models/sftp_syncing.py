from odoo import models, fields, _
from odoo.exceptions import ValidationError, UserError
import paramiko


class SftpSyncing(models.Model):
    _name = "sftp.syncing"

    name = fields.Char("Server name", required=True)
    sftp_host = fields.Char("Host", required=True)
    sftp_username = fields.Char("User Name", required=True)
    sftp_password = fields.Char("Password")
    sftp_port = fields.Char("Port", required=True)
    store = fields.Selection([('import_dynamic_records', 'Import Dynamic Records')], string="Store")
    cron_created = fields.Boolean(string="Cron Created", default=False, copy=False)
    import_file_path = fields.Char(string="File Import Path", default="/tmp")
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one("res.company", "Company")
    dynamic_import_records_id = fields.Many2one("dynamic.import.records", "Dynamic Import Record")
    row_first_as_header = fields.Boolean(string="Use first row as a header?", default=True)

    def connect_sftp(self):
        try:
            sftp_host = self.sftp_host
            sftp_username = self.sftp_username
            sftp_password = self.sftp_password
            sftp_port = int(self.sftp_port)
            # key_filename = self.directory_name
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(hostname=sftp_host, username=sftp_username, password=sftp_password, port=sftp_port or 2222)
            sftp_client = ssh.open_sftp()
            return sftp_client
        except Exception as e:
            raise UserError(_("SFTP Connection Test Failed! Here is what we got instead:\n %s") % (e))

    def sftp_test_connection(self):
        try:
            sftp_client = self.connect_sftp()
            if sftp_client:
                title = _("SFTP Connection Test Succeeded!")
                message = _("Everything seems properly set up!")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': title,
                        'message': message,
                        'sticky': False,
                    }
                }
        except Exception as e:
            raise UserError(_("Connection Failed! Here is what we got instead:\n %s") % (e))

    def rename_file_from_sftp_server(self, sftp_client, old_path, new_path):
        # You can use this method to change file location as well
        try:
            sftp_client.rename(old_path, new_path)
        except Exception as e:
            raise UserError(_("Error while change file location! Here is what we got instead:\n %s") % (e))

    def export_file_to_sftp_server(self, sftp_client, local_location, server_location):
        try:
            sftp_client.put(local_location, server_location)
        except Exception as e:
            raise UserError(_("Error while export file to Server! Here is what we got instead:\n %s") % (e))

    def import_file_to_local_from_sftp(self, sftp_client, server_location, local_location):
        try:
            sftp_client.get(server_location, local_location)
        except Exception as e:
            raise UserError(_("Error while getting file from Server! Here is what we got instead:\n %s") % (e))

    def get_all_files_and_folders_from_server_location(self, sftp_client, server_location, match):
        try:
            sftp_client.chdir(server_location)
            return list(set([x for x in sftp_client.listdir() if match in x]))
        except Exception as e:
            raise UserError(
                _("Error while get file and folders name from Server! Here is what we got instead:\n %s") % (e))

    def create_cron_job(self, cron_name, code_method, interval_number=10, interval_type='minutes', numbercall=1):
        self.env['ir.cron'].create({
            'name': cron_name,
            'model_id': self.env.ref('dynamic_import_records.model_sftp_syncing').id,
            'state': 'code',
            'code': code_method,
            'interval_number': interval_number,
            'interval_type': interval_type,
            'numbercall': numbercall,
            'doall': True,
            'active': False,
            'user_id': 1
        })

    def click_to_create_cron(self):
        if not self.store:
            raise ValidationError(_("PLease Select Your 3PL store."))
        if hasattr(self, '{}_create_schedule_actions'.format(self.store)):
            getattr(self, '{}_create_schedule_actions'.format(self.store))()
        self.cron_created = True

    def import_dynamic_records_create_schedule_actions(self):
        if not self.env['ir.cron'].search(
                [('code', '=', "model.import_dynamic_records({})".format(self.id))]):
            cron_name = "SFTP - [{}] import file fetch".format(self.name)
            code_method = "model.sftp_import_file({})".format(self.id)
            self.create_cron_job(cron_name, code_method, interval_number=2, interval_type='hours', numbercall=-1)

    def sftp_import_file(self, sftp_id):
        sftp_server_ids = self.browse(sftp_id)
        dynamic_import_record = sftp_server_ids.dynamic_import_records_id
        dynamic_import = self.env['dynamic.import.records.wizard']
        dynamic_import.action_submit_button(sftp_server_ids, dynamic_import_record)
