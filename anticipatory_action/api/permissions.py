"""Row-level scoping for Anticipatory Action submissions.

AA participants are System Users, so they *could* reach the desk. These hooks
make sure a non-admin only ever sees their own submissions — in the desk list,
in reports, and when opening a document directly — while admins keep the full
operational picture.

Wired in hooks.py via `permission_query_conditions` and `has_permission`.
"""

import frappe

# Full administrators — manage users, organizations and sign-up approvals.
ADMIN_ROLES = {"Anticipatory Action Admin", "System Manager"}

# The middle "Approver" role: reviews submissions and curates content
# (reports, activities, publications, messages) but cannot manage users,
# organizations, sign-up requests or assign roles.
APPROVER_ROLE = "Anticipatory Action Approver"

# Everyone who may see/act on every submission (the review queue).
REVIEW_ROLES = ADMIN_ROLES | {APPROVER_ROLE}


def _is_admin(user=None):
	return bool(ADMIN_ROLES & set(frappe.get_roles(user or frappe.session.user)))


def _can_review(user=None):
	"""Admins, System Managers and Approvers — anyone allowed to see and act on
	the submission queue (an Approver only within their own organization; admins
	across every organization — see ``reviewer_owner_scope``)."""
	return bool(REVIEW_ROLES & set(frappe.get_roles(user or frappe.session.user)))


# ---------------------------------------------------------------------------
# Organisation scoping — an Approver reviews only the submissions of their own
# organization. A submission's organization is the organization of its owner
# (the member who filed it); the link is owner (User) -> roster
# (Anticipatory Action User) -> organization. Full admins / System Managers are
# never scoped.
# ---------------------------------------------------------------------------

def _user_org(user=None):
	"""The AA organization a roster account belongs to, or None when the account
	is not on the roster / has no organization set."""
	user = user or frappe.session.user
	if user in ("Guest", "Administrator"):
		return None
	org = frappe.db.get_value("Anticipatory Action User", {"user": user}, "organization")
	if not org:
		org = frappe.db.get_value("Anticipatory Action User", {"email": user}, "organization")
	return org or None


def _org_logins(org):
	"""Every login account (User name + email) of the roster members of ``org`` —
	the set of possible submission ``owner`` values for that organization."""
	logins = set()
	if not org:
		return logins
	for r in frappe.get_all(
		"Anticipatory Action User",
		filters={"organization": org},
		fields=["user", "email"],
	):
		if r.user:
			logins.add(r.user)
		if r.email:
			logins.add(r.email)
	return logins


def reviewer_owner_scope(user=None):
	"""The submission ``owner`` values a user is allowed to see/act on.

	* ``None``  — no restriction (full admins and System Managers see every
	  organization's submissions).
	* a ``set`` — the owners the user is confined to:
	    - an Approver: every roster member of their own organization (plus
	      themselves), so they review only their organization's submissions;
	    - anyone else: only their own submissions.
	"""
	user = user or frappe.session.user
	if _is_admin(user):
		return None
	if APPROVER_ROLE in set(frappe.get_roles(user)):
		logins = _org_logins(_user_org(user))
		logins.add(user)
		return logins
	return {user}


def aa_query_conditions(user=None):
	"""SQL WHERE fragment scoping the caller to the submissions they may see."""
	user = user or frappe.session.user
	if user == "Guest":
		return ""
	scope = reviewer_owner_scope(user)
	if scope is None:
		return ""  # admins / System Managers — the full picture
	owners = ", ".join(frappe.db.escape(o) for o in sorted(scope))
	return f"`tabAnticipatory Action`.`owner` in ({owners})"


def aa_has_permission(doc, ptype=None, user=None):
	"""Deny access to submissions outside the caller's scope.

	Returns None to defer to the normal role-based check (for admins, guests, and
	in-scope records), and False to actively deny everything else.
	"""
	user = user or frappe.session.user
	if user == "Guest":
		return None
	scope = reviewer_owner_scope(user)
	if scope is None:
		return None
	return None if getattr(doc, "owner", None) in scope else False


# ---------------------------------------------------------------------------
# User doctype scoping — a "pure" AA account (only AA + default roles, no
# System Manager / other-project roles) is a confined desk user. It must not be
# able to browse everyone else's accounts, so it only ever sees its own User
# record. Other users (System Managers, other projects) are untouched.
# ---------------------------------------------------------------------------

AA_ONLY_ROLES = {"Anticipatory Action User", "Anticipatory Action Admin", APPROVER_ROLE}
_DEFAULT_ROLES = {"All", "Guest", "Desk User"}


def _is_pure_aa_user(user):
	if user in ("Guest", "Administrator"):
		return False
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return False
	aa = roles & AA_ONLY_ROLES
	return bool(aa) and not (roles - aa - _DEFAULT_ROLES)


def user_query_conditions(user=None):
	user = user or frappe.session.user
	if _is_pure_aa_user(user):
		return f"`tabUser`.`name` = {frappe.db.escape(user)}"
	return ""


def user_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if _is_pure_aa_user(user):
		return getattr(doc, "name", None) == user
	return None


# ---------------------------------------------------------------------------
# After-login routing — send AA members/admins to their web portal whatever
# login path they use, WITHOUT changing where anyone else lands. System
# Managers and other-project users are left on their normal destination.
# Wired via the `on_session_creation` hook; the redirect is consumed by Frappe
# in set_user_info (response["redirect_to"]).
# ---------------------------------------------------------------------------

def route_aa_user_after_login(login_manager=None):
	user = getattr(login_manager, "user", None) or frappe.session.user
	if user in ("Administrator", "Guest"):
		return
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return  # general admins keep their normal landing
	if {"Anticipatory Action Admin", APPROVER_ROLE} & roles:
		dest = "/aa-admin"
	elif "Anticipatory Action User" in roles:
		dest = "/aa-portal"
	else:
		return  # not an AA account — don't touch
	frappe.cache.hset("redirect_after_login", user, dest)
