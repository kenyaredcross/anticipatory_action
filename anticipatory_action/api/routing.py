"""Host-scoped web routing for the Anticipatory Action subdomain.

This is hard-coded to a single host, ``anticipatoryaction.ndoc.go.ke``, and does
nothing on any other host. That is deliberate: the app runs on a shared site with
several subdomains, so it must never change where the main URL or any other
subdomain lands. All behaviour here is a no-op unless the request host matches
exactly.
"""

import frappe

# The only host this module ever acts on.
AA_HOST = "anticipatoryaction.ndoc.go.ke"

AA_ROLES = {
	"Anticipatory Action User",
	"Anticipatory Action Approver",
	"Anticipatory Action Admin",
}


def _is_aa_member():
	try:
		return bool(AA_ROLES & set(frappe.get_roles()))
	except Exception:
		return False


def route_subdomain():
	"""before_request hook.

	On the AA subdomain only, send the bare home page to the AA experience:

	* a signed-in member (including someone who has just completed a password
	  reset and been logged in) lands on their dashboard, ``/aa-portal``;
	* everyone else lands on the public AA page, ``/aa``.

	On every other host this returns immediately and changes nothing.
	"""
	dest = None
	try:
		req = getattr(frappe.local, "request", None)
		if not req:
			return
		host = (req.host or "").split(":")[0].lower()
		if host != AA_HOST:
			return  # not our subdomain -> leave the request completely untouched

		path = (req.path or "/").rstrip("/") or "/"
		if path != "/":
			return  # only the bare home page is redirected

		user = getattr(frappe.session, "user", "Guest")
		if user and user != "Guest" and _is_aa_member():
			dest = "/aa-portal"
		else:
			dest = "/aa"
	except Exception:
		# Routing must never break a request; if anything is off, do nothing.
		return

	if dest:
		frappe.local.flags.redirect_location = dest
		raise frappe.Redirect
