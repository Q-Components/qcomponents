from odoo import models, fields, api, _
from odoo.tools.translate import _
from odoo.exceptions import Warning

class python_code_execute(models.Model):
    _name = "python.code.execute"
    
    name=fields.Char(string='Name',required=True)
    py_code=fields.Text(string='Python Code',required=True)
    result=fields.Text(string='Result',readonly=True)
    
    def execute(self):
        codedict = {'self':self,'user_obj':self.env.user}
        for code_obj in self:
            try :
                exec(code_obj.py_code,codedict)
                if codedict.get('result', False):
                    self.write({'result':codedict['result']})
                else : 
                    self.write({'result':'Nothing'})
            except Exception as e:
                raise Warning('Getting an error in python code : %s' %(e))
        return True    
