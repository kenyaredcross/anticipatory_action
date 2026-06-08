import frappe
from frappe.apps import get_default_path
from frappe.website.utils import get_home_page
from frappe.www.login import sanitize_redirect


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	# Only honour same-origin redirect targets (guards against open redirects).
	redirect_to = sanitize_redirect(frappe.local.request.args.get("redirect-to"))

	# Already authenticated? Skip the login screen and send them onward.
	if frappe.session.user and frappe.session.user != "Guest":
		if not redirect_to:
			if frappe.session.data.user_type == "Website User":
				redirect_to = get_default_path() or get_home_page()
			else:
				redirect_to = get_default_path() or "/app"
		frappe.local.flags.redirect_location = redirect_to
		raise frappe.Redirect

	context.redirect_to = redirect_to or ""
