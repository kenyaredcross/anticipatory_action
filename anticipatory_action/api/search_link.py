import frappe
from frappe.desk.search import search_link

@frappe.whitelist(allow_guest = True)
def search_link_fields(doctype, txt, filters=None, page_length=20):
    link_fields = ["County", "Sub County"]

    if doctype not in link_fields:
        frappe.throw("Not Allowed", frappe.PermissionError)

    return search_link(doctype, txt, filters, page_length)