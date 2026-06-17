import frappe


def get_context(context):
	context.no_cache = 1

	# Guests may now fill the whole form (online-shopping "checkout" style): they
	# are only asked to create an account or sign in at the final submit step.
	is_guest = frappe.session.user == "Guest"
	context.is_logged_in = not is_guest

	if is_guest:
		context.reporter_name = ""
		context.reporter_email = ""
		context.reporter_phone = ""
		return

	# Pre-fill the reporter fields from the signed-in user's profile (and the AA
	# roster as a phone fallback) so members don't retype who they are. Editing a
	# saved draft overrides these client-side with the draft's own values.
	u = frappe.db.get_value(
		"User", frappe.session.user, ["full_name", "email", "phone", "mobile_no"], as_dict=True
	) or {}
	roster_phone = (
		frappe.db.get_value("Anticipatory Action User", {"user": frappe.session.user}, "phone")
		or frappe.db.get_value("Anticipatory Action User", {"email": frappe.session.user}, "phone")
	)
	context.reporter_name = u.get("full_name") or ""
	context.reporter_email = u.get("email") or frappe.session.user
	context.reporter_phone = u.get("phone") or u.get("mobile_no") or roster_phone or ""
