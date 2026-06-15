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
			aa_roles = {"Anticipatory Action User", "Anticipatory Action Admin"} & set(frappe.get_roles())
			if aa_roles:
				# AA accounts land on their portal (role_home_page), not the desk.
				redirect_to = get_home_page()
			elif frappe.session.data.user_type == "Website User":
				redirect_to = get_default_path() or get_home_page()
			else:
				redirect_to = get_default_path() or "/app"
		if redirect_to and not redirect_to.startswith("/"):
			redirect_to = "/" + redirect_to
		frappe.local.flags.redirect_location = redirect_to
		raise frappe.Redirect

	context.redirect_to = redirect_to or ""
