import csv
import base64
import requests
import os
import binascii
import xlrd
import random
import pandas as pd
import tempfile
import logging
from odoo import fields, models, api
from odoo.exceptions import ValidationError
from dateutil import parser
from odoo.tools.convert import safe_eval

_logger = logging.getLogger("All in one import")

ALL_SHEET_DATA = {
    'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7, 'I': 8, 'J': 9, 'K': 10, 'L': 11, 'M': 12, 'N': 13,
    'O': 14, 'P': 15, 'Q': 16, 'R': 17, 'S': 18, 'T': 19, 'U': 20, 'V': 21, 'W': 22, 'X': 23, 'Y': 24, 'Z': 25,
    'AA': 26, 'AB': 27, 'AC': 28, 'AD': 29, 'AE': 30, 'AF': 31, 'AG': 32, 'AH': 33, 'AI': 34, 'AJ': 35, 'AK': 36, 'AL': 37,
    'AM': 38, 'AN': 39, 'AO': 40, 'AP': 41, 'AQ': 42, 'AR': 43, 'AS': 44, 'AT': 45, 'AU': 46, 'AV': 47, 'AW': 48, 'AX': 49,
    'AY': 50, 'AZ': 51, 'BA': 52, 'BB': 53, 'BC': 54, 'BD': 55, 'BE': 56, 'BF': 57, 'BG': 58, 'BH': 59, 'BI': 60, 'BJ': 61,
    'BK': 62, 'BL': 63, 'BM': 64, 'BN': 65, 'BO': 66, 'BP': 67, 'BQ': 68, 'BR': 69, 'BS': 70, 'BT': 71, 'BU': 72, 'BV': 73,
    'BW': 74, 'BX': 75, 'BY': 76, 'BZ': 77, 'CA': 78, 'CB': 79, 'CC': 80, 'CD': 81, 'CE': 82, 'CF': 83, 'CG': 84, 'CH': 85,
    'CI': 86, 'CJ': 87, 'CK': 88, 'CL': 89, 'CM': 90, 'CN': 91, 'CO': 92, 'CP': 93, 'CQ': 94, 'CR': 95, 'CS': 96, 'CT': 97,
    'CU': 98, 'CV': 99, 'CW': 100
}


class DynamicImportRecordsWizard(models.TransientModel):
    _name = "dynamic.import.records.wizard"
    _description = "Dynamic Import Records Wizard"

    dynamic_import_records_id = fields.Many2one(comodel_name="dynamic.import.records", string="Dynamic Import Record",
                                                help="Select model in which you want to import/create records.")
    import_type = fields.Selection(
        selection=[('Inventory', 'Inventory'), ('Other', 'Other')],
        default="Other",
        string="Which type of data import?"
    )
    inventory_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Inventory Location'
    )
    import_file = fields.Binary('Import File')
    filename = fields.Char(string="File Name")
    row_first_as_header = fields.Boolean(string="Use first row as a header?", default=True)
    csv_file_delimiter = fields.Char(
        string="CSV File Delimiter"
    )

    @api.constrains('filename')
    def _check_filename(self):
        """
        Author: DG
        Usage: From this method checked import file format, if not csv then raise error.
        """
        if self.import_file:
            if not self.filename:
                raise ValidationError("There is no file")
            file_extension = os.path.splitext(self.filename)[1]
            if file_extension.lower() not in ['.csv', '.xlsx']:
                raise ValidationError("The file must be a csv/xlsx file")

    def action_submit_button(self, ftp_server_id=False, sftp_id=False, matched_record_of_import_records=False):
        """
        Author: DG
        Usage: From this method fetch csv/xlsx file & based on configuration of Odoo model record import in Odoo.
        """
        company_id = sftp_id and sftp_id.company_id if sftp_id else ftp_server_id and ftp_server_id.company_id
        if not company_id:
            company_id = self.env.company
        matched_files = []
        if not matched_record_of_import_records:
            matched_record_of_import_records = self.dynamic_import_records_id
            if self.filename.endswith('.csv') and not self.csv_file_delimiter:
                raise ValidationError('Please add CSV File Delimiter.')
        if matched_record_of_import_records:
            inventory_location = self.env['stock.location']

            ftp_split = False
            sftp_split = False
            # When it's through SFTP then fetch files
            if sftp_id:
                try:
                    sftp_client = sftp_id.connect_sftp()
                except Exception as e:
                    raise ValidationError("Something went wrong when we try to connect SFTP server. \n {}".format(e))

                # Fetch all files from SFTP, which matched with the required format.
                matched_files.append(sftp_id.get_all_files_and_folders_from_server_location(sftp_client,
                                                                                            sftp_id.import_file_path,
                                                                                            match='.csv'))
                matched_files.append(sftp_id.get_all_files_and_folders_from_server_location(sftp_client,
                                                                                            sftp_id.import_file_path,
                                                                                            match='.xlsx'))
                matched_files = [item for sublist in matched_files for item in sublist]
                _logger.info("SFTP Matched Files => {}".format(matched_files))
                server_dir = sftp_client.getcwd()
                if server_dir[-1] != '/':
                    server_dir += '/'
                csv_file_delimiter = sftp_id.sftp_delimiter
                if sftp_id.import_type == 'Inventory':
                    inventory_location = sftp_id.inventory_location_id

                # Check if split_records is enabled
                if sftp_id and sftp_id.split_records:
                    sftp_split = True
                    split_dir = server_dir.rstrip('/').split('/')[-1] + "_split"
                    split_path = os.path.join(server_dir, split_dir)

                    # Ensure split directory exists
                    try:
                        sftp_client.listdir(split_path)
                    except FileNotFoundError:
                        sftp_client.mkdir(split_path)

                    split_matched_files = []
                    for file in matched_files:
                        local_temp_file = os.path.join(tempfile.gettempdir(), file)

                        # Download file from SFTP
                        with sftp_client.open(os.path.join(server_dir, file), 'rb') as remote_file, open(local_temp_file, 'wb') as local_file:
                            local_file.write(remote_file.read())

                        # Read CSV/XLSX file and split into chunks of 1000 rows
                        if file.endswith('.csv'):
                            df = pd.read_csv(local_temp_file, delimiter=csv_file_delimiter)
                        elif file.endswith('.xlsx'):
                            df = pd.read_excel(local_temp_file)
                        else:
                            continue  # Skip non-CSV/XLSX files

                        total_rows = len(df)
                        for i in range(0, total_rows, 1000):
                            chunk = df[i:i + 1000]
                            split_file_name = f"{file.rsplit('.', 1)[0]}_part{i // 1000 + 1}.{'csv' if file.endswith('.csv') else 'xlsx'}"
                            split_local_path = os.path.join(tempfile.gettempdir(), split_file_name)

                            # Save split file
                            if file.endswith('.csv'):
                                chunk.to_csv(split_local_path, index=False, sep=csv_file_delimiter)
                            else:
                                chunk.to_excel(split_local_path, index=False)

                            # Upload a split file back to SFTP
                            with open(split_local_path, 'rb') as split_file:
                                with sftp_client.open(os.path.join(split_path, split_file_name), 'wb') as remote_split_file:
                                    remote_split_file.write(split_file.read())

                            split_matched_files.append(split_file_name)
                        os.remove(local_temp_file)
                    _logger.info("Old matched files => {}".format(matched_files))
                    matched_files = split_matched_files  # Update matched_files
                    _logger.info("New matched files => {}".format(split_matched_files))

            # When it's through FTP then fetch files
            elif ftp_server_id:
                if not ftp_server_id.import_file_path:
                    raise ValidationError("File Import Path is not set.")

                try:
                    ftp = ftp_server_id.check_ftp_connection()
                except Exception as e:
                    raise ValidationError("Something went wrong when we try to connect FTP connection. \n {}".format(e))
                ftp.cwd(ftp_server_id.import_file_path)
                files = ftp.nlst()
                server_dir = ftp.pwd()
                valid_extensions = {'.csv', '.xlsx'}
                matched_files = [file for file in files if
                                 file not in {'.', '..'} and any(file.endswith(ext) for ext in valid_extensions)]
                _logger.info("FTP Matched Files => {}".format(matched_files))

                if server_dir[-1] != '/':
                    server_dir += '/'

                csv_file_delimiter = ftp_server_id.ftp_delimiter
                if ftp_server_id.import_type == 'Inventory':
                    inventory_location = ftp_server_id.inventory_location_id

                # If split_records is True, and it's a CSV file, split and store
                if ftp_server_id and ftp_server_id.split_records:
                    ftp_split = True
                    split_dir = server_dir.rstrip('/').split('/')[-1] + "_split"

                    # Create directory if not exists
                    try:
                        ftp.cwd(split_dir)
                    except Exception:
                        ftp.mkd(split_dir)

                    split_matched_files = []
                    for file in matched_files:
                        local_temp_file = os.path.join(tempfile.gettempdir(), file)

                        # Download file from FTP
                        with open(local_temp_file, 'wb') as f:
                            ftp.retrbinary(f"RETR " + server_dir + file, f.write)

                        # Read CSV/XLSX file and split into chunks of 1000 rows
                        if file.endswith('.csv'):
                            df = pd.read_csv(local_temp_file, delimiter=ftp_server_id.ftp_delimiter)
                        elif file.endswith('.xlsx'):
                            df = pd.read_excel(local_temp_file)
                        else:
                            continue  # Skip non-CSV/XLSX files

                        total_rows = len(df)
                        for i in range(0, total_rows, 1000):
                            chunk = df[i:i + 1000]
                            split_file_name = f"{file.rsplit('.', 1)[0]}_part{i // 1000 + 1}.{'csv' if file.endswith('.csv') else 'xlsx'}"
                            _logger.info("FTP: Split file name => {}".format(split_file_name))
                            split_local_path = os.path.join(tempfile.gettempdir(), split_file_name)

                            # Save split file
                            if file.endswith('.csv'):
                                chunk.to_csv(split_local_path, index=False, sep=csv_file_delimiter)
                            else:
                                chunk.to_excel(split_local_path, index=False)

                            # Upload a split file back to FTP
                            with open(split_local_path, 'rb') as f:
                                ftp.storbinary(f"STOR {server_dir}{split_dir}/{split_file_name}", f)

                            split_matched_files.append(split_file_name)
                        os.remove(local_temp_file)
                    _logger.info("Old matched files => {}".format(matched_files))
                    matched_files = split_matched_files  # Update matched_files
                    _logger.info("New matched files => {}".format(split_matched_files))

            # When it's through manual import & CSV file
            elif self.filename.strip().endswith('.csv'):
                try:
                    decoded_data = base64.b64decode(self.import_file).decode('utf-8')
                except UnicodeDecodeError:
                    decoded_data = base64.b64decode(self.import_file).decode('ISO-8859-1')
                with open('/tmp/' + self.filename, "wb") as temp_file:
                    temp_file.write(decoded_data.encode('utf-8', errors='replace'))
                    matched_files = [temp_file.name.split('/')[2]]
                    csv_file_delimiter = self.csv_file_delimiter
                    if self.import_type == 'Inventory':
                        inventory_location = self.inventory_location_id

            # When it's through manual import & XLSX file
            elif self.filename.strip().endswith('.xlsx'):
                with open('/tmp/' + self.filename, "wb") as temp_file:
                    temp_file.write(binascii.a2b_base64(self.import_file))
                    matched_files = [temp_file.name.split('/')[2]]
                    if self.import_type == 'Inventory':
                        inventory_location = self.inventory_location_id

            split_added = False
            for file_name in matched_files:
                main_log_id = self.env['log.book'].create_main_log(file_name)
                if sftp_id:
                    if not sftp_split:
                        sftp_id.import_file_to_local_from_sftp(sftp_client, server_dir + file_name, '/tmp/' + file_name)
                elif ftp_server_id:
                    if not ftp_split:
                        with open('/tmp/' + file_name, 'wb') as local_file:
                            # Retrieve the file from the FTP server
                            ftp.retrbinary(f'RETR {server_dir + file_name}', local_file.write)
                try:
                    file_extension = os.path.splitext(file_name)[1]
                    if file_extension.lower() not in ['.csv', '.xlsx']:
                        self.env['log.book.lines'].create_log("Unsupported File Type", main_log_id,
                                                              fault_operation=True)
                    else:
                        csv_reader = []

                        # When it's a CSV file.
                        if file_name.strip().endswith('.csv'):
                            file = open('/tmp/' + file_name, 'r')
                            csv_reader = csv.reader(file, delimiter=csv_file_delimiter)
                            if sftp_id and sftp_id.row_first_as_header:
                                next(csv_reader)
                            elif ftp_server_id and ftp_server_id.row_first_as_header:
                                next(csv_reader)
                            elif self.row_first_as_header:
                                next(csv_reader)

                        # When it's a XLSX file.
                        elif file_name.strip().endswith('.xlsx'):
                            workbook = xlrd.open_workbook('/tmp/' + file_name)
                            sheet = workbook.sheet_by_index(0)
                            for row_idx in range(sheet.nrows):
                                if sftp_id and row_idx == 0 and sftp_id.row_first_as_header:
                                    continue
                                if ftp_server_id and row_idx == 0 and ftp_server_id.row_first_as_header:
                                    continue
                                if row_idx == 0 and self.row_first_as_header:
                                    continue
                                csv_reader.append([str(cell.value) for cell in sheet.row(row_idx)])

                        row = 0
                        parent_csv_line = []
                        for csv_line in csv_reader:
                            row += 1
                            vals = {} if not self.dynamic_import_records_id.default_value_dynamic_records else safe_eval(self.dynamic_import_records_id.default_value_dynamic_records)
                            multiple_o2m = {}
                            create_record = True
                            child_record = False
                            matched_record_of_o2m = False

                            of_record = ALL_SHEET_DATA[
                                str(matched_record_of_import_records.search_record_from_this_value)]

                            # In csv/xlsx line if all details are not there then based on parent csv line values get
                            # & checked for existing record in odoo.
                            if not csv_line[of_record] and parent_csv_line:
                                search_value = parent_csv_line[of_record]
                                create_record = False
                                child_record = True
                            else:
                                search_value = csv_line[of_record]
                            if not search_value:
                                continue
                            field_name_to_search = matched_record_of_import_records.line_ids.filtered(
                                lambda a: a.file_data == matched_record_of_import_records.search_record_from_this_value)
                            if field_name_to_search:
                                if inventory_location and matched_record_of_import_records.model_id.model == 'stock.quant':
                                    existing_main_record = self.env[matched_record_of_import_records.model_id.model].sudo().with_company(company_id).search(
                                        [(field_name_to_search[0].mapping_model_field_selection_id.name, '=', search_value), ('location_id', '=', inventory_location.id)], limit=1)
                                else:
                                    existing_main_record = self.env[
                                        matched_record_of_import_records.model_id.model].sudo().with_company(company_id).search(
                                        [(field_name_to_search[0].mapping_model_field_selection_id.name, '=', search_value)], limit=1)
                            else:
                                if inventory_location and matched_record_of_import_records.model_id.model == 'stock.quant':
                                    existing_main_record = self.env[matched_record_of_import_records.model_id.model].sudo().with_company(company_id).search(
                                        [('name', '=', search_value), ('location_id', '=', inventory_location.id)], limit=1)
                                else:
                                    existing_main_record = self.env[matched_record_of_import_records.model_id.model].sudo().with_company(company_id).search(
                                        [('name', '=', search_value)], limit=1)

                            for odoo_line in matched_record_of_import_records.line_ids:
                                try:
                                    line = csv_line[ALL_SHEET_DATA[odoo_line.file_data]]
                                except IndexError:
                                    line = ''
                                mapped_field = odoo_line.mapping_model_field_selection_id

                                if not line:
                                    continue
                                try:
                                    if mapped_field.ttype == 'many2one':
                                        # If anyone set any inner field of m2o to search with that data then need to
                                        # check records based on that field value
                                        if odoo_line.field_of_m2o_field:
                                            domain = [(odoo_line.field_of_m2o_field.name, '=', line)]
                                        else:
                                            domain = [('name', '=', line)]
                                        matched_record_of_m2o = self.env[mapped_field.relation].search(domain, limit=1)
                                        if matched_record_of_m2o:
                                            vals.update({mapped_field.name: matched_record_of_m2o.id})
                                        else:
                                            # Value not matched with Odoo records then skip that row,
                                            # not import that record.
                                            create_record = False
                                            log_msg = "In row number [{}], your [{}] field's value [{}] is not matched with Odoo records, so this particular row/record is skipped".format(
                                                row, odoo_line.file_data, line)
                                            self.env['log.book.lines'].create_log(log_msg, main_log_id,
                                                                                  fault_operation=True)
                                            break

                                    # Vals prepared for one2many field
                                    elif mapped_field.ttype == 'one2many':
                                        sub_table_for_o2m = odoo_line.sub_dynamic_mapping_record_id
                                        vals_for_o2m = {} if not sub_table_for_o2m.default_value_dynamic_records else safe_eval(sub_table_for_o2m.default_value_dynamic_records)
                                        if sub_table_for_o2m.search_record_from_this_value:
                                            o2m_value_search = csv_line[ALL_SHEET_DATA[
                                                str(sub_table_for_o2m.search_record_from_this_value)]]
                                            existing_record_update = existing_main_record[
                                                mapped_field.name].filtered(
                                                lambda a: o2m_value_search in a.display_name)
                                        else:
                                            existing_record_update = self.env[sub_table_for_o2m.model_id.model]

                                        for o2m_field_line in sub_table_for_o2m.line_ids:
                                            line = csv_line[ALL_SHEET_DATA[o2m_field_line.file_data]]

                                            o2m_field = o2m_field_line.mapping_model_field_selection_id
                                            if o2m_field.ttype == 'many2one':
                                                if o2m_field_line.field_of_m2o_field:
                                                    domain = [(o2m_field_line.field_of_m2o_field.name, '=', line)]
                                                else:
                                                    domain = [('name', '=', line)]
                                                matched_record_of_o2m = self.env[o2m_field.relation].search(
                                                    domain, limit=1)
                                                if matched_record_of_o2m:
                                                    vals_for_o2m.update({o2m_field.name: matched_record_of_o2m.id})
                                                else:
                                                    # Value not matched with Odoo records then skip that row,
                                                    # not import that record.
                                                    create_record = False
                                                    log_msg = "In row number [{}], your [{}] field's value [{}] is not matched with Odoo records, so this particular row/record is skipped".format(
                                                        row, odoo_line.file_data, line)
                                                    self.env['log.book.lines'].create_log(log_msg, main_log_id,
                                                                                          fault_operation=True)
                                                    break

                                            elif o2m_field.ttype == 'many2many':
                                                o2m_m2m_values = line.split(',')
                                                o2m_m2m_values_list = []
                                                for o2m_m2m_val in o2m_m2m_values:
                                                    # if matched_record_of_o2m:
                                                    #     matched_record_of_o2m_m2m = matched_record_of_o2m.mapped(
                                                    #         o2m_field.name).filtered(lambda a: a.name == o2m_m2m_val)
                                                    # else:
                                                    if o2m_field_line.field_of_m2m_field:
                                                        domain = [(o2m_field_line.field_of_m2m_field.name, '=', o2m_m2m_val)]
                                                    else:
                                                        domain = [('name', '=', o2m_m2m_val)]
                                                    matched_record_of_o2m_m2m = self.env[o2m_field.relation].search(
                                                        domain, limit=1)
                                                    if not matched_record_of_o2m_m2m:
                                                        # Value not matched with Odoo records then skip that row,
                                                        # not import that record.
                                                        create_record = False
                                                        log_msg = "In row number [{}], your [{}] field's value [{}] is not matched with Odoo records, so this particular row/record is skipped".format(
                                                            row, odoo_line.file_data, line)
                                                        self.env['log.book.lines'].create_log(log_msg,
                                                                                              main_log_id,
                                                                                              fault_operation=True)
                                                        break
                                                    o2m_m2m_values_list.append(matched_record_of_o2m_m2m.id)
                                                vals_for_o2m.update(
                                                    {o2m_field.name: [(6, 0, o2m_m2m_values_list)]})

                                            elif o2m_field.ttype in ['float', 'monetary']:
                                                vals_for_o2m.update({o2m_field.name: float(line.replace(',','.'))})

                                            elif o2m_field.ttype == 'integer':
                                                vals_for_o2m.update({o2m_field.name: int(float(line.replace(',','.')))})

                                            elif o2m_field.ttype in ['date', 'datetime']:
                                                if isinstance(line, str):
                                                    parsed_date = parser.parse(line)
                                                    if o2m_field.ttype == 'date':
                                                        line = parsed_date.strftime('%Y-%m-%d')
                                                    elif o2m_field.ttype == 'datetime':
                                                        line = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
                                                vals_for_o2m.update({o2m_field.name: line})

                                            elif o2m_field.ttype == 'selection':
                                                if line in o2m_field.selection_ids.mapped('value'):
                                                    vals_for_o2m.update({o2m_field.name: line})
                                                else:
                                                    if line in o2m_field.selection_ids.mapped('name'):
                                                        selection_value = o2m_field.selection_ids.filtered(
                                                            lambda a: a.name == line).value
                                                        vals_for_o2m.update({o2m_field.name: selection_value})
                                                    else:
                                                        # Value not matched with Odoo records then skip that row,
                                                        # not import that record.
                                                        create_record = False
                                                        log_msg = "In row number [{}], your [{}] field's value [{}] is not matched with Odoo records, so this particular row/record is skipped".format(
                                                            row, odoo_line.file_data, line)
                                                        self.env['log.book.lines'].create_log(log_msg, main_log_id,
                                                                                              fault_operation=True)
                                                        break

                                            elif o2m_field.ttype == 'binary':
                                                image = base64.b64encode(requests.get(line).content)
                                                vals_for_o2m.update({o2m_field.name: image})

                                            else:
                                                vals_for_o2m.update({o2m_field.name: line})
                                        # if mapped_field.name in multiple_o2m:
                                        #     multiple_o2m.get(mapped_field.name).update(vals_for_o2m)
                                        # else:
                                        if create_record or child_record:
                                            multiple_o2m.update({mapped_field.name: vals_for_o2m})

                                    # Vals prepared for many2many field
                                    elif mapped_field.ttype == 'many2many':
                                        m2m_values = line.split(',')
                                        m2m_values_list = []
                                        for m2m_val in m2m_values:
                                            if odoo_line.field_of_m2m_field:
                                                domain = [(odoo_line.field_of_m2m_field.name, '=', m2m_val)]
                                            else:
                                                domain = [('name', '=', m2m_val)]
                                            matched_record_of_m2m = self.env[mapped_field.relation].search(domain,
                                                                                                           limit=1)
                                            if not matched_record_of_m2m:
                                                # Value not matched with Odoo records then skip that row,
                                                # not import that record.
                                                create_record = False
                                                log_msg = "In row number [{}], your [{}] field's value [{}] is not matched with Odoo records, so this particular row/record is skipped".format(
                                                    row, odoo_line.file_data, line)
                                                self.env['log.book.lines'].create_log(log_msg, main_log_id,
                                                                                      fault_operation=True)
                                                break
                                            m2m_values_list.append(matched_record_of_m2m.id)
                                        vals.update({mapped_field.name: [(6, 0, m2m_values_list)]})

                                    # Vals prepared for boolean type fields
                                    elif mapped_field.ttype == 'boolean':
                                        if line.lower() in ['yes', 'true', 'y', '1']:
                                            vals.update({mapped_field.name: True})
                                        elif line.lower() in ['no', 'false', 'n', '0']:
                                            vals.update({mapped_field.name: False})

                                    # Vals prepared for float type fields
                                    elif mapped_field.ttype in ['float', 'monetary']:
                                        vals.update({mapped_field.name: float(line.replace(',','.'))})

                                    # Vals prepared for integer type fields
                                    elif mapped_field.ttype == 'integer':
                                        vals.update({mapped_field.name: int(float(line.replace(',','.')))})

                                    # Vals prepared for date/datetime type fields
                                    elif mapped_field.ttype in ['date', 'datetime']:
                                        if isinstance(line, str):
                                            parsed_date = parser.parse(line)
                                            # Format the date object to yyyy-mm-dd
                                            if mapped_field.ttype == 'date':
                                                line = parsed_date.strftime('%Y-%m-%d')
                                            # Format the datetime object to yyyy-mm-dd h-m-s
                                            elif mapped_field.ttype == 'datetime':
                                                line = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
                                        vals.update({mapped_field.name: line})

                                    # Vals prepared for selection type fields
                                    elif mapped_field.ttype == 'selection':
                                        if line in mapped_field.selection_ids.mapped('value'):
                                            vals.update({mapped_field.name: line})
                                        else:
                                            if line in mapped_field.selection_ids.mapped('name'):
                                                selection_value = mapped_field.selection_ids.filtered(
                                                    lambda a: a.name == line).value
                                                vals.update({mapped_field.name: selection_value})
                                            else:
                                                create_record = False
                                                log_msg = "In row number [{}], your [{}] field's value [{}] is not matched with Odoo records, so this particular row/record is skipped".format(
                                                    row, odoo_line.file_data, line)
                                                self.env['log.book.lines'].create_log(log_msg, main_log_id,
                                                                                      fault_operation=True)
                                                break

                                    # Vals prepared for binary type fields
                                    elif mapped_field.ttype == 'binary':
                                        image = base64.b64encode(requests.get(line).content)
                                        vals.update({mapped_field.name: image})

                                    # Vals prepared for other type fields
                                    else:
                                        vals.update({mapped_field.name: line})

                                    # if multiple_o2m:
                                    #     for key, values in multiple_o2m.items():
                                    #         if existing_record_update:
                                    #             vals.update({key: [(1, existing_record_update[0].id, values)]})
                                    #         else:
                                    #             random_number = random.randint(1, 100)
                                    #             if not vals.get(key):
                                    #                 vals.update({key: []})
                                    #             vals.get(key).append([0, f'virtual_{random_number}', values])
                                    #             # vals.update({key: [(0, 0, values)]})
                                except Exception as e:
                                    error_message = "Something went wrong! {}".format(e)
                                    _logger.info(">>>>>>>>>>>>>>>>>>>>>>=> {}".format(error_message))

                                    self.env['log.book.lines'].create_log(error_message, main_log_id,
                                                                  fault_operation=True)
                            try:
                                if multiple_o2m:
                                    for key, values in multiple_o2m.items():
                                        if existing_record_update:
                                            vals.update({key: [(1, existing_record_update[0].id, values)]})
                                        else:
                                            random_number = random.randint(1, 100)
                                            if not vals.get(key):
                                                vals.update({key: []})
                                            vals.get(key).append([0, f'virtual_{random_number}', values])
                            except Exception as e:
                                error_message = "Something went wrong! {}".format(e)
                                _logger.info(">>>>>>>>>>>>>>>>>>>>>>=> {}".format(error_message))

                                self.env['log.book.lines'].create_log(error_message, main_log_id,
                                                                      fault_operation=True)

                            if csv_line[0]:
                                parent_csv_line = csv_line
                            if existing_main_record:
                                existing_main_record.sudo().with_company(company_id).write(vals)
                                if matched_record_of_import_records.model_id.model == 'stock.quant':
                                    existing_main_record.action_apply_inventory()
                                log_msg = f"Found Existing Record of [{existing_main_record._description}]. Updated the values in record ID : [{existing_main_record.id}]."
                                self.env['log.book.lines'].create_log(log_msg, main_log_id)
                            else:
                                if create_record and vals:
                                    if matched_record_of_import_records.model_id.model == 'product.template' and (
                                            'type' not in vals or vals.get('type') == 'consu'):
                                        if 'is_storable' not in vals:
                                            vals['is_storable'] = True
                                    try:
                                        if inventory_location and matched_record_of_import_records.model_id.model == 'stock.quant':
                                            if 'location_id' not in vals:
                                                vals['location_id'] = inventory_location.id
                                                product_id = self.env['product.product'].search(
                                                    [('default_code', '=', csv_line[0])])
                                                if product_id:
                                                    new_quant = (
                                                    self.env['stock.quant'].sudo().with_context(inventory_mode=True).with_company(company_id).create({
                                                        'product_id': product_id.id,
                                                        'location_id': vals.get('location_id'),
                                                        'inventory_quantity': int(csv_line[1]),
                                                    }))
                                                    new_quant.action_apply_inventory()
                                                    log_msg = f"New [{new_quant._description}] record created for Product [{product_id.display_name}] with quantity [{new_quant.quantity}]."
                                                    self.env['log.book.lines'].create_log(log_msg, main_log_id)
                                        else:
                                            created_record = self.env[matched_record_of_import_records.model_id.model].sudo().with_company(company_id).create(vals)
                                            log_msg = f"New [{matched_record_of_import_records.model_id.name}] record created."
                                            self.env['log.book.lines'].create_log(log_msg, main_log_id)
                                    except Exception as e:
                                        error_message = (f"Failed to create record with vals: {vals} of {matched_record_of_import_records.model_id.name}. Error: {e}")
                                        _logger.info(
                                            ">>>>>>>>>>>>>>>>>>>>>> => {}".format(error_message))
                                        # self.env.cr.rollback()
                                        self.env['log.book.lines'].create_log(error_message, main_log_id,
                                                                              fault_operation=True)
                                        continue
                                    # if matched_record_of_import_records.model_id.model == 'stock.quant':
                                    #     created_record.action_apply_inventory()
                                    # onchange_fields = list(vals.keys()) or []
                                    # for field_name in onchange_fields:
                                    #     for method in parent_record._onchange_methods.get(field_name, ()):
                                    #         method(parent_record)
                                elif child_record and not create_record:
                                    log_msg = "For row number [{}], no any parent record found, so this particular row/record is skipped".format(
                                        row)
                                    self.env['log.book.lines'].create_log(log_msg, main_log_id,
                                                                          fault_operation=True)
                            self._cr.commit()
                        if sftp_id:
                            if sftp_split and not split_added:
                                server_dir = server_dir + split_dir + '/'
                                split_added = True
                            try:
                                sftp_client.chdir(server_dir + 'Archive')
                            except IOError:
                                sftp_client.mkdir(server_dir + 'Archive')
                                sftp_client.chdir(server_dir + 'Archive')
                            sftp_id.rename_file_from_sftp_server(sftp_client, server_dir + file_name,
                                                                 server_dir + '/Archive/' + file_name)
                        elif ftp_server_id:
                            if ftp_split and not split_added:
                                server_dir = server_dir + split_dir + '/'
                                split_added = True
                            try:
                                ftp.cwd(server_dir + 'Archive')
                                print(f"Archive folder already exists: {server_dir + 'Archive'}")
                            except Exception:
                                ftp.mkd(server_dir + 'Archive')
                                print(f"Created Archive folder: {server_dir + 'Archive'}")
                            ftp.rename(server_dir + file_name, server_dir + 'Archive/' + file_name)
                except Exception as e:
                    error_message = "Please upload in specified format ! {}".format(e)
                    _logger.info(">>>>>>>>>>>>>>>>>>>>>>=> {}".format(error_message))
                    self.env['log.book.lines'].create_log(error_message, main_log_id,
                                                          fault_operation=True)
                if main_log_id and not main_log_id.log_detail_ids:
                    main_log_id.unlink()
