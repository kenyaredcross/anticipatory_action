import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	# Already signed in? No need to request access.
	if frappe.session.user and frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/aa-portal"
		raise frappe.Redirect
