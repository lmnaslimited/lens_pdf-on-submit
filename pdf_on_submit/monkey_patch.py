import frappe
from frappe import _
from frappe.model.workflow import (
	get_workflow_name,
)
from frappe.workflow.doctype.workflow_action.workflow_action import (
	get_doc_workflow_state,
	get_users_next_action_data
)

'''
This function is equivalent to the standard "get_users_next_action_data"
located at "frappe.workflow.doctype.workflow_action.workflow_action".

This customization is known as monkey patching in ERPNext. To apply this custom function,
we need to specify the path to this function in the "__init__.py" file of the custom app.

The "__init__.py" file should be located at:
"apps/custom_app/custom_app/__init__.py".

By doing this, we override the original function with our custom implementation.
'''

def custom_get_users_next_action_data(transitions, doc):

	user_data_map = {}

	#getting the workflow name from the doctype
	workflow = get_workflow_name(doc.get("doctype"))

	if not workflow:
		return
	
	'''
	Check if the state should mute email notifications.
	To achieve this, we need to customize the "Workflow Document State" doctype
	by adding a field named "custom_mute_email_notification" which is a checkbox.

	'''
	mute_email = frappe.get_cached_value(
		"Workflow Document State", 
		{"parent": workflow, "state": get_doc_workflow_state(doc)}, 
		"custom_mute_email_notification"
		)
	
	if not mute_email:
		return get_users_next_action_data(transitions, doc)
	
	return user_data_map

    