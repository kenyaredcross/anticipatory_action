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
	# Approvers and admins both reach the /aa-admin console (approvers get a reduced,
	# review-only tab set) - surface the link to them on the member portal so they can
	# get to it even when they land on the portal.
	context.is_reviewer = context.is_admin or "Anticipatory Action Approver" in roles
	# Approvers reach the review console via /aa-admin; only true desk users (System
	# Managers) see the raw Frappe desk link. AA Approvers and Users never do.
	context.is_system_manager = "System Manager" in roles
	context.csrf_token = frappe.sessions.get_csrf_token()
