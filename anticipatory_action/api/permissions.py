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
	the full submission queue (not scoped to their own records)."""
	return bool(REVIEW_ROLES & set(frappe.get_roles(user or frappe.session.user)))


def aa_query_conditions(user=None):
	"""SQL WHERE fragment restricting non-admins to records they own."""
	user = user or frappe.session.user
	if _can_review(user) or user == "Guest":
		return ""
	return f"`tabAnticipatory Action`.`owner` = {frappe.db.escape(user)}"


def aa_has_permission(doc, ptype=None, user=None):
	"""Deny non-admins access to submissions they don't own.

	Returns None to defer to the normal role-based check (for admins, guests,
	and the owner), and False to actively deny everyone else.
	"""
	user = user or frappe.session.user
	if _can_review(user) or user == "Guest":
		return None
	return None if getattr(doc, "owner", None) == user else False


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
