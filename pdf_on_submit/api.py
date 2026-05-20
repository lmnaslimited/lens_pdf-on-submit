import frappe
from frappe.core.api.file import create_new_folder
import json
from frappe.realtime import publish_realtime
from frappe import _
from frappe import scrub
from frappe.desk.reportview import get_filters_cond, get_match_cond
from frappe.utils import nowdate

@frappe.whitelist()
def fn_doc_pdf_source_to_target(im_source_doc_type, im_source_doc_name, im_target_doc_type, im_target_doc_name, im_print_format=None, im_letter_head=None, im_languages=["en"], im_file_name=None):

    #if incoming languages is empty, but en as default  
    if im_languages is not ["en"]:
        if isinstance(im_languages, list):
            la_language_list = im_languages
        else:
            #make the incoming i_langs parameter to json
            #because when called from client side each char in the array is considered as language
            la_language_list = json.loads(im_languages)
    else:
        la_language_list = im_languages            

    #this will get the source doctype and create a folder in File/Home 
    #if the folder with the source doctype name is not there

    def fn_create_folder(im_folder, im_parent):
        ex_new_folder_name = "/".join([im_parent, im_folder])

        if not frappe.db.exists("File", ex_new_folder_name):
            create_new_folder(im_folder, im_parent)

        return ex_new_folder_name
    
    #check if the target doc_name has attachment
    #If true comeout of the api

    la_existing_files = frappe.get_all(
                        "File", 
                        filters={
                            "attached_to_doctype": im_target_doc_type,
                            "attached_to_name": im_target_doc_name
                        })
    if la_existing_files:
        return None

    ld_message = {} # Dictionary to store file objects
    
    for l_language in la_language_list:

        #set the global language as lang
        frappe.local.lang = l_language
        frappe.local.lang_full_dict = None       
        frappe.local.jenv = None

        try:
        #generate html and convert them into pdf
            l_html = frappe.get_print(im_source_doc_type, im_source_doc_name, print_format=im_print_format, letterhead=im_letter_head)
            l_binary_content =  frappe.utils.pdf.get_pdf(l_html)
            l_doctype_folder = fn_create_folder(im_target_doc_type, "Home")
            l_target_folder =  l_doctype_folder

            #logic for filename
            if im_file_name:
                l_file_name = im_file_name.replace("{language}", l_language) + ".pdf"
            else:
                l_file_name = f"{im_source_doc_name}-{l_language}.pdf"

           # Create and save the file
            lo_file = frappe.new_doc("File")
            lo_file.file_name = l_file_name
            lo_file.content = l_binary_content
            lo_file.folder = l_target_folder
            lo_file.is_private = 1
            lo_file.attached_to_doctype = im_target_doc_type
            lo_file.attached_to_name = im_target_doc_name
            lo_file.save()
            
            # Store the file object in the dictionary using the language as key
            ld_message[l_language] = lo_file       

        except Exception as e:
            frappe.message_log(f"Error saving PDF file for language {l_language}: {str(e)}")

    return ld_message


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def custom_item_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
	doctype = "Item"
	conditions = []

	if isinstance(filters, str):
		filters = json.loads(filters)

	# Get searchfields from meta and use in Item Link field query
	meta = frappe.get_meta(doctype, cached=True)
	searchfields = meta.get_search_fields()

	columns = ""
	extra_searchfields = [field for field in searchfields if field not in ["name", "description"]]

	if extra_searchfields:
		columns += ", " + ", ".join(extra_searchfields)

	if "description" in searchfields:
		columns += """, if(length(tabItem.description) > 40, \
			concat(substr(tabItem.description, 1, 40), "..."), description) as description"""

	searchfields = searchfields + [
		field
		for field in [searchfield or "name", "item_code", "item_group", "item_name"]
		if field not in searchfields
	]
	searchfields = " or ".join([field + " like %(txt)s" for field in searchfields])

	if filters and isinstance(filters, dict):
		if filters.get("customer") or filters.get("supplier"):
			party = filters.get("customer") or filters.get("supplier")
			item_rules_list = frappe.get_all(
				"Party Specific Item",
				filters={"party": party},
				fields=["restrict_based_on", "based_on_value"],
			)

			filters_dict = {}
			for rule in item_rules_list:
				if rule["restrict_based_on"] == "Item":
					rule["restrict_based_on"] = "name"
				filters_dict[rule.restrict_based_on] = []

			for rule in item_rules_list:
				filters_dict[rule.restrict_based_on].append(rule.based_on_value)

			for filter in filters_dict:
				filters[scrub(filter)] = ["in", filters_dict[filter]]

			if filters.get("customer"):
				del filters["customer"]
			else:
				del filters["supplier"]
		else:
			filters.pop("customer", None)
			filters.pop("supplier", None)

	description_cond = ""
	if frappe.db.count(doctype, cache=True) < 50000:
		# scan description only if items are less than 50000
		description_cond = "or tabItem.description LIKE %(txt)s"
	preferred_template = ""

	try:
		meta = frappe.get_meta("Quotation Presets")

		if meta.has_field("item_search_priority"):
			preferred_template = (
				frappe.db.get_single_value(
					"Quotation Presets",
					"item_search_priority",
				)
				or ""
			)

	except frappe.DoesNotExistError:
		pass
	return frappe.db.sql(
		"""select
			tabItem.name {columns}
		from tabItem
		where tabItem.docstatus < 2
			and tabItem.disabled=0
			and tabItem.has_variants=0
			and (tabItem.end_of_life > %(today)s or ifnull(tabItem.end_of_life, '0000-00-00')='0000-00-00')
			and ({scond} or tabItem.item_code IN (select parent from `tabItem Barcode` where barcode LIKE %(txt)s)
				{description_cond})
			{fcond} {mcond}
		order by
			case
				when ifnull(tabItem.variant_of, '') = %(preferred_template)s then 0
				else 1
			end,
			if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
			if(locate(%(_txt)s, item_name), locate(%(_txt)s, item_name), 99999),
			idx desc,
			name, item_name
		limit %(start)s, %(page_len)s """.format(
			columns=columns,
			scond=searchfields,
			fcond=get_filters_cond(doctype, filters, conditions).replace("%", "%%"),
			mcond=get_match_cond(doctype).replace("%", "%%"),
			description_cond=description_cond,
		),
		{
			"today": nowdate(),
			"txt": "%%%s%%" % txt,
			"_txt": txt.replace("%", ""),
			"start": start,
			"page_len": page_len,
			"preferred_template": preferred_template,
		},
		as_dict=as_dict,
	)