import frappe


def get_context(context):
	context.no_cache = 1

	# Reporting an anticipatory action requires a sign-in. Send guests to the
	# branded login and bring them straight back to the form afterwards.
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/anticipatory-login?redirect-to=/anticipatory-action"
		raise frappe.Redirect

	context.is_logged_in = True
