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


'''
Custom Item search query used to prioritize Item search results
based on the preferred "Item Search Priority" configured in
Quotation Presets.
This helps users see preferred Item first
during Item selection in transactions.

Implemenation:
refer: https://github.com/frappe/erpnext/blob/v15.91.1/erpnext/controllers/queries.py#L175-L270

The standard ERPNext item_query implementation is reused with an
additional CASE condition in ORDER BY to prioritize matching
preferred Item templates first in search results.

If no preferred template is configured, the query follows the
default ERPNext Item ordering behavior.
'''
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def custom_item_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
	# Force query execution on Item doctype regardless of incoming doctype
	l_doctype = "Item"
	la_conditions = [] # Store additional query conditions dynamically if needed

	# Convert filters from JSON string to dictionary format for processing
	if isinstance(filters, str):
		filters = json.loads(filters)

	# Get searchfields from meta and use in Item Link field query
	ld_doctype_meta = frappe.get_meta(l_doctype, cached=True)
	la_searchfields = ld_doctype_meta.get_search_fields()

	l_columns = ""
	# Exclude default fields from extra selectable columns
	la_extra_searchfields = [l_field for l_field in la_searchfields if l_field not in ["name", "description"]]

	# Include additional search fields in query result columns
	# to improve Link field visibility and user selection experience
	if la_extra_searchfields:
		l_columns += ", " + ", ".join(la_extra_searchfields)

	# Truncate long Item descriptions in dropdown results
	# to keep Link field search results clean and readable
	if "description" in la_searchfields:
		l_columns += """, if(length(tabItem.description) > 40, \
			concat(substr(tabItem.description, 1, 40), "..."), description) as description"""

	# Build dynamic search conditions using configured Item search fields
	# so Item lookup remains flexible and metadata-driven
	la_searchfields = la_searchfields + [
		l_field
		for l_field in [searchfield or "name", "item_code", "item_group", "item_name"]
		if l_field not in la_searchfields
	]
	# Generate SQL LIKE conditions for all searchable fields
	la_searchfields = " or ".join([l_field + " like %(txt)s" for l_field in la_searchfields])

	if filters and isinstance(filters, dict):
		# Apply Party Specific Item restrictions
		# so users can search only Items mapped to the selected customer/supplier
		if filters.get("customer") or filters.get("supplier"):
			l_party = filters.get("customer") or filters.get("supplier")
			# Fetch Party Specific Item rules configured for the selected party
			la_item_rules_list = frappe.get_all(
				"Party Specific Item",
				filters={"party": l_party},
				fields=["restrict_based_on", "based_on_value"],
			)

			ld_filters_dict = {}
			for ld_rule in la_item_rules_list:
				# Convert Item restriction into Item name filtering
				# because Item master records are stored using the Item document name
				if ld_rule["restrict_based_on"] == "Item":
					ld_rule["restrict_based_on"] = "name"
				ld_filters_dict[ld_rule.restrict_based_on] = []

			# Group all allowed values under their corresponding restriction field
			for ld_rule in la_item_rules_list:
				ld_filters_dict[ld_rule.restrict_based_on].append(ld_rule.based_on_value)

			# Inject dynamically prepared filters into query filters
			for l_filter in ld_filters_dict:
				filters[scrub(l_filter)] = ["in", ld_filters_dict[l_filter]]

			# Remove customer/supplier filters after converting them into Item restrictions
			# to avoid invalid conditions in Item query execution
			if filters.get("customer"):
				del filters["customer"]
			else:
				del filters["supplier"]
		else:
			# Remove unused customer/supplier filters to avoid unwanted query conditions
			filters.pop("customer", None)
			filters.pop("supplier", None)

	l_description_cond = ""
	# Enable description search only for smaller Item datasets
	# to avoid expensive full table scans and maintain search performance
	if frappe.db.count(l_doctype, cache=True) < 50000:
		# scan description only if items are less than 50000
		l_description_cond = "or tabItem.description LIKE %(txt)s"

	# Fetch preferred Item template from Quotation Presets
	# to prioritize preferred Item variants in search results
	l_preferred_item_template = ""

	try:
		# Check whether Quotation Presets doctype and field exist
		ld_quo_presets_meta = frappe.get_meta("Quotation Presets")

		if ld_quo_presets_meta.has_field("item_search_priority"):
			l_preferred_item_template = (
				frappe.db.get_single_value(
					"Quotation Presets",
					"item_search_priority",
				)
				or ""
			)
	# Ignore error if Quotation Presets doctype does not exist
	except frappe.DoesNotExistError:
		pass

	l_order_priority = ""
	# Apply custom ordering only when a preferred Item template is configured
	# to avoid unnecessary ordering conditions in the query
	if l_preferred_item_template:
		l_order_priority = """
			case
				when ifnull(tabItem.variant_of, '') = %(l_preferred_item_template)s then 0
				else 1
			end,
		"""
	return frappe.db.sql(
		"""select
			tabItem.name {l_columns}
		from tabItem
		where tabItem.docstatus < 2
			and tabItem.disabled=0
			and tabItem.has_variants=0
			and (tabItem.end_of_life > %(today)s or ifnull(tabItem.end_of_life, '0000-00-00')='0000-00-00')
			and ({scond} or tabItem.item_code IN (select parent from `tabItem Barcode` where barcode LIKE %(txt)s)
				{l_description_cond})
			{fcond} {mcond}
		order by
			{l_order_priority}
			if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
			if(locate(%(_txt)s, item_name), locate(%(_txt)s, item_name), 99999),
			idx desc,
			name, item_name
		limit %(start)s, %(page_len)s """.format(
			l_columns=l_columns,
			scond=la_searchfields,
			fcond=get_filters_cond(l_doctype, filters, la_conditions).replace("%", "%%"),
			mcond=get_match_cond(l_doctype).replace("%", "%%"),
			l_description_cond=l_description_cond,
			l_order_priority=l_order_priority,
		),
		{
			"today": nowdate(),
			"txt": "%%%s%%" % txt,
			"_txt": txt.replace("%", ""),
			"start": start,
			"page_len": page_len,
			"l_preferred_item_template": l_preferred_item_template,
		},
		as_dict=as_dict,
	)