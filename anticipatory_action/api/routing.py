"""Host-scoped web routing for the Anticipatory Action subdomain.

This is hard-coded to a single host, ``anticipatoryaction.ndoc.go.ke``, and does
nothing on any other host. That is deliberate: the app runs on a shared site with
several subdomains, so it must never change where the main URL or any other
subdomain lands. All behaviour here is a no-op unless the request host matches
exactly.
"""

import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect as _wz_redirect

# The only host this module ever acts on.
AA_HOST = "anticipatoryaction.ndoc.go.ke"


class _Redirect302(HTTPException):
	"""A 302 redirect that Frappe's ``application()`` returns cleanly.

	``frappe.Redirect`` is only handled by the website render path, NOT by the
	``before_request`` hook chain, so raising it here would fall through to the
	generic exception handler and be logged as a traceback. ``application()`` does
	have ``except HTTPException: return e``, so raising a real HTTPException gives
	a clean, un-logged 302.
	"""

	code = 302

	def __init__(self, location):
		super().__init__()
		self._location = location

	def get_response(self, environ=None, scope=None):
		return _wz_redirect(self._location, 302)

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

	Two responsibilities, both safe on the shared multi-subdomain site:

	1. (any host) A *confined* AA account — one that only holds AA roles, see
	   ``_is_pure_aa_user`` — must never see the Frappe desk. Any ``/app`` request
	   from such a user is bounced to their web portal/admin. System Managers and
	   users of other subdomains (e.g. redhive) are never "pure AA", so they keep
	   full desk access untouched.
	2. (AA subdomain only) The bare home page goes to the AA experience: a
	   signed-in member (including someone who just completed a password reset)
	   lands on ``/aa-portal``; everyone else lands on the public ``/aa`` page.

	Anything not matched here returns immediately and changes nothing.
	"""
	try:
		req = getattr(frappe.local, "request", None)
		if not req:
			return
		path = (req.path or "/").rstrip("/") or "/"
		user = getattr(frappe.session, "user", "Guest")

		# 1. Keep confined AA users out of the Frappe desk. Host-independent, but
		#    gated on _is_pure_aa_user so nothing else on the shared site (other
		#    subdomains, System Managers) is ever affected. get_landing() returns
		#    /aa-admin or /aa-portal for these accounts, so there is no loop.
		if user and user != "Guest" and (path == "/app" or path.startswith("/app/")):
			from anticipatory_action.api.permissions import _is_pure_aa_user
			if _is_pure_aa_user(user):
				from anticipatory_action.api.portal import get_landing
				raise _Redirect302(get_landing())

		# 2. AA-subdomain home-page routing.
		host = (req.host or "").split(":")[0].lower()
		if host != AA_HOST:
			return  # not our subdomain -> leave the request completely untouched
		if path != "/":
			return  # only the bare home page is redirected
		if user and user != "Guest" and _is_aa_member():
			raise _Redirect302("/aa-portal")
		raise _Redirect302("/aa")
	except _Redirect302:
		raise
	except Exception:
		# Routing must never break a request; if anything is off, do nothing.
		return
