import frappe


def get_context(context):
	context.no_cache = 1
	# Logged-in members get a portal-aware experience (edit drafts, return to
	# their dashboard); guests keep the public submit-and-redirect flow.
	context.is_logged_in = frappe.session.user != "Guest"
