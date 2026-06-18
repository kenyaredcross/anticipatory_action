import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	# Already signed in? No need to request access.
	if frappe.session.user and frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/aa-portal"
		raise frappe.Redirect

	# Policy / terms documents an admin has published (managed under the admin
	# Policy & Terms tab). Shown on the sign-up page so applicants can read them,
	# and the acceptance line links to the Terms & Conditions document.
	policies = frappe.get_all(
		"AA Policy Document",
		filters={"published": 1},
		fields=["title", "policy_type", "attachment", "link", "display_order"],
		order_by="display_order asc, creation asc",
		limit=50,
	)
	for p in policies:
		p["url"] = p.get("link") or p.get("attachment") or "#"
	context.policies = policies
	terms = next((p for p in policies if p.get("policy_type") == "Terms & Conditions"), None)
	context.terms_url = (terms or {}).get("url")
