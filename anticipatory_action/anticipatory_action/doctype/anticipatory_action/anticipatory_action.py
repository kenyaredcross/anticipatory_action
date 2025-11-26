# Copyright (c) 2025, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AnticipatoryAction(Document):
	pass


@frappe.whitelist()
def get_subcounties(doctype, txt, searchfield, start, page_len, filters):
    county = filters.get("county")
    if not county:
        return []

    return frappe.db.get_all(
        "Sub County",
        filters={"county": county},  # Only subcounties linked to this county
        fields=["name"],
        as_list=True
    )
