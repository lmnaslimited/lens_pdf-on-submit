import frappe
from frappe.core.api.file import create_new_folder
import json
from frappe.realtime import publish_realtime
from frappe import _

from frappe import scrub
from frappe.desk.reportview import get_filters_cond, get_match_cond
from frappe.utils import cint, nowdate


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

def fn_get_item_search_configuration():
	"""Fetch configured Item template priority sequence from Quotation Presets."""

	try:
		# Check whether Quotation Presets doctype and child table field exist
		ld_quo_presets_meta = frappe.get_meta("Quotation Presets")

		# Validate whether Item search Sort Order child table field exists
		if not ld_quo_presets_meta.has_field("item_search_sort_order"):
			return []

		# Fetch child table metadata to ensure referenced doctype exists
		l_child_doctype = ld_quo_presets_meta.get_field(
			"item_search_sort_order"
		).options

		if not frappe.db.exists("DocType", l_child_doctype):
			return []
		
		# Fetch Item template priority order based on child table row sequence (idx)
		return frappe.get_all(
			l_child_doctype,
			filters={"parent": "Quotation Presets"},
			fields=["item_template","is_catalog_item", "idx"],
			order_by="idx asc",
		)

	# Ignore error if Quotation Presets doctype does not exist
	except frappe.DoesNotExistError:
		return []
	
def fn_get_priority_order_clause(ia_item_search_priority, i_txt):
	"""
	Generate SQL CASE condition for Item priority ordering.

	Two-condition priority:
	  Condition 1 (best):     variant_of matches the configured template AND
	                          (if configured) is_catalog_item is also set.
	  Condition 2 (fallback): variant_of matches the configured template,
	                          but the catalog-item flag requirement isn't met.
	                          Still ranked ahead of items whose template
	                          isn't configured at all.
	"""

	if not (ia_item_search_priority and i_txt.strip("%")):
		return ""

	# Guarantees every Condition 1 match outranks every Condition 2 match,
	# regardless of how many priority rows are configured — offset always
	# exceeds the highest possible idx in this list.
	CONDITION2_OFFSET = len(ia_item_search_priority) + 1

	la_case_conditions = []
	la_processed_rules = set()

	for ld_row in ia_item_search_priority:
		if not ld_row.item_template:
			continue

		l_rule = (ld_row.item_template, cint(ld_row.is_catalog_item))
		if l_rule in la_processed_rules:
			continue
		la_processed_rules.add(l_rule)

		l_template_cond = (
			f"ifnull(tabItem.variant_of, '') = "
			f"{frappe.db.escape(ld_row.item_template)}"
		)

		if ld_row.is_catalog_item:
			# Condition 1 checks template + catalog flag both match
			la_case_conditions.append(f"""
				when {l_template_cond}
					and ifnull(tabItem.is_catalog_item, 0) = 1
					and tabItem.item_name like %(txt)s
				then {ld_row.idx}
			""")
			# Condition 2 checks right template, catalog flag not set on this item —
			# still better than an unconfigured template .
			la_case_conditions.append(f"""
				when {l_template_cond}
					and tabItem.item_name like %(txt)s
				then {CONDITION2_OFFSET + ld_row.idx}
			""")
		else:
			# No catalog requirement configured — template match alone is Tier 1.
			la_case_conditions.append(f"""
				when {l_template_cond}
					and tabItem.item_name like %(txt)s
				then {ld_row.idx}
			""")

	if not la_case_conditions:
		return ""

	return f"""
		case
			{' '.join(la_case_conditions)}
			else 999
		end,
	"""
	

'''
Custom Item search query used to prioritize Item search results
based on the Item Search Sort Order configuration maintained in
Quotation Presets.

The priority configuration is managed through a child table,
where the child row sequence (idx) determines Item search Sort.
This allows users to control preferred Item template
ordering directly from the UI without modifying code.

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

	# Fetch Item search Sort Order configuration from Quotation Presets
	# to prioritize preferred Item template variants in search results
	la_item_search_priority = fn_get_item_search_configuration()

	l_order_priority = fn_get_priority_order_clause(
		la_item_search_priority,
		txt
	)
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
			if(tabItem.item_name like %(txt)s, 1, 2),
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
		},
		as_dict=as_dict,
	)