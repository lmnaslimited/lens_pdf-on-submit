__version__ = "15.0.1"

'''
Monkey Patch Technique
'''
from frappe.workflow.doctype.workflow_action import workflow_action
from pdf_on_submit.monkey_patch import custom_get_users_next_action_data

workflow_action.get_users_next_action_data = custom_get_users_next_action_data