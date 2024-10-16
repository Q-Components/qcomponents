import datetime
from odoo import models, fields, api
from datetime import datetime, timedelta


class LogBook(models.Model):
    _name = "log.book"
    _description = "Log Book"
    _order = 'id desc'

    name = fields.Char("Name")
    company_id = fields.Many2one("res.company", "Company")
    file_name = fields.Char(string="File Name")
    log_detail_ids = fields.One2many('log.book.lines', 'log_id', 'Logs')

    @api.model
    def create(self, vals):
        sequence = self.env.ref("dynamic_import_records.seq_log_main_log")
        name = sequence and sequence.next_by_id() or '/'
        company_id = self._context.get('company_id', self.env.user.company_id.id)
        if type(vals) == dict:
            vals.update({'name': name, 'company_id': company_id})
        return super(LogBook, self).create(vals)

    def auto_delete_log_message(self):
        """
        Auto delete log message through crone process
        """
        for obj in self.search([('create_date', '<', datetime.now() - timedelta(days=13))]):
            obj.log_detail_ids.unlink()
            obj.unlink()

    def create_main_log(self, file_name):
        vals = {
            'file_name': file_name,
        }
        log_id = self.create(vals)
        return log_id


class LogBookLines(models.Model):
    _name = "log.book.lines"
    _description = "Log Book Lines"
    _order = 'id desc'

    name = fields.Char("Name")
    company_id = fields.Many2one("res.company", "Company")
    log_message = fields.Char("Message")
    log_id = fields.Many2one('log.book', 'Main Log')
    fault_operation = fields.Boolean(string="Fault")

    @api.model
    def create(self, vals):
        sequence = self.env.ref("dynamic_import_records.seq_log_logs_line")
        name = sequence and sequence.next_by_id() or '/'
        company_id = self._context.get('company_id', self.env.user.company_id.id)
        if type(vals) == dict:
            vals.update({'name': name, 'company_id': company_id})
        return super(LogBookLines, self).create(vals)

    def create_log(self, log_message, main_log, fault_operation=False):
        vals = {
            'log_message': log_message,
            'log_id': main_log and main_log.id,
            'fault_operation': fault_operation
        }
        log_id = self.create(vals)
        return log_id
