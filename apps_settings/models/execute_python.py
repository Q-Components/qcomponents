from odoo import models, fields, api, _
from odoo.tools.translate import _
from odoo.exceptions import Warning
from odoo.tools.safe_eval import safe_eval

class python_code_execute(models.Model):
    _name = "python.code.execute"
    
    name=fields.Char(string='Name',required=True)
    py_code=fields.Text(string='Python Code',required=True)
    result=fields.Text(string='Result',readonly=True)
    
    def execute(self):
        result = {}
        codedict = {'self':self,'user_obj':self.env.user,'result': None}
        try :
            #safe_eval(self.py_code, codedict, mode='exec', nocopy=True)
            exec(self.py_code,codedict)
            if codedict.get('result', ''):
                self.write({'result':codedict['result']})
            else : 
                self.write({'result':'Getting None Record'})
        except Exception as e:
            raise Warning('Getting an Error:{0}'.format(e))
