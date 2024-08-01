__version__ = "15.0.1"
from frappe.workflow.doctype.workflow_action import workflow_action
from pdf_on_submit.monkey_patch import custom_send_workflow_action_email

workflow_action.send_workflow_action_email = custom_send_workflow_action_email