# from typing import TYPE_CHECKING, Union
# import frappe

# if TYPE_CHECKING:
#     from frappe.model.document import Document
#     from frappe.workflow.doctype.workflow.workflow import Workflow

# @frappe.whitelist()
# def custom_get_transitions(
#     doc: Union["Document", str, dict], workflow: "Workflow" = None, raise_exception: bool = False
# )-> list[dict]:
    
#     transitions = frappe.call("frappe.model.workflow.get_transitions", doc = doc, workflow = workflow)

#     # custom_transition_method = frappe.call(workflow.custom_transition_method, get_transition)
#     return transitions

import frappe
from frappe import _
from frappe.desk.notifications import clear_doctype_notifications
from frappe.model.workflow import (
	get_workflow_name,
	send_email_alert,
)
from frappe.utils.background_jobs import enqueue
from frappe.workflow.doctype.workflow_action.workflow_action import (
	create_workflow_actions_for_roles,
	clear_workflow_actions,
	is_workflow_action_already_created,
	update_completed_workflow_actions,
	get_doc_workflow_state,
	get_next_possible_transitions,
	send_workflow_action_email,
)


def custom_send_workflow_action_email(doc, transitions):
	# workflow = get_workflow_name(doc.get("doctype"))
	# if not workflow:
	# 	return

	# if state == "on_trash":
	# 	clear_workflow_actions(doc.get("doctype"), doc.get("name"))
	# 	return

	# if is_workflow_action_already_created(doc):
	# 	return

	# update_completed_workflow_actions(doc, workflow=workflow, workflow_state=get_doc_workflow_state(doc))
	# clear_doctype_notifications("Workflow Action")

	# next_possible_transitions = get_next_possible_transitions(workflow, get_doc_workflow_state(doc), doc)

	# if not next_possible_transitions:
	# 	return

	# roles = {t.allowed for t in next_possible_transitions}
	# create_workflow_actions_for_roles(roles, doc)

	# mute_email = frappe.get_cached_value("Workflow Document State", {"parent": workflow, "state": get_doc_workflow_state(doc)}, "custom_mute_email_notification")
    
	# if send_email_alert(workflow) and not mute_email:
	# 	enqueue(
	# 		send_workflow_action_email,
	# 		queue="short",
	# 		doc=doc,
	# 		transitions=next_possible_transitions,
	# 		enqueue_after_commit=True,
	# 	)
	# # frappe.msgprint("this is to test the monkey patch")

    workflow = get_workflow_name(doc.get("doctype"))
    if not workflow:
        return
    mute_email = frappe.get_cached_value("Workflow Document State", {"parent": workflow, "state": get_doc_workflow_state(doc)}, "custom_mute_email_notification")
    
    if (not mute_email):
        return send_workflow_action_email(doc, transitions)
    else: 
        frappe.msgprint("don't trigger the email")
        return []
    