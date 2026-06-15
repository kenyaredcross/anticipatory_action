"""Row-level scoping for Anticipatory Action submissions.

AA participants are System Users, so they *could* reach the desk. These hooks
make sure a non-admin only ever sees their own submissions — in the desk list,
in reports, and when opening a document directly — while admins keep the full
operational picture.

Wired in hooks.py via `permission_query_conditions` and `has_permission`.
"""

import frappe

# Roles that get to see every submission.
ADMIN_ROLES = {"Anticipatory Action Admin", "System Manager"}


def _is_admin(user=None):
	return bool(ADMIN_ROLES & set(frappe.get_roles(user or frappe.session.user)))


def aa_query_conditions(user=None):
	"""SQL WHERE fragment restricting non-admins to records they own."""
	user = user or frappe.session.user
	if _is_admin(user) or user == "Guest":
		return ""
	return f"`tabAnticipatory Action`.`owner` = {frappe.db.escape(user)}"


def aa_has_permission(doc, ptype=None, user=None):
	"""Deny non-admins access to submissions they don't own.

	Returns None to defer to the normal role-based check (for admins, guests,
	and the owner), and False to actively deny everyone else.
	"""
	user = user or frappe.session.user
	if _is_admin(user) or user == "Guest":
		return None
	return None if getattr(doc, "owner", None) == user else False


# ---------------------------------------------------------------------------
# User doctype scoping — a "pure" AA account (only AA + default roles, no
# System Manager / other-project roles) is a confined desk user. It must not be
# able to browse everyone else's accounts, so it only ever sees its own User
# record. Other users (System Managers, other projects) are untouched.
# ---------------------------------------------------------------------------

AA_ONLY_ROLES = {"Anticipatory Action User", "Anticipatory Action Admin"}
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
