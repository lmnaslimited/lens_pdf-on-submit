import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name, send_email_alert

from frappe.workflow.doctype.workflow_action.workflow_action import \
get_doc_workflow_state, get_users_next_action_data, clear_workflow_actions, \
is_workflow_action_already_created, update_completed_workflow_actions, \
clear_doctype_notifications, create_workflow_actions_for_roles, get_next_possible_transitions, \
send_workflow_action_email
from frappe.utils.background_jobs import enqueue



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
	else:
		user_data_map['empty'] = frappe._dict(
					{
						"possible_actions": [],
						"email": ''
					}
				)
	
	return user_data_map
# def check_state_if_email_muted():

'''
Monkey patching the standard process workflow actions with custom
process workflow actions to supress email notification for a particular
workflow state.
'''
def cust_process_workflow_actions(doc, state):
	workflow = get_workflow_name(doc.get("doctype"))
	if not workflow:
		return

	if state == "on_trash":
		clear_workflow_actions(doc.get("doctype"), doc.get("name"))
		return

	if is_workflow_action_already_created(doc):
		return

	update_completed_workflow_actions(doc, workflow=workflow, workflow_state=get_doc_workflow_state(doc))
	clear_doctype_notifications("Workflow Action")

	next_possible_transitions = get_next_possible_transitions(workflow, get_doc_workflow_state(doc), doc)

	if not next_possible_transitions:
		return

	roles = {t.allowed for t in next_possible_transitions}
	create_workflow_actions_for_roles(roles, doc)

    # Check if the state is muted for email notifications
	is_mute_email = frappe.get_cached_value(
		"Workflow Document State", 
		{"parent": workflow, "state": get_doc_workflow_state(doc)}, 
		"custom_mute_email_notification"
		)
	# Do not process the worklfow email triggers when email notification
	# is muted for the state
	if is_mute_email:
		return
	if send_email_alert(workflow):
		enqueue(
			send_workflow_action_email,
			queue="short",
			doc=doc,
			transitions=next_possible_transitions,
			enqueue_after_commit=True,
		)