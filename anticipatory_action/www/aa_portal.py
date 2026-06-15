import frappe
from frappe.utils import get_fullname


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/anticipatory-login?redirect-to=/aa-portal"
		raise frappe.Redirect

	roles = set(frappe.get_roles())
	context.full_name = get_fullname(frappe.session.user)
	context.is_admin = bool({"Anticipatory Action Admin", "System Manager"} & roles)
	context.csrf_token = frappe.sessions.get_csrf_token()
