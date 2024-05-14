import frappe
from frappe.core.api.file import create_new_folder
import json
from frappe.realtime import publish_realtime
from frappe import _

@frappe.whitelist()
def fn_doc_pdf_source_to_target(im_source_doc_type, im_source_doc_name, im_target_doc_type, im_target_doc_name, im_print_format=None, im_letter_head=None, im_languages=["en"]):

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

            lo_file = frappe.new_doc("File")
            lo_file.file_name = f"{im_source_doc_name}-{l_language}.pdf"
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
