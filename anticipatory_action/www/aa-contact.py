import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.success = False
	context.error = None


@frappe.whitelist(allow_guest=True)
def submit_contact(full_name, email, organization, phone, subject, message):
	try:
		doc = frappe.get_doc({
			"doctype": "AA Contact Message",
			"full_name": full_name,
			"email": email,
			"organization": organization,
			"phone": phone,
			"subject": subject,
			"message": message,
			"status": "New"
		})
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return {"success": True}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "AA Contact Form Error")
		return {"success": False, "error": str(e)}
