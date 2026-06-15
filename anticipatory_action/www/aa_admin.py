import frappe
from frappe.utils import get_fullname


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/anticipatory-login?redirect-to=/aa-admin"
		raise frappe.Redirect

	if not ({"Anticipatory Action Admin", "System Manager"} & set(frappe.get_roles())):
		# Authenticated but not an admin — send them to the member portal.
		frappe.local.flags.redirect_location = "/aa-portal"
		raise frappe.Redirect

	context.full_name = get_fullname(frappe.session.user)
	context.is_admin = True
	context.csrf_token = frappe.sessions.get_csrf_token()
