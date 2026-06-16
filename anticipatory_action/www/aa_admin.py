import frappe
from frappe.utils import get_fullname


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/anticipatory-login?redirect-to=/aa-admin"
		raise frappe.Redirect

	roles = set(frappe.get_roles())
	is_admin = bool({"Anticipatory Action Admin", "System Manager"} & roles)
	is_approver = "Anticipatory Action Approver" in roles

	if not (is_admin or is_approver):
		# Authenticated but neither admin nor approver — send them to the portal.
		frappe.local.flags.redirect_location = "/aa-portal"
		raise frappe.Redirect

	context.full_name = get_fullname(frappe.session.user)
	# Full admins manage users, organizations and sign-up requests; approvers
	# only review submissions and curate content. The template hides the tabs an
	# approver can't use; every API is independently guarded server-side too.
	context.is_admin = is_admin
	context.is_approver = is_approver and not is_admin
	context.can_manage_users = is_admin
	context.is_system_manager = "System Manager" in roles
	context.csrf_token = frappe.sessions.get_csrf_token()
