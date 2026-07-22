"""Portal & admin API for the Anticipatory Action self-service experience.

Every privileged action lives here behind an explicit role / ownership guard
and runs under ``ignore_permissions`` *after* that guard. This module — not the
desk permission rules — is the trust boundary for the portal:

* AA participants edit only their own submissions and profile.
* AA Admins manage only the AA roster (never the global User list), never see
  or touch users from the other projects on this shared site, and can never
  grant a role outside the two AA roles (so never System Manager).
"""

import contextlib

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import sanitize_html, strip_html

from anticipatory_action.api.anticipatory_action import _sanitize
from anticipatory_action.api.aa_email import (
	AA_INBOX,
	aa_email_html,
	aa_sendmail,
	send_submission_rejected,
	send_submission_replied,
)
from anticipatory_action.api.permissions import _can_review, _is_admin, _user_org, reviewer_owner_scope

# The roles an AA account may hold. "Approver" sits between User and Admin:
# it can clear the submission queue and curate content, but not manage users,
# organizations or sign-ups.
AA_ROLES = {
	"Anticipatory Action User",
	"Anticipatory Action Approver",
	"Anticipatory Action Admin",
}

# Roles every (system) user picks up by default — ignored when deciding whether
# an account "belongs" to another project.
_DEFAULT_ROLES = {"All", "Guest", "Desk User"}


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _require_login():
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in to continue.", frappe.PermissionError)


def _require_admin():
	"""Full admin only — user, organization and sign-up management."""
	_require_login()
	if not _is_admin():
		frappe.throw("You are not authorised to perform this action.", frappe.PermissionError)


def _require_approver():
	"""Approver or Admin — submission review and content curation."""
	_require_login()
	if not _can_review():
		frappe.throw("You are not authorised to perform this action.", frappe.PermissionError)


def _can_approve_accounts(user=None):
	"""May the user act on sign-up / account requests? Full admins always can; an
	Approver may too once an admin grants them the capability (the roster's
	``can_approve_accounts`` flag)."""
	user = user or frappe.session.user
	if _is_admin(user):
		return True
	flag = frappe.db.get_value("Anticipatory Action User", {"user": user}, "can_approve_accounts")
	if flag is None:
		flag = frappe.db.get_value("Anticipatory Action User", {"email": user}, "can_approve_accounts")
	return bool(flag)


def _require_account_approver():
	"""Full admin, or an Approver who has been granted the account-approval
	capability — used for the sign-up request queue."""
	_require_login()
	if not _can_approve_accounts():
		frappe.throw("You are not authorised to perform this action.", frappe.PermissionError)


def _assert_submission_in_scope(doc_or_name):
	"""An Approver may only view/act on submissions from their own organization;
	full admins and System Managers see every submission. A submission's
	organization is the organization of its owner (the member who filed it).
	Raises PermissionError when the submission is out of scope."""
	scope = reviewer_owner_scope()
	if scope is None:
		return  # admin — unrestricted
	owner = (doc_or_name.owner if hasattr(doc_or_name, "owner")
			 else frappe.db.get_value("Anticipatory Action", doc_or_name, "owner"))
	if owner not in scope:
		frappe.throw(
			"This submission belongs to another organization.",
			frappe.PermissionError,
		)


def _constrain_role(role):
	if role not in AA_ROLES:
		frappe.throw("Invalid role.", frappe.PermissionError)
	return role


def _can_set_role():
	"""Who may decide a member's role. System Managers and AA Admins both can.
	The value is always passed through ``_constrain_role`` so it can never be set
	to anything outside the three AA roles (so never System Manager) — an AA Admin
	can move someone between User / Approver / Admin but never escalate beyond AA."""
	return bool({"System Manager", "Anticipatory Action Admin"} & set(frappe.get_roles()))


def _foreign_roles(user):
	"""Roles held by ``user`` that aren't AA roles or universal defaults."""
	if not user or not frappe.db.exists("User", user):
		return set()
	return set(frappe.get_roles(user)) - AA_ROLES - _DEFAULT_ROLES


def _assert_is_aa_user(name):
	"""Ensure ``name`` is a genuine AA roster record whose login account is not
	shared with another project. Returns the roster's (email, user)."""
	if not frappe.db.exists("Anticipatory Action User", name):
		frappe.throw("Unknown Anticipatory Action user.", frappe.PermissionError)
	roster = frappe.db.get_value(
		"Anticipatory Action User", name, ["email", "user"], as_dict=True
	)
	target = roster.user or roster.email
	if _foreign_roles(target):
		frappe.throw(
			"This account is managed elsewhere and cannot be modified here.",
			frappe.PermissionError,
		)
	return roster


@contextlib.contextmanager
def _elevated():
	"""Run a privileged account mutation as Administrator.

	Frappe's User controller performs nested writes (notification settings,
	session cleanup) that fail for a non-System-Manager even under
	``ignore_permissions``. We only enter this *after* the AA-admin and scoping
	guards have already passed as the real caller — and the role value is always
	constrained to the two AA roles — so an AA Admin still can never escalate a
	user or touch a foreign account; this only lets the mechanical write through.
	"""
	original = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(original)


@frappe.whitelist()
def get_landing():
	"""Where an AA account should go after signing in.

	The login API hardcodes ``/app`` for System Users (ignoring role_home_page),
	so the branded login page asks us instead.
	"""
	roles = set(frappe.get_roles())
	if {"Anticipatory Action Admin", "System Manager", "Anticipatory Action Approver"} & roles:
		return "/aa-admin"
	if "Anticipatory Action User" in roles:
		return "/aa-portal"
	return "/app"


# ===========================================================================
# USER-FACING
# ===========================================================================

# Parent fields a reporter may set on their own submission.
_PARENT_FIELDS = (
	"implementing_organization", "entity_or_organization_type", "other_organization_entity",
	"funding_source", "reporting_person", "reporter_email", "reporter_phone_number",
	"anticipated_hazard", "other_anticipated_hazards", "implementing_partners",
	"other_implementing_partners", "activation_start_date", "activation_end_date",
	"triggers_and_thresholds", "lessons_learnt", "challenges", "recommendations",
	"supporting_materials", "email_me_a_copy",
)

_DETAIL_FIELDS = (
	"name", "subcounty_level", "county", "subcounty", "sector",
	"number_of_livestock_targeted", "number_of_wildlife_targeted",
	"amount_for_anticipatory_action_kes", "describe_the_anticipatory_action_intervention",
	"status_of_the_early_action", "number_of_people_targeted", "number_of_hh_targeted",
	"number_of_males_targeted", "number_of_females_targeted",
)


def _detail_row(row):
	return {
		"subcounty_level": row.get("subcounty_level", 0),
		"county": row.get("county"),
		"subcounty": row.get("subcounty"),
		"sector": row.get("sector"),
		"number_of_livestock_targeted": row.get("number_of_livestock_targeted"),
		"number_of_wildlife_targeted": row.get("number_of_wildlife_targeted"),
		"amount_for_anticipatory_action_kes": row.get("amount_for_anticipatory_action_kes"),
		"describe_the_anticipatory_action_intervention": row.get("describe_the_anticipatory_action_intervention"),
		"status_of_the_early_action": row.get("status_of_the_early_action", "Planned"),
		"number_of_people_targeted": row.get("number_of_people_targeted"),
		"number_of_hh_targeted": row.get("number_of_hh_targeted"),
		"number_of_males_targeted": row.get("number_of_males_targeted"),
		"number_of_females_targeted": row.get("number_of_females_targeted"),
	}


_EDITABLE_STATUSES = ("Pending", "Not Approved", "Replied")


def _editable(doc):
	"""A submission can still be changed while it is a Draft and not yet approved.
	'Replied' (the reviewer asked for more information) is editable too."""
	return doc.docstatus == 0 and (doc.status or "Pending") in _EDITABLE_STATUSES


@frappe.whitelist()
def get_my_submissions():
	"""The signed-in reporter's own submissions, newest first, with detail rows."""
	_require_login()
	rows = frappe.get_all(
		"Anticipatory Action",
		# docstatus < 2 hides cancelled, superseded versions left behind by an
		# update/amend — the live amendment (a fresh Draft) is what shows instead.
		filters={"owner": frappe.session.user, "docstatus": ["<", 2], "is_test": ["!=", 1]},
		fields=[
			"name", "implementing_organization", "anticipated_hazard",
			"activation_start_date", "activation_end_date", "status",
			"reason_for_rejection", "info_request", "docstatus", "modified", "creation",
			"amended_from", "is_update",
		],
		order_by="modified desc",
		limit=200,
	)
	# CODE-004: fetch every submission's detail rows in ONE query, not one per row.
	names = [r["name"] for r in rows]
	details_by_parent = {}
	if names:
		for d in frappe.get_all(
			"Anticipatory Action Details",
			filters={"parent": ["in", names]},
			fields=["parent", "county", "sector", "number_of_people_targeted",
					"amount_for_anticipatory_action_kes", "status_of_the_early_action"],
			order_by="parent asc, idx asc",
		):
			details_by_parent.setdefault(d.pop("parent"), []).append(d)
	for r in rows:
		r["can_edit"] = int(r.get("docstatus") == 0 and (r.get("status") or "Pending") in _EDITABLE_STATUSES)
		r["can_update"] = int(r.get("docstatus") == 1 and (r.get("status") or "") == "Approved")
		r["details"] = details_by_parent.get(r["name"], [])
	return {"success": True, "data": _sanitize(rows)}


@frappe.whitelist()
def get_my_submission(name):
	"""Full editable payload for one owned, still-editable submission."""
	_require_login()
	doc = frappe.get_doc("Anticipatory Action", name)
	if doc.owner != frappe.session.user:
		frappe.throw("You can only view your own submissions.", frappe.PermissionError)
	data = {f: doc.get(f) for f in _PARENT_FIELDS}
	data["name"] = doc.name
	data["status"] = doc.status
	data["info_request"] = doc.get("info_request")
	data["reason_for_rejection"] = doc.get("reason_for_rejection")
	data["amended_from"] = doc.get("amended_from")
	data["is_update"] = int(doc.get("is_update") or 0)
	data["can_edit"] = int(_editable(doc))
	data["anticipatory_action_details"] = [
		{f: row.get(f) for f in _DETAIL_FIELDS if f != "name"}
		for row in doc.get("anticipatory_action_details", [])
	]
	return {"success": True, "data": _sanitize(data)}


def _version_chain(name):
	"""Walk the ``amended_from`` links back to the original submission and return
	the whole history (oldest first) so a reporter can see every version they
	filed when an approved submission was updated."""
	chain = []
	seen = set()
	cur = name
	while cur and cur not in seen:
		seen.add(cur)
		row = frappe.db.get_value(
			"Anticipatory Action", cur,
			["name", "status", "docstatus", "creation", "modified", "amended_from"],
			as_dict=True,
		)
		if not row:
			break
		chain.append(row)
		cur = row.get("amended_from")
	chain.reverse()
	for i, row in enumerate(chain, start=1):
		row["version"] = i
	return chain


@frappe.whitelist()
def get_my_submission_versions(name):
	"""Version history (amendment chain) for one owned submission."""
	_require_login()
	doc = frappe.get_doc("Anticipatory Action", name)
	if doc.owner != frappe.session.user:
		if not _can_review():
			frappe.throw("You can only view your own submissions.", frappe.PermissionError)
		_assert_submission_in_scope(doc)
	return {"success": True, "data": _version_chain(name)}


@frappe.whitelist()
def update_my_submission_start(name):
	"""Begin an update of an APPROVED (submitted) submission.

	Behind the scenes this cancels the locked, approved document and opens a fresh
	editable Draft amendment that back-links to it via ``amended_from`` — so the
	reporter keeps every previous version, and reviewers can see at a glance that
	the new Draft is an update to a submission they had already approved. The
	amendment re-enters the queue as Pending when the reporter saves it.
	"""
	_require_login()
	doc = frappe.get_doc("Anticipatory Action", name)
	if doc.owner != frappe.session.user:
		frappe.throw("You can only update your own submissions.", frappe.PermissionError)
	if doc.docstatus != 1 or (doc.status or "") != "Approved":
		frappe.throw("Only an approved submission can be updated.")

	# If an open amendment already exists, reuse it rather than cancelling twice.
	existing = frappe.db.get_value(
		"Anticipatory Action", {"amended_from": name, "docstatus": 0}, "name"
	)
	if existing:
		return {"success": True, "name": existing}

	doc.flags.ignore_permissions = True
	doc.cancel()

	amended = frappe.copy_doc(doc)
	amended.amended_from = doc.name
	amended.is_update = 1
	amended.status = "Pending"
	amended.reason_for_rejection = None
	amended.info_request = None
	amended.docstatus = 0
	amended.flags.ignore_permissions = True
	amended.insert()
	frappe.db.commit()
	return {"success": True, "name": amended.name}


@frappe.whitelist()
def update_my_submission(name, data):
	"""Rewrite an owned Draft submission and reset it to Pending for review."""
	_require_login()
	doc = frappe.get_doc("Anticipatory Action", name)
	if doc.owner != frappe.session.user:
		frappe.throw("You can only edit your own submissions.", frappe.PermissionError)
	if not _editable(doc):
		frappe.throw("This submission has been finalised and can no longer be edited.")

	d = frappe.parse_json(data)
	# A submission must keep at least one intervention row — that content is the
	# submission. Block an edit that would empty it out (the form's client-side
	# check catches this first with a friendlier message).
	if not (d.get("anticipatory_action_details") or []):
		frappe.throw("Please keep at least one anticipatory action entry.")
	for f in _PARENT_FIELDS:
		if f in d:
			doc.set(f, d.get(f))

	doc.set("anticipatory_action_details", [])
	for row in (d.get("anticipatory_action_details") or []):
		doc.append("anticipatory_action_details", _detail_row(row))

	# Editing for any reason (revision after rejection, or answering a reviewer's
	# request for more info) returns the submission to the review queue as Pending.
	doc.status = "Pending"
	doc.reason_for_rejection = None
	doc.info_request = None
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def withdraw_my_submission(name):
	"""Delete an owned Draft submission."""
	_require_login()
	doc = frappe.get_doc("Anticipatory Action", name)
	if doc.owner != frappe.session.user:
		frappe.throw("You can only withdraw your own submissions.", frappe.PermissionError)
	if doc.docstatus != 0:
		frappe.throw("This submission has been finalised and can no longer be withdrawn.")
	frappe.delete_doc("Anticipatory Action", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def download_my_submission_pdf(name):
	"""Stream the NDOC-branded PDF copy of a submission — same layout as the
	emailed copy. A member may print any of their own submissions (any status);
	reviewers may print any submission."""
	_require_login()
	doc = frappe.get_doc("Anticipatory Action", name)
	if doc.owner != frappe.session.user:
		if not _can_review():
			frappe.throw("You can only download your own submissions.", frappe.PermissionError)
		_assert_submission_in_scope(doc)

	from anticipatory_action.anticipatory_action.doctype.anticipatory_action.pdf import (
		build_submission_pdf,
	)

	frappe.local.response.filename = f"Anticipatory_Action_{doc.name}.pdf"
	frappe.local.response.filecontent = build_submission_pdf(doc)
	frappe.local.response.type = "download"


# ---- profile ----

@frappe.whitelist()
def get_my_profile():
	_require_login()
	u = frappe.db.get_value(
		"User", frappe.session.user,
		["first_name", "last_name", "full_name", "phone", "mobile_no", "email"],
		as_dict=True,
	)
	roster = frappe.db.get_value(
		"Anticipatory Action User",
		{"user": frappe.session.user},
		["organization", "role"],
		as_dict=True,
	)
	if roster and roster.get("organization"):
		roster["organization_name"] = frappe.db.get_value(
			"Anticipatory Action Organization", roster["organization"], "name_of_organization"
		)
	return {"success": True, "data": u, "membership": roster}


@frappe.whitelist()
def update_my_profile(first_name=None, last_name=None, phone=None):
	"""Update the signed-in user's basic details. Never touches email / roles."""
	_require_login()
	# Validate BEFORE touching anything. The roster doctype makes first_name,
	# last_name and phone mandatory; the old code saved the User first, then hit a
	# raw mandatory error on roster.save() before commit — rolling back the whole
	# edit (even the field the user actually changed) with a misleading message.
	if first_name is not None and not first_name.strip():
		frappe.throw("First name is required.")
	if last_name is not None and not (last_name or "").strip():
		frappe.throw("Last name is required.")
	if phone is not None and not (phone or "").strip():
		frappe.throw("Phone number is required.")
	user = frappe.get_doc("User", frappe.session.user)
	if first_name is not None:
		user.first_name = first_name.strip()
	if last_name is not None:
		user.last_name = (last_name or "").strip()
	if phone is not None:
		user.phone = (phone or "").strip()
	user.flags.ignore_permissions = True
	user.save()

	# Mirror onto the AA roster record so both stay consistent.
	roster_name = frappe.db.get_value("Anticipatory Action User", {"user": user.name}, "name") \
		or frappe.db.get_value("Anticipatory Action User", {"email": user.name}, "name")
	if roster_name:
		roster = frappe.get_doc("Anticipatory Action User", roster_name)
		if first_name is not None:
			roster.first_name = first_name.strip()
		if last_name is not None:
			roster.last_name = (last_name or "").strip()
		if phone is not None:
			roster.phone = (phone or "").strip()
		roster.flags.ignore_permissions = True
		roster.save()

	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def get_my_notifications():
	"""Unread in-app alerts for the signed-in member (e.g. a role change). The
	portal shows these as a popup, then calls mark_my_notifications_read."""
	_require_login()
	rows = frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user, "read": 0, "type": "Alert"},
		fields=["name", "subject", "email_content", "creation"],
		order_by="creation desc",
		limit=10,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def mark_my_notifications_read(names=None):
	"""Mark the member's alerts read once the portal has shown them."""
	_require_login()
	filters = {"for_user": frappe.session.user, "read": 0, "type": "Alert"}
	targets = frappe.parse_json(names) if names else None
	for n in (targets or frappe.get_all("Notification Log", filters=filters, pluck="name")):
		with contextlib.suppress(Exception):
			frappe.db.set_value("Notification Log", n, "read", 1, update_modified=False)
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def change_my_password(old_password, new_password):
	"""Change the signed-in user's password (verifying the current one first)."""
	_require_login()
	from frappe.utils.password import check_password

	try:
		check_password(frappe.session.user, old_password)
	except frappe.AuthenticationError:
		frappe.throw("Your current password is incorrect.")

	user = frappe.get_doc("User", frappe.session.user)
	user.new_password = new_password  # runs the site password policy on save
	user.flags.ignore_permissions = True
	user.save()
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN — USERS
# ===========================================================================

def _ensure_roster_for_aa_users():
	"""Self-heal: make sure every Frappe User that holds an AA role (e.g. people
	created before this app, via sign-up, or directly in the desk) has a roster
	record, so the admin can see and manage all of them. Pure-AA accounts only —
	anyone who also holds other-project roles is left untouched."""
	role_rows = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": ["in", list(AA_ROLES)]},
		fields=["parent as user"],
		limit=5000,
	)
	emails = {r.user for r in role_rows} - {"Administrator", "Guest"}
	if not emails:
		return
	have = {d.email for d in frappe.get_all(
		"Anticipatory Action User", filters={"email": ["in", list(emails)]}, fields=["email"])}
	missing = emails - have
	if not missing:
		return

	org = frappe.db.get_value("Anticipatory Action Organization", {}, "name")
	if not org:
		opts = frappe.get_meta("Anticipatory Action Organization").get_field("type_of_organization").options or ""
		otype = next((o for o in opts.split("\n") if o.strip()), "Other")
		o = frappe.get_doc({"doctype": "Anticipatory Action Organization",
			"name_of_organization": "Unassigned", "type_of_organization": otype})
		o.flags.ignore_permissions = True
		o.insert()
		org = o.name

	for email in missing:
		roles = set(frappe.get_roles(email))
		if roles - AA_ROLES - _DEFAULT_ROLES:
			continue  # also has non-AA roles -> managed elsewhere, leave alone
		ud = frappe.db.get_value("User", email, ["first_name", "last_name", "phone"], as_dict=True) or {}
		role = "Anticipatory Action Admin" if "Anticipatory Action Admin" in roles else "Anticipatory Action User"
		try:
			doc = frappe.get_doc({"doctype": "Anticipatory Action User",
				"first_name": ud.get("first_name") or email.split("@")[0],
				"last_name": ud.get("last_name") or "-", "email": email,
				# L10N-002: don't fabricate a "0000000000" phone. Carry the real one if the
				# User has it, else leave it blank (self-heal is for legacy accounts) so the
				# admin can fill a genuine number rather than storing a fake one.
				"phone": ud.get("phone") or None, "organization": org,
				"role": role, "enabled": 1})
			doc.flags.ignore_permissions = True
			doc.insert(ignore_mandatory=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ensure_roster_for_aa_users")
	frappe.db.commit()


@frappe.whitelist()
def list_aa_users(search=None):
	"""AA members with their roster details.

	Admins see every member and may manage them. An Approver — their
	organization's focal person — sees only the members of their own organization,
	and read-only (the create/edit/deactivate endpoints stay admin-only).
	Self-heals missing roster records (admin maintenance) so legacy / desk-created
	users show up too."""
	_require_approver()
	if _is_admin():
		try:
			_ensure_roster_for_aa_users()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "list_aa_users self-heal")
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"full_name": ["like", like], "email": ["like", like]}
	filters = {}
	if not _is_admin():
		# Focal person: confined to their own organization's members. The sentinel
		# guarantees an empty result if the approver somehow has no organization.
		filters["organization"] = _user_org() or "__no_org__"
	users = frappe.get_all(
		"Anticipatory Action User",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name", "full_name", "first_name", "last_name", "email", "phone",
			"organization", "role", "user", "enabled", "creation", "can_approve_accounts",
		],
		order_by="creation desc",
		limit=1000,
	)
	# Resolve the opaque AA-ORG-#### docname to the human organisation name for display.
	org_names = dict(frappe.get_all(
		"Anticipatory Action Organization",
		fields=["name", "name_of_organization"], as_list=True,
	))
	for u in users:
		u["organization_name"] = org_names.get(u.get("organization")) or u.get("organization")
	return {"success": True, "data": users}


@frappe.whitelist()
def get_user_form_meta():
	_require_admin()
	orgs = frappe.get_all(
		"Anticipatory Action Organization",
		fields=["name", "name_of_organization"],
		order_by="name_of_organization asc",
	)
	return {"success": True, "organizations": orgs, "roles": sorted(AA_ROLES)}


@frappe.whitelist()
def create_aa_user(first_name, last_name, email, phone, organization, role="Anticipatory Action User"):
	_require_admin()
	if not _can_set_role():
		# WKF-003: System Managers AND AA Admins may choose the role (_can_set_role);
		# anyone else who reaches here (shouldn't, given _require_admin) defaults to a
		# plain member. The chosen role is always passed through _constrain_role, so it
		# can never be set outside the three AA roles (never System Manager).
		role = "Anticipatory Action User"
	_constrain_role(role)
	# Name each missing field explicitly. The roster doctype makes first_name,
	# last_name and phone mandatory, so without these guards a blank one falls
	# through to a raw "X is mandatory" error for a field the modal never flagged.
	first_name = (first_name or "").strip()
	last_name = (last_name or "").strip()
	phone = (phone or "").strip()
	email = (email or "").strip().lower()
	if not first_name:
		frappe.throw("First name is required.")
	if not last_name:
		frappe.throw("Last name is required.")
	if not email:
		frappe.throw("Email is required.")
	if not phone:
		frappe.throw("Phone number is required.")
	if frappe.db.exists("Anticipatory Action User", {"email": email}):
		frappe.throw("An Anticipatory Action user with this email already exists.")
	# Refuse to attach AA roles onto an account that belongs to another project.
	if _foreign_roles(email):
		frappe.throw("A user with this email already exists on this site and is managed elsewhere.")
	if not organization or not frappe.db.exists("Anticipatory Action Organization", organization):
		frappe.throw("Please choose a valid organization.")

	doc = frappe.get_doc({
		"doctype": "Anticipatory Action User",
		"first_name": first_name,
		"last_name": last_name,
		"email": email,
		"phone": phone,
		"organization": organization,
		"role": role,
		"enabled": 1,
	})
	doc.flags.ignore_permissions = True
	with _elevated():
		doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name, "user": doc.user}


@frappe.whitelist()
def update_aa_user(name, first_name=None, last_name=None, phone=None, organization=None, role=None):
	_require_admin()
	_assert_is_aa_user(name)
	doc = frappe.get_doc("Anticipatory Action User", name)
	# These three are mandatory on the roster; reject a cleared value with a named
	# message rather than letting roster.save() raise a raw "X is mandatory" for a
	# field the modal didn't flag.
	if first_name is not None:
		if not first_name.strip():
			frappe.throw("First name is required.")
		doc.first_name = first_name.strip()
	if last_name is not None:
		if not last_name.strip():
			frappe.throw("Last name is required.")
		doc.last_name = last_name.strip()
	if phone is not None:
		if not phone.strip():
			frappe.throw("Phone number is required.")
		doc.phone = phone.strip()
	if organization is not None:
		if not frappe.db.exists("Anticipatory Action Organization", organization):
			frappe.throw("Please choose a valid organization.")
		doc.organization = organization
	# WKF-003: System Managers and AA Admins may both change the role (_can_set_role),
	# always constrained to the three AA roles — never System Manager. Non-privileged
	# callers can't reach here (_require_admin above).
	if role is not None and _can_set_role():
		_constrain_role(role)
		doc.role = role
	# Email is intentionally immutable — it is the account identity.
	doc.flags.ignore_permissions = True
	with _elevated():
		doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def set_account_approver(name, enabled):
	"""Grant or revoke the account-approval capability for an AA member. Admin only,
	and (per requirement) only an Approver can be made an account approver."""
	_require_admin()
	_assert_is_aa_user(name)
	on = 1 if str(enabled).lower() in ("1", "true", "yes", "on") else 0
	doc = frappe.get_doc("Anticipatory Action User", name)
	if on and doc.role != "Anticipatory Action Approver":
		frappe.throw("Only an Approver can be made an account approver — set this member's role to Approver first.")
	doc.can_approve_accounts = on
	doc.flags.ignore_permissions = True
	with _elevated():
		doc.save()
	frappe.db.commit()
	return {"success": True, "can_approve_accounts": on}


@frappe.whitelist()
def set_aa_user_active(name, enabled):
	"""Enable / disable an AA login without ever deleting the record."""
	_require_admin()
	roster = _assert_is_aa_user(name)
	enabled = 1 if str(enabled).lower() in ("1", "true", "yes", "on") else 0

	doc = frappe.get_doc("Anticipatory Action User", name)
	doc.enabled = enabled
	doc.flags.ignore_permissions = True

	target = doc.user or (roster.email if frappe.db.exists("User", roster.email) else None)
	with _elevated():
		doc.save()  # on_update syncs the linked User when one is linked
		if target:
			user = frappe.get_doc("User", target)
			user.enabled = enabled
			user.flags.ignore_permissions = True
			user.save()  # proper disable: clears sessions etc.
			if not doc.user:
				doc.db_set("user", user.name)

	frappe.db.commit()
	return {"success": True, "enabled": enabled}


@frappe.whitelist()
def send_password_reset(name):
	"""Admin-triggered password reset: email the member a fresh set-password link.
	Works whether or not the roster has been linked to its User yet."""
	_require_admin()
	roster = _assert_is_aa_user(name)
	target = roster.user or (roster.email if frappe.db.exists("User", roster.email) else None)
	if not target:
		frappe.throw("This member does not have a login account yet.")
	with _elevated():
		user = frappe.get_doc("User", target)
		# Send the branded AA set-password email (not Frappe's plain reset), so it
		# matches the welcome email and lands the member on the portal.
		from anticipatory_action.api.aa_email import send_set_password_email
		if not send_set_password_email(user):
			frappe.throw("Could not generate a password-reset link on this version.")
	frappe.db.commit()
	return {"success": True, "email": target}


# ===========================================================================
# ADMIN — SUBMISSIONS (approve / reject)
# ===========================================================================

@frappe.whitelist()
def list_submissions(status=None):
	_require_approver()
	from anticipatory_action.anticipatory_action.page.aa_operations.aa_operations import get_activations

	return {"success": True, "data": get_activations(status=status)}


@frappe.whitelist()
def get_submission(name):
	"""Full read-only detail of one submission, so an admin can review it before
	approving or rejecting."""
	_require_approver()
	doc = frappe.get_doc("Anticipatory Action", name)
	_assert_submission_in_scope(doc)
	data = {f: doc.get(f) for f in _PARENT_FIELDS}
	data.update({
		"name": doc.name,
		"status": doc.status,
		"reason_for_rejection": doc.reason_for_rejection,
		"info_request": doc.get("info_request"),
		"docstatus": doc.docstatus,
		"supporting_materials": doc.get("supporting_materials"),
		"amended_from": doc.get("amended_from"),
		"is_update": int(doc.get("is_update") or 0),
		"owner": doc.owner,
		"creation": str(doc.creation),
		"modified": str(doc.modified),
	})
	data["versions"] = _version_chain(doc.name)
	data["anticipatory_action_details"] = [
		{f: row.get(f) for f in _DETAIL_FIELDS} for row in doc.get("anticipatory_action_details", [])
	]
	return {"success": True, "data": _sanitize(data)}


@frappe.whitelist()
def set_submission_status(name, status, reason=None):
	"""Reviewer decision on a submission:

	* Approved      -> submit + lock the document.
	* Not Approved  -> keep editable; a rejection reason is required.
	* Replied       -> ask the reporter for more information; keep editable. The
	                   message is required and shown to the reporter, who answers
	                   by editing and saving, which flips it back to Pending.
	* Pending       -> reset to the queue.
	"""
	_require_approver()
	if status not in ("Pending", "Approved", "Not Approved", "Replied"):
		frappe.throw("Invalid status.")
	if status == "Not Approved" and not (reason or "").strip():
		frappe.throw("Please provide a reason for rejection.")
	if status == "Replied" and not (reason or "").strip():
		frappe.throw("Please describe the information you need from the reporter.")

	doc = frappe.get_doc("Anticipatory Action", name)
	_assert_submission_in_scope(doc)
	doc.flags.ignore_permissions = True
	reason_val = reason if status == "Not Approved" else None
	info_val = reason if status == "Replied" else None

	if doc.docstatus == 1:
		if status in ("Not Approved", "Replied"):
			# WKF-001: a finalised (docstatus 1) submission is not editable, so simply
			# db_set-ting it to Not Approved / Replied would strand the reporter — they
			# could neither revise nor answer. Instead reopen it the same way the member
			# amend flow does: cancel the locked doc and open a fresh editable Draft
			# amendment carrying the reviewer's decision + reason, which re-enters the
			# queue as Pending once the reporter saves it.
			existing = frappe.db.get_value(
				"Anticipatory Action", {"amended_from": doc.name, "docstatus": 0}, "name"
			)
			if existing:
				frappe.db.set_value("Anticipatory Action", existing, {
					"status": status, "reason_for_rejection": reason_val, "info_request": info_val,
				}, update_modified=False)
				frappe.db.commit()
				if status == "Replied":
					send_submission_replied(doc, reason)
				elif status == "Not Approved":
					send_submission_rejected(doc, reason)
				return {"success": True, "status": status, "name": existing}
			doc.cancel()
			amended = frappe.copy_doc(doc)
			amended.amended_from = doc.name
			amended.is_update = 1
			amended.status = status
			amended.reason_for_rejection = reason_val
			amended.info_request = info_val
			amended.docstatus = 0
			amended.flags.ignore_permissions = True
			amended.insert()
			# WKF-001: insert() stamps owner = the current user (the REVIEWER), which would
			# strand the reporter — the whole member portal keys off owner, so the reporter
			# would lose their own submission and the Replied -> edit -> Pending round-trip.
			# Force ownership back to the original reporter after insert (set_user_and_timestamp
			# overrides any owner set beforehand, so this must happen post-insert).
			if doc.owner and doc.owner != amended.owner:
				frappe.db.set_value("Anticipatory Action", amended.name, "owner", doc.owner, update_modified=False)
			frappe.db.commit()
			if status == "Replied":
				send_submission_replied(amended, reason)
			elif status == "Not Approved":
				send_submission_rejected(amended, reason)
			return {"success": True, "status": status, "name": amended.name}
		# Approved (already) / Pending — status / reason are the only mutable bits.
		doc.db_set("status", status)
		doc.db_set("reason_for_rejection", reason_val)
		doc.db_set("info_request", info_val)
	elif status == "Approved":
		doc.status = "Approved"
		doc.reason_for_rejection = None
		doc.info_request = None
		doc.submit()
	else:
		doc.status = status
		doc.reason_for_rejection = reason_val
		doc.info_request = info_val
		doc.save()

	frappe.db.commit()
	if status == "Replied":
		send_submission_replied(doc, reason)
	elif status == "Not Approved":
		send_submission_rejected(doc, reason)
	return {"success": True, "status": status}


# ===========================================================================
# ADMIN — REPORTS (standalone Anticipatory Report doctype)
# ===========================================================================

_PILLARS = ("Pillar 1", "Pillar 2", "Pillar 3", "Pillar 4", "Pillar 5")


def _as_bool(v, default=1):
	if v is None:
		return default
	return 1 if str(v).strip().lower() in ("1", "true", "yes", "on") else 0


@frappe.whitelist()
def list_reports():
	_require_approver()
	rows = frappe.get_all(
		"Anticipatory Report",
		fields=["name", "year", "month", "title", "description", "category", "source",
				"key_words", "link", "attachment", "published", "visibility",
				"uploaded_by", "removed", "removal_reason", "owner"],
		order_by="year desc, modified desc",
		limit=1000,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def get_report(name):
	_require_approver()
	return {"success": True, "data": frappe.get_doc("Anticipatory Report", name).as_dict()}


def _norm_visibility(v):
	v = (v or "Public").strip().title()
	return v if v in ("Public", "Private") else "Public"


def _safe_link(url):
	"""SEC-101: reject dangerous URL schemes on stored report links. Allows http(s),
	mailto, tel and relative/anchor URLs; blocks javascript:, data:, vbscript: etc. so a
	stored link can never become an XSS payload when rendered into an href on the
	console. (The frontend also neutralises these at render time — this is the second
	layer, at the point of storage.)"""
	u = (url or "").strip()
	if not u:
		return None
	head = u.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
	if ":" in head:
		scheme = head.split(":", 1)[0].strip().lower()
		if scheme not in ("http", "https", "mailto", "tel"):
			frappe.throw("Please provide a valid http(s) link.")
	return u


@frappe.whitelist()
def add_report(title, year=None, month=None, description=None, category=None,
			   source=None, key_words=None, link=None, attachment=None, published=1,
			   visibility=None):
	_require_approver()
	if not (title or "").strip():
		frappe.throw("Report title is required.")
	if category and category not in ("Report", "Workshop Report"):
		frappe.throw("Invalid category.")
	visibility = _norm_visibility(visibility)
	doc = frappe.get_doc({
		"doctype": "Anticipatory Report",
		"title": title, "year": year or None, "month": month, "description": description,
		"category": category or "Report", "source": source, "key_words": key_words,
		"link": _safe_link(link), "attachment": attachment, "visibility": visibility,
		# 'Published' means "visible on the public website" — Private reports are
		# portal-only, so they are never published to the website.
		"published": _as_bool(published) if visibility == "Public" else 0,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_report(name, title=None, year=None, month=None, description=None, category=None,
				  source=None, key_words=None, link=None, attachment=None, published=None,
				  visibility=None):
	_require_approver()
	if category and category not in ("Report", "Workshop Report"):
		frappe.throw("Invalid category.")
	if link is not None:
		link = _safe_link(link) or ""  # SEC-101: validate scheme; "" clears the field
	doc = frappe.get_doc("Anticipatory Report", name)
	for field, value in (("title", title), ("year", year), ("month", month), ("description", description),
						 ("category", category), ("source", source), ("key_words", key_words),
						 ("link", link), ("attachment", attachment)):
		if value is not None:
			doc.set(field, value)
	if visibility is not None:
		doc.visibility = _norm_visibility(visibility)
	if published is not None:
		doc.published = _as_bool(published)
	# A Private report is never on the public website.
	if doc.visibility == "Private":
		doc.published = 0
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def remove_report(name, reason=None):
	"""Reviewer takes a report down. A reason is required (reviewers review and
	remove member content, they do not silently edit it). The record is kept,
	marked removed, and hidden everywhere."""
	_require_approver()
	reason = (reason or "").strip()
	if not reason:
		frappe.throw("Please provide a reason for removing this report.")
	if not frappe.db.exists("Anticipatory Report", name):
		frappe.throw("Unknown report.")
	doc = frappe.get_doc("Anticipatory Report", name)
	doc.removed = 1
	doc.removal_reason = reason
	doc.published = 0
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def delete_report(name):
	_require_approver()
	if not frappe.db.exists("Anticipatory Report", name):
		frappe.throw("Unknown report.")
	frappe.delete_doc("Anticipatory Report", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ---- member-uploaded reports (portal self-service) ----

@frappe.whitelist()
def list_my_reports():
	"""Reports the signed-in member uploaded themselves."""
	_require_login()
	rows = frappe.get_all(
		"Anticipatory Report",
		filters={"uploaded_by": frappe.session.user},
		fields=["name", "title", "description", "category", "source", "key_words",
				"link", "attachment", "visibility", "published", "removed",
				"removal_reason", "year", "month", "creation"],
		order_by="creation desc",
		limit=500,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def submit_my_report(title, description=None, category=None, source=None,
					 key_words=None, link=None, attachment=None, visibility="Private"):
	"""A member uploads a report. They choose Public (also shown on the public
	website) or Private (only visible inside the portal)."""
	_require_login()
	if not (title or "").strip():
		frappe.throw("Report title is required.")
	if not (link or attachment):
		frappe.throw("Please provide a link or upload a file.")
	if category and category not in ("Report", "Workshop Report"):
		frappe.throw("Invalid category.")
	visibility = _norm_visibility(visibility)
	doc = frappe.get_doc({
		"doctype": "Anticipatory Report",
		"title": title, "description": description, "category": category or "Report",
		"source": source, "key_words": key_words, "link": _safe_link(link), "attachment": attachment,
		"visibility": visibility,
		"published": 1 if visibility == "Public" else 0,
		"uploaded_by": frappe.session.user,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def delete_my_report(name):
	"""A member removes their own uploaded report (only if a reviewer hasn't)."""
	_require_login()
	row = frappe.db.get_value("Anticipatory Report", name, ["uploaded_by", "removed"], as_dict=True)
	if not row or row.uploaded_by != frappe.session.user:
		frappe.throw("You can only remove your own reports.", frappe.PermissionError)
	frappe.delete_doc("Anticipatory Report", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN — ACTIVITIES (standalone Anticipatory Activity doctype)
# ===========================================================================

_ACTIVITY_STATUSES = ("Planned", "Ongoing", "Completed", "On Hold", "Cancelled")


@frappe.whitelist()
def list_activities():
	_require_approver()
	rows = frappe.get_all(
		"Anticipatory Activity",
		fields=["name", "start_date", "end_date", "pillar", "activity", "activity_reference",
				"milestone", "status", "published", "details", "narrative", "image"],
		order_by="start_date desc, modified desc",
		limit=1000,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def get_activity(name):
	_require_approver()
	return {"success": True, "data": frappe.get_doc("Anticipatory Activity", name).as_dict()}


@frappe.whitelist()
def add_activity(activity, start_date=None, end_date=None, pillar=None, activity_reference=None,
				 milestone=None, status=None, details=None, published=1, image=None, narrative=None):
	_require_approver()
	if not (activity or "").strip():
		frappe.throw("Activity is required.")
	if pillar and pillar not in _PILLARS:
		frappe.throw("Invalid pillar.")
	if status and status not in _ACTIVITY_STATUSES:
		frappe.throw("Invalid status.")
	doc = frappe.get_doc({
		"doctype": "Anticipatory Activity",
		"activity": activity, "start_date": start_date or None, "end_date": end_date or None,
		"pillar": pillar, "activity_reference": activity_reference, "milestone": milestone,
		"status": status or "Planned", "details": details, "image": image, "narrative": narrative,
		"published": _as_bool(published),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_activity(name, activity=None, start_date=None, end_date=None, pillar=None,
					activity_reference=None, milestone=None, status=None, details=None,
					published=None, image=None, narrative=None):
	_require_approver()
	if pillar and pillar not in _PILLARS:
		frappe.throw("Invalid pillar.")
	if status and status not in _ACTIVITY_STATUSES:
		frappe.throw("Invalid status.")
	doc = frappe.get_doc("Anticipatory Activity", name)
	for field, value in (("activity", activity), ("start_date", start_date), ("end_date", end_date),
						 ("pillar", pillar), ("activity_reference", activity_reference),
						 ("milestone", milestone), ("status", status), ("details", details),
						 ("image", image), ("narrative", narrative)):
		if value is not None:
			doc.set(field, value)
	if published is not None:
		doc.published = _as_bool(published)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def delete_activity(name):
	_require_approver()
	if not frappe.db.exists("Anticipatory Activity", name):
		frappe.throw("Unknown activity.")
	frappe.delete_doc("Anticipatory Activity", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN - EVENTS
# ===========================================================================

_EVENT_PILLARS = ("Early Warning", "Early Action", "Coordination and Governance",
				  "Research and Learning", "Policy and Advocacy", "Financing",
				  "Monitoring and Evaluation")


@frappe.whitelist()
def list_events():
	_require_approver()
	rows = frappe.get_all(
		"AA Event",
		fields=["name", "title", "description", "location", "pillar", "start_date",
				"end_date", "status", "published", "image"],
		order_by="start_date desc, modified desc",
		limit=1000,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def get_event(name):
	_require_approver()
	return {"success": True, "data": frappe.get_doc("AA Event", name).as_dict()}


@frappe.whitelist()
def add_event(title, start_date, end_date=None, location=None, pillar=None,
			  description=None, image=None, status=None, published=1):
	_require_approver()
	if not (title or "").strip():
		frappe.throw("Event title is required.")
	if not (start_date or "").strip():
		frappe.throw("An event date is required.")
	if pillar and pillar not in _EVENT_PILLARS:
		frappe.throw("Invalid pillar.")
	if status and status not in _ACTIVITY_STATUSES:
		frappe.throw("Invalid status.")
	doc = frappe.get_doc({
		"doctype": "AA Event",
		"title": title, "start_date": start_date, "end_date": end_date or None,
		"location": location, "pillar": pillar, "description": description, "image": image,
		"status": status or None, "published": _as_bool(published),
	})
	doc.flags.ignore_permissions = True
	doc.insert()  # validate() auto-sets status from the dates
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_event(name, title=None, start_date=None, end_date=None, location=None, pillar=None,
				 description=None, image=None, status=None, published=None):
	_require_approver()
	if pillar and pillar not in _EVENT_PILLARS:
		frappe.throw("Invalid pillar.")
	if status and status not in _ACTIVITY_STATUSES:
		frappe.throw("Invalid status.")
	doc = frappe.get_doc("AA Event", name)
	for field, value in (("title", title), ("start_date", start_date), ("end_date", end_date),
						 ("location", location), ("pillar", pillar), ("description", description),
						 ("image", image), ("status", status)):
		if value is not None:
			doc.set(field, value)
	if published is not None:
		doc.published = _as_bool(published)
	doc.flags.ignore_permissions = True
	doc.save()  # validate() re-derives status unless On Hold / Cancelled
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def delete_event(name):
	_require_approver()
	if not frappe.db.exists("AA Event", name):
		frappe.throw("Unknown event.")
	frappe.delete_doc("AA Event", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN — ORGANIZATIONS
# ===========================================================================

@frappe.whitelist()
def list_organizations():
	# Read-only: approvers need the org list to pick a publishing authority.
	_require_approver()
	orgs = frappe.get_all(
		"Anticipatory Action Organization",
		fields=[
			"name", "name_of_organization", "type_of_organization",
			"primary_contact_person_name", "primary_email_contact",
			"organization_phone", "organization_email",
		],
		order_by="name_of_organization asc",
		limit=500,
	)
	return {"success": True, "data": orgs}


@frappe.whitelist()
def add_organization(
	name_of_organization, type_of_organization=None, primary_contact_person_name=None,
	primary_phone_contact=None, primary_email_contact=None, organization_phone=None,
	organization_email=None, organization_website=None, address=None,
	about=None, narrative=None, logo=None, pillars_involved=None, aa_support=None,
	show_on_website=None,
):
	_require_admin()
	if not (name_of_organization or "").strip():
		frappe.throw("Organization name is required.")
	doc = frappe.get_doc({
		"doctype": "Anticipatory Action Organization",
		"name_of_organization": name_of_organization,
		"type_of_organization": type_of_organization,
		"primary_contact_person_name": primary_contact_person_name,
		"primary_phone_contact": primary_phone_contact,
		"primary_email_contact": primary_email_contact,
		"organization_phone": organization_phone,
		"organization_email": organization_email,
		"organization_website": organization_website,
		"address": address,
		"about": about, "narrative": narrative, "logo": logo,
		"pillars_involved": pillars_involved, "aa_support": aa_support,
		"show_on_website": _as_bool(show_on_website) if show_on_website is not None else 1,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


# ===========================================================================
# ADMIN — PUBLICATIONS (Reference Documents)
# ===========================================================================

@frappe.whitelist()
def list_publications():
	_require_approver()
	pubs = frappe.get_all(
		"Anticipatory Action Reference Documents",
		fields=[
			"name", "title", "type", "publication_date", "publishing_authority",
			"publication_url", "attach_publication", "docstatus",
		],
		order_by="publication_date desc",
		limit=500,
	)
	return {"success": True, "data": pubs}


@frappe.whitelist()
def get_publication(name):
	_require_approver()
	return {"success": True, "data": frappe.get_doc("Anticipatory Action Reference Documents", name).as_dict()}


@frappe.whitelist()
def add_publication(title, type, publishing_authority, publication_date=None, publication_url=None, attach_publication=None):
	_require_approver()
	if not (title or "").strip():
		frappe.throw("Publication title is required.")
	if not publishing_authority or not frappe.db.exists("Anticipatory Action Organization", publishing_authority):
		frappe.throw("Please choose a valid publishing authority.")
	doc = frappe.get_doc({
		"doctype": "Anticipatory Action Reference Documents",
		"title": title,
		"type": type,
		"publishing_authority": publishing_authority,
		"publication_date": publication_date,
		"publication_url": publication_url,
		"attach_publication": attach_publication,
	})
	doc.flags.ignore_permissions = True
	doc.insert()  # left as a Draft so it can be removed cleanly later
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def delete_publication(name):
	_require_approver()
	if not frappe.db.exists("Anticipatory Action Reference Documents", name):
		frappe.throw("Unknown publication.")
	doc = frappe.get_doc("Anticipatory Action Reference Documents", name)
	doc.flags.ignore_permissions = True
	if doc.docstatus == 1:
		doc.cancel()
	frappe.delete_doc("Anticipatory Action Reference Documents", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN — CONTACT MESSAGES
# ===========================================================================

@frappe.whitelist()
def list_messages(status=None):
	_require_approver()
	filters = {"status": status} if status else {}
	msgs = frappe.get_all(
		"AA Contact Message",
		filters=filters,
		fields=[
			"name", "full_name", "email", "organization", "phone",
			"subject", "message", "status", "submitted_on", "creation",
		],
		order_by="creation desc",
		limit=500,
	)
	for m in msgs:
		if m.get("message"):
			m["message"] = strip_html(m["message"]).strip()
	return {"success": True, "data": msgs}


@frappe.whitelist()
def set_message_status(name, status):
	_require_approver()
	if status not in ("New", "Read", "Replied", "Closed"):
		frappe.throw("Invalid status.")
	if not frappe.db.exists("AA Contact Message", name):
		frappe.throw("Unknown message.")
	frappe.db.set_value("AA Contact Message", name, "status", status)
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN — OVERVIEW
# ===========================================================================

@frappe.whitelist()
def get_admin_overview():
	_require_approver()
	from anticipatory_action.anticipatory_action.page.aa_operations.aa_operations import get_summary

	return {"success": True, "data": get_summary()}


# ===========================================================================
# ADMIN - FAQ (the public Frequently Asked Questions page)
# ===========================================================================

_FAQ_FIELDS = ["name", "question", "answer", "category", "display_order", "published"]


@frappe.whitelist()
def list_faqs():
	_require_approver()
	return {"success": True, "data": frappe.get_all(
		"AA FAQ", fields=_FAQ_FIELDS,
		order_by="category asc, display_order asc, creation asc", limit=500)}


@frappe.whitelist()
def get_faq(name):
	_require_approver()
	doc = frappe.get_doc("AA FAQ", name)
	return {"success": True, "data": {f: doc.get(f) for f in _FAQ_FIELDS}}


@frappe.whitelist()
def add_faq(question, answer, category=None, display_order=0, published=1):
	"""Create a FAQ. The answer is rich text (HTML) so links/bold/lists survive."""
	_require_approver()
	if not (question or "").strip() or not (answer or "").strip():
		frappe.throw("A question and an answer are required.")
	doc = frappe.get_doc({
		"doctype": "AA FAQ",
		"question": question.strip(),
		# SEC-102: the answer is rich HTML rendered via innerHTML on the PUBLIC FAQ page;
		# allowlist-sanitise on store so <script>/onerror payloads can never reach a visitor.
		"answer": sanitize_html(answer),
		"category": category or "General",
		"display_order": int(display_order or 0),
		"published": _as_bool(published, 1),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_faq(name, question=None, answer=None, category=None, display_order=None, published=None):
	_require_approver()
	doc = frappe.get_doc("AA FAQ", name)
	if question is not None:
		doc.question = question.strip()
	if answer is not None:
		doc.answer = sanitize_html(answer)  # SEC-102
	if category is not None:
		doc.category = category
	if display_order is not None:
		doc.display_order = int(display_order or 0)
	if published is not None:
		doc.published = _as_bool(published, 1)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def delete_faq(name):
	_require_admin()
	frappe.delete_doc("AA FAQ", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN - POLICY / TERMS DOCUMENTS (presented before sign-up)
# ===========================================================================

_POLICY_FIELDS = ["name", "title", "policy_type", "description", "attachment", "link", "published", "display_order"]


@frappe.whitelist()
def list_policies():
	_require_admin()
	return {"success": True, "data": frappe.get_all(
		"AA Policy Document", fields=_POLICY_FIELDS,
		order_by="display_order asc, creation asc", limit=200)}


@frappe.whitelist()
def add_policy(title, policy_type=None, description=None, attachment=None, link=None, published=1, display_order=0):
	_require_admin()
	if not (title or "").strip():
		frappe.throw("A title is required.")
	doc = frappe.get_doc({
		"doctype": "AA Policy Document",
		"title": title.strip(), "policy_type": policy_type or "Terms & Conditions",
		"description": description, "attachment": attachment, "link": link,
		"published": _as_bool(published, 1), "display_order": int(display_order or 0),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_policy(name, title=None, policy_type=None, description=None, attachment=None, link=None, published=None, display_order=None):
	_require_admin()
	doc = frappe.get_doc("AA Policy Document", name)
	if title is not None:
		doc.title = title.strip()
	if policy_type is not None:
		doc.policy_type = policy_type
	if description is not None:
		doc.description = description
	if attachment is not None:
		doc.attachment = attachment
	if link is not None:
		doc.link = link
	if published is not None:
		doc.published = _as_bool(published, 1)
	if display_order is not None:
		doc.display_order = int(display_order or 0)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def delete_policy(name):
	_require_admin()
	frappe.delete_doc("AA Policy Document", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ===========================================================================
# ADMIN - TEST / DISSEMINATION ENVIRONMENT
# ===========================================================================

@frappe.whitelist()
def get_testing_status():
	"""Whether the test/dissemination environment is on, plus a quick test count.
	Approvers and admins use this to show/hide the Testing Environment button and
	the Test Data widget, the active batch name, and who switched testing on."""
	_require_approver()
	settings = frappe.get_single("Anticipatory Action Settings")
	enabled = bool(settings.testing_enabled)
	count = frappe.db.count("Anticipatory Action", {"is_test": 1}) if enabled else 0
	enabled_by = None
	if settings.testing_enabled_by:
		enabled_by = frappe.db.get_value("User", settings.testing_enabled_by, "full_name") or settings.testing_enabled_by
	return {
		"success": True,
		"enabled": enabled,
		"count": count,
		"can_toggle": _is_admin(),
		"batch_name": settings.test_batch_name or None,
		"enabled_by": enabled_by,
		"enabled_on": str(settings.testing_enabled_on) if settings.testing_enabled_on else None,
		# True when nobody else owns the active run (so the UI can word the
		# confirm prompt accordingly).
		"is_mine": (not settings.testing_enabled_by) or settings.testing_enabled_by == frappe.session.user,
	}


@frappe.whitelist()
def set_testing_enabled(enabled, batch_name=None, force=0):
	"""Switch the test/dissemination environment on or off (full admins only).

	Turning ON requires a batch name (e.g. "Garissa testing 2026"); every entry
	submitted through the test form while it is on is tagged with that batch. We
	also record who turned it on and when. Turning OFF while a *different* admin
	owns the active run returns ``needs_confirm`` (with who/when) instead of
	switching it off, so the console can warn before interrupting someone else's
	testing — pass ``force=1`` to proceed anyway. When off, the public test form
	refuses submissions and the console hides the test button + widget."""
	_require_admin()
	on = 1 if str(enabled).lower() in ("1", "true", "yes", "on") else 0
	forced = str(force).lower() in ("1", "true", "yes", "on")
	settings = frappe.get_single("Anticipatory Action Settings")

	if on:
		bn = (batch_name or settings.test_batch_name or "").strip()
		if not bn:
			frappe.throw('Please name this test (e.g. "Garissa testing 2026") before turning the test environment on.')
		settings.testing_enabled = 1
		settings.test_batch_name = bn
		settings.testing_enabled_by = frappe.session.user
		settings.testing_enabled_on = frappe.utils.now_datetime()
	else:
		if (settings.testing_enabled and settings.testing_enabled_by
				and settings.testing_enabled_by != frappe.session.user and not forced):
			owner = frappe.db.get_value("User", settings.testing_enabled_by, "full_name") or settings.testing_enabled_by
			return {
				"success": False,
				"needs_confirm": True,
				"enabled_by": owner,
				"enabled_on": str(settings.testing_enabled_on) if settings.testing_enabled_on else None,
				"batch_name": settings.test_batch_name or None,
			}
		settings.testing_enabled = 0
		settings.testing_enabled_by = None
		settings.testing_enabled_on = None

	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()
	return {"success": True, "enabled": bool(on), "batch_name": settings.test_batch_name or None}


@frappe.whitelist()
def list_test_submissions(status=None):
	"""Test/dissemination submissions only, for the admin Test Data widget."""
	_require_approver()
	from anticipatory_action.anticipatory_action.page.aa_operations.aa_operations import get_activations

	return {"success": True, "data": get_activations(status=status, test_only=1)}


@frappe.whitelist()
def update_organization(
	name, name_of_organization=None, type_of_organization=None, primary_contact_person_name=None,
	primary_phone_contact=None, primary_email_contact=None, organization_phone=None,
	organization_email=None, organization_website=None, address=None,
	about=None, narrative=None, logo=None, pillars_involved=None, aa_support=None,
	show_on_website=None,
):
	"""Edit an organization (full admins only; approvers are read-only)."""
	_require_admin()
	if not frappe.db.exists("Anticipatory Action Organization", name):
		frappe.throw("Unknown organization.")
	doc = frappe.get_doc("Anticipatory Action Organization", name)
	for field, value in (
		("name_of_organization", name_of_organization),
		("type_of_organization", type_of_organization),
		("primary_contact_person_name", primary_contact_person_name),
		("primary_phone_contact", primary_phone_contact),
		("primary_email_contact", primary_email_contact),
		("organization_phone", organization_phone),
		("organization_email", organization_email),
		("organization_website", organization_website),
		("address", address),
		("about", about),
		("narrative", narrative),
		("logo", logo),
		("pillars_involved", pillars_involved),
		("aa_support", aa_support),
	):
		if value is not None:
			doc.set(field, value)
	if show_on_website is not None:
		doc.show_on_website = _as_bool(show_on_website)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def get_organization(name):
	"""Full detail of one organization (for the view/edit widget)."""
	_require_approver()
	return {"success": True, "data": frappe.get_doc("Anticipatory Action Organization", name).as_dict()}


# ===========================================================================
# PILLAR LEADS
# ===========================================================================

PILLARS = (
	"Early Warning", "Early Action", "Coordination and Governance", "Research and Learning",
	"Policy and Advocacy", "Financing", "Monitoring and Evaluation",
)


@frappe.whitelist()
def list_pillar_leads():
	"""Every pillar with its currently assigned lead (admins set these)."""
	_require_approver()
	existing = {r.pillar: r for r in frappe.get_all(
		"AA Pillar Lead", fields=["pillar", "lead", "lead_name", "lead_email"], limit=50)}
	rows = []
	for pillar in PILLARS:
		r = existing.get(pillar)
		rows.append({
			"pillar": pillar,
			"lead": r.lead if r else None,
			"lead_name": r.lead_name if r else None,
			"lead_email": r.lead_email if r else None,
		})
	return {"success": True, "data": rows}


@frappe.whitelist()
def set_pillar_lead(pillar, lead=None):
	"""Assign (or clear) the lead for a pillar. Admins only."""
	_require_admin()
	if pillar not in PILLARS:
		frappe.throw("Unknown pillar.")
	lead = (lead or "").strip() or None
	if lead and not frappe.db.exists("Anticipatory Action User", lead):
		frappe.throw("Please choose a valid Anticipatory Action member as the lead.")
	if frappe.db.exists("AA Pillar Lead", pillar):
		doc = frappe.get_doc("AA Pillar Lead", pillar)
	else:
		doc = frappe.new_doc("AA Pillar Lead")
		doc.pillar = pillar
	doc.lead = lead
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def list_aa_reviewers(search=None):
	"""AA members who can be a pillar lead: Approvers and Admins only."""
	_require_approver()
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"full_name": ["like", like], "email": ["like", like]}
	rows = frappe.get_all(
		"Anticipatory Action User",
		filters={"role": ["in", ["Anticipatory Action Approver", "Anticipatory Action Admin"]], "enabled": 1},
		or_filters=or_filters,
		fields=["name", "full_name", "email", "role"],
		order_by="full_name asc",
		limit=500,
	)
	return {"success": True, "data": rows}


# ===========================================================================
# CHANGE LOG (who changed what - exposes track_changes history in the UI)
# ===========================================================================

# Only AA doctypes may be inspected through the portal.
_AUDITABLE = {
	"Anticipatory Action", "Anticipatory Report", "Anticipatory Activity",
	"Anticipatory Action Organization", "Anticipatory Action Reference Documents",
	"AA Membership Request", "AA Support Request", "AA Contact Message",
	"AA Pillar Lead", "AA FAQ", "Anticipatory Action User",
}

# The subset of auditable doctypes that hold per-organisation (tenant) data. A
# non-admin Approver may only read the change log of one of these when the record
# belongs to their own organisation (SEC-003). The rest of _AUDITABLE is
# programme-wide content that approvers already curate across every organisation.
_ORG_SCOPED_AUDITABLE = {
	"Anticipatory Action", "Anticipatory Action User",
	"Anticipatory Action Organization", "AA Membership Request",
}


def _assert_auditable_in_scope(doctype, name):
	"""Confine a non-admin Approver's change-log reads to their own organisation
	for the tenant-scoped record types. Full admins / System Managers are
	unrestricted. Raises PermissionError when the record is out of scope."""
	if reviewer_owner_scope() is None:
		return  # admin / System Manager — the full picture
	if doctype not in _ORG_SCOPED_AUDITABLE:
		return  # programme-wide content, not organisation-partitioned
	if doctype == "Anticipatory Action":
		_assert_submission_in_scope(name)
		return
	if doctype == "AA Membership Request":
		# Pre-account applicant PII — only account approvers may audit it, and a
		# membership request has no reliable link to an AA Organization yet.
		if not _can_approve_accounts():
			frappe.throw("This record belongs to another organization.", frappe.PermissionError)
		return
	org = _user_org()
	record_org = (name if doctype == "Anticipatory Action Organization"
				  else frappe.db.get_value("Anticipatory Action User", name, "organization"))
	if not org or record_org != org:
		frappe.throw("This record belongs to another organization.", frappe.PermissionError)


@frappe.whitelist()
def get_change_log(doctype, name):
	"""Who created and changed a record, and what changed. Reads Frappe's Version
	history (populated because these doctypes have track_changes on)."""
	_require_approver()
	if doctype not in _AUDITABLE:
		frappe.throw("This record type cannot be audited here.")
	if not frappe.db.exists(doctype, name):
		frappe.throw("Unknown record.")
	# SEC-003: _require_approver alone lets an Approver read any auditable record's
	# field-level history (incl. another org's members / submissions). Scope it.
	_assert_auditable_in_scope(doctype, name)

	meta = frappe.get_meta(doctype)

	def _label(fieldname):
		df = meta.get_field(fieldname)
		return df.label if df and df.label else fieldname

	base = frappe.db.get_value(doctype, name, ["owner", "creation"], as_dict=True) or {}
	entries = [{
		"by": base.get("owner"),
		"by_name": frappe.db.get_value("User", base.get("owner"), "full_name") or base.get("owner"),
		"on": str(base.get("creation")),
		"action": "Created",
		"changes": [],
	}]

	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": doctype, "docname": name},
		fields=["owner", "creation", "data"],
		order_by="creation asc",
		limit=200,
	)
	for v in versions:
		try:
			data = frappe.parse_json(v.data) or {}
		except Exception:
			data = {}
		changes = []
		for ch in (data.get("changed") or []):
			# ch = [fieldname, old, new]
			if len(ch) >= 3:
				changes.append({"field": _label(ch[0]), "from": ch[1], "to": ch[2]})
		row_changes = bool(data.get("added") or data.get("removed") or data.get("row_changed"))
		if not changes and not row_changes:
			continue
		entries.append({
			"by": v.owner,
			"by_name": frappe.db.get_value("User", v.owner, "full_name") or v.owner,
			"on": str(v.creation),
			"action": "Updated",
			"changes": changes,
			"detail_changed": row_changes,
		})

	entries.reverse()  # newest first
	return {"success": True, "data": _sanitize(entries)}


# ===========================================================================
# SUPPORT REQUESTS (approvers raise requests; members report problems)
# ===========================================================================

@frappe.whitelist()
def submit_support_request(subject, message, request_type=None, priority="Medium"):
	"""A signed-in member or approver raises a request / problem report."""
	_require_login()
	if not (subject or "").strip() or not (message or "").strip():
		frappe.throw("Please provide a subject and details.")
	# Approvers/admins make 'Request's; plain members 'Report a problem'.
	default_type = "Request" if _can_review() else "Problem"
	request_type = request_type if request_type in ("Request", "Problem") else default_type
	doc = frappe.get_doc({
		"doctype": "AA Support Request",
		"subject": subject, "message": message, "request_type": request_type,
		"priority": priority if priority in ("Low", "Medium", "High") else "Medium",
		"status": "New", "raised_by": frappe.session.user,
		"raised_by_role": "Approver" if _can_review() else "Member",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def list_my_support_requests():
	"""The signed-in user's own support requests / problem reports."""
	_require_login()
	rows = frappe.get_all(
		"AA Support Request", filters={"raised_by": frappe.session.user},
		fields=["name", "subject", "request_type", "status", "priority", "response", "submitted_on", "creation"],
		order_by="creation desc", limit=200)
	return {"success": True, "data": rows}


@frappe.whitelist()
def list_support_requests(status=None):
	"""Admin triage queue: all support requests / problem reports."""
	_require_admin()
	filters = {"status": status} if status else {}
	rows = frappe.get_all(
		"AA Support Request", filters=filters,
		fields=["name", "subject", "request_type", "status", "priority", "raised_by",
				"raised_by_role", "response", "submitted_on", "creation"],
		order_by="creation desc", limit=500)
	return {"success": True, "data": rows}


@frappe.whitelist()
def update_support_request(name, status=None, response=None):
	"""Admin updates the status / response on a support request."""
	_require_admin()
	if not frappe.db.exists("AA Support Request", name):
		frappe.throw("Unknown request.")
	doc = frappe.get_doc("AA Support Request", name)
	if status is not None:
		if status not in ("New", "Open", "Resolved", "Closed"):
			frappe.throw("Invalid status.")
		doc.status = status
	if response is not None:
		doc.response = response
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return {"success": True}


def _select_options(doctype, fieldname):
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or not field.options:
		return []
	return [o for o in field.options.split("\n") if o.strip()]


@frappe.whitelist()
def get_admin_meta():
	"""Live Select options for the admin console forms — sourced from the
	doctypes themselves so the dropdowns never drift from the schema."""
	_require_approver()
	return {
		"success": True,
		"organization_types": _select_options("Anticipatory Action Organization", "type_of_organization"),
		"publication_types": _select_options("Anticipatory Action Reference Documents", "type"),
		"report_categories": _select_options("Anticipatory Report", "category"),
		"faq_categories": _select_options("AA FAQ", "category"),
		"pillars": _select_options("Anticipatory Activity", "pillar"),
		"activity_statuses": _select_options("Anticipatory Activity", "status"),
		"roles": sorted(AA_ROLES),
		"caps": {
			"is_admin": _is_admin(),          # manage users, orgs, sign-ups
			"is_system_manager": _can_set_role(),  # may assign roles
		},
	}


# ===========================================================================
# SIGN-UP / MEMBERSHIP REQUESTS
# ===========================================================================

def _create_membership_request(first_name, last_name=None, email=None, phone=None,
							   organization=None, position=None, message=None):
	"""Core sign-up-request logic, shared by the public endpoint and guest checkout.

	Enumeration-safe (SEC-005): a repeat email — one already queued as Pending, or
	one that already has an AA account — returns the SAME neutral success as a
	brand-new request and creates nothing, so an anonymous caller cannot tell which
	emails are registered. Validation errors are still surfaced (they describe the
	input shape, not whether an account exists)."""
	from frappe.utils import validate_email_address

	# Everything is required except the free-text "Why would you like access?"
	# (message). Mirror the form's required fields server-side and name the specific
	# missing field: a single generic "fill in all fields" message was read as
	# "reason for joining" (the one OPTIONAL field) when a required field such as
	# Position was actually the one left blank.
	first_name = (first_name or "").strip()
	last_name = (last_name or "").strip()
	email = (email or "").strip().lower()
	phone = (phone or "").strip()
	organization = (organization or "").strip()
	position = (position or "").strip()
	if not first_name:
		return {"success": False, "error": "Please enter your first name."}
	if not email:
		return {"success": False, "error": "Please enter your email address."}
	if not validate_email_address(email):
		return {"success": False, "error": "Please enter a valid email address."}
	if not phone:
		return {"success": False, "error": "Please enter your phone number."}
	if not organization:
		return {"success": False, "error": "Please choose or enter your organisation."}
	if not position:
		return {"success": False, "error": "Please enter your position or role — it is required."}
	if (frappe.db.exists("AA Membership Request", {"email": email, "status": "Pending"})
			or frappe.db.exists("Anticipatory Action User", {"email": email})):
		# Neutral no-op — do not reveal that this email is already known. (The guest
		# checkout flow catches an already-registered email earlier and steers the
		# person to sign in; this remains the safe default for the public form.)
		return {"success": True}
	try:
		doc = frappe.get_doc({
			"doctype": "AA Membership Request",
			"first_name": first_name, "last_name": last_name, "email": email,
			"phone": phone, "organization": organization, "position": position,
			"message": message, "status": "Pending",
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		frappe.db.commit()
		_email_request_received(doc)
		_email_request_admins(doc)
		return {"success": True}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "submit_membership_request")
		return {"success": False, "error": "Could not submit your request. Please try again."}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=200, seconds=60 * 60)
def submit_membership_request(first_name, last_name=None, email=None, phone=None,
							  organization=None, position=None, message=None):
	"""Public self-service sign-up: creates a Pending request for an admin to
	approve or reject. No login account is created until it is approved.
	Rate limited per IP (SEC-004)."""
	return _create_membership_request(
		first_name=first_name, last_name=last_name, email=email, phone=phone,
		organization=organization, position=position, message=message,
	)


_CONTACT_TYPES = ("General enquiry", "Get involved", "Join a pillar", "Report a problem")


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=100, seconds=60 * 60)
def submit_contact(full_name=None, email=None, organization=None, phone=None, subject=None,
				   message=None, request_type=None, pillar=None):
	"""Public 'Contact us' form. Lives here (an importable module) rather than the
	hyphenated www controller, whose dotted path cannot be imported by /api/method.
	A 'Join a pillar' / 'Get involved' request is routed to the relevant pillar lead.
	Rate limited per IP (SEC-004)."""
	from frappe.utils import validate_email_address

	full_name = (full_name or "").strip()
	email = (email or "").strip()
	subject = (subject or "").strip()
	message = (message or "").strip()
	request_type = request_type if request_type in _CONTACT_TYPES else "General enquiry"
	pillar = (pillar or "").strip() or None
	if not full_name or not email or not subject or not message:
		return {"success": False, "error": "Please fill in your name, email, subject and message."}
	if not validate_email_address(email):
		return {"success": False, "error": "Please enter a valid email address."}
	try:
		doc = frappe.get_doc({
			"doctype": "AA Contact Message",
			"full_name": full_name, "email": email, "organization": organization,
			"phone": phone, "subject": subject, "message": message, "status": "New",
			"request_type": request_type, "pillar": pillar,
		})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		if pillar and request_type in ("Join a pillar", "Get involved"):
			_route_to_pillar_lead(doc, pillar)
		return {"success": True}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "submit_contact")
		return {"success": False, "error": "Could not send your message. Please try again."}


def _route_to_pillar_lead(msg, pillar):
	"""Email the pillar lead AND the central AA inbox, and leave the lead an in-app
	notification, about a new get-involved / join-a-pillar enquiry."""
	try:
		from anticipatory_action.api.aa_email import portal_url
		row = frappe.db.get_value("AA Pillar Lead", pillar, ["lead", "lead_email"], as_dict=True) or {}
		lead_email = (row.get("lead_email") or "").strip()
		lead_user = frappe.db.get_value("Anticipatory Action User", row.lead, "user") if row.get("lead") else None
		body = (
			"<p>A new enquiry has come in through the website for the "
			"<strong>" + frappe.utils.escape_html(pillar) + "</strong> pillar. The details are below.</p>"
		)
		rows = [
			("From", frappe.utils.escape_html(msg.full_name) + "<br>" + frappe.utils.escape_html(msg.email)),
			("Organisation", frappe.utils.escape_html(msg.organization) if msg.organization else "-"),
			("Type", frappe.utils.escape_html(msg.request_type or "-")),
			("Message", frappe.utils.escape_html(msg.message or "-")),
		]
		html = aa_email_html(
			"New enquiry for the " + pillar + " pillar", body, rows=rows,
			cta_label="Open the admin console", cta_url=portal_url("/aa-admin"),
			chip="New enquiry", chip_tone="blue",
		)
		# Both the pillar lead and the central AA inbox are notified.
		recipients = [e for e in [lead_email, AA_INBOX] if e]
		aa_sendmail(recipients, "New enquiry - " + pillar + " pillar", html)
		if lead_user:
			with contextlib.suppress(Exception):
				frappe.get_doc({
					"doctype": "Notification Log",
					"subject": f"New {msg.request_type}: {pillar}",
					"email_content": f"{msg.full_name} is interested in the {pillar} pillar.",
					"for_user": lead_user, "type": "Alert",
					"document_type": "AA Contact Message", "document_name": msg.name,
				}).insert(ignore_permissions=True)
		else:
			# No lead is assigned to this pillar yet: the enquiry still lands in the
			# central inbox, but nobody owns it. Alert every admin in-system to
			# appoint a pillar lead so future enquiries reach an owner.
			with contextlib.suppress(Exception):
				admins = frappe.get_all(
					"Anticipatory Action User",
					filters={"role": "Anticipatory Action Admin", "enabled": 1},
					pluck="user",
				)
				for admin_user in {a for a in admins if a}:
					frappe.get_doc({
						"doctype": "Notification Log",
						"subject": f"Pillar lead needed: {pillar}",
						"email_content": (
							f"A new {msg.request_type} enquiry came in for the {pillar} pillar, "
							f"which has no lead assigned. Set a pillar lead in the admin console "
							f"so future enquiries reach an owner."
						),
						"for_user": admin_user, "type": "Alert",
						"document_type": "AA Contact Message", "document_name": msg.name,
					}).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "route_to_pillar_lead")


# WKF-004: the most submissions one email may hold against a pending sign-up request.
_GUEST_HELD_CAP = 10


def _has_account(email):
	"""Does this email already have a sign-in account (an AA member, or a Frappe
	User managed by another project on this shared site)? Used to steer a returning
	visitor to sign in instead of filing another access request."""
	email = (email or "").strip().lower()
	if not email:
		return False
	return bool(
		frappe.db.exists("Anticipatory Action User", {"email": email})
		or _foreign_roles(email)
		or frappe.db.exists("User", {"name": email, "enabled": 1})
	)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60 * 60)
def guest_email_status(email):
	"""Guest sign-up helper: report whether an email already has an account so the
	submission form can steer a returning user to sign in rather than file a
	duplicate access request.

	This intentionally trades a little enumeration-safety — an anonymous caller can
	learn that an email is registered — for the sign-in-vs-sign-up UX the platform
	owner asked for. The per-IP rate limit blunts bulk scraping."""
	from frappe.utils import validate_email_address

	email = (email or "").strip().lower()
	if not email or not validate_email_address(email):
		return {"success": True, "registered": False}
	return {"success": True, "registered": _has_account(email)}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60 * 60)
def list_public_organizations():
	"""Public, minimal list of organisation names for the guest sign-up dropdown —
	names only, no contact details — so a returning organisation's people can pick
	their employer from the list instead of retyping it (with an "Other" fallback
	handled client-side)."""
	names = sorted({
		(o.name_of_organization or "").strip()
		for o in frappe.get_all(
			"Anticipatory Action Organization",
			fields=["name_of_organization"], limit=1000,
		)
	} - {""})
	return {"success": True, "data": names}


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=200, seconds=60 * 60)
def submit_guest_application(submission, account):
	"""Guest checkout: a visitor fills the whole submission form, then provides
	account details at the end. We create BOTH a Pending sign-up request and the
	submission, link them, and hold the submission (``awaiting_account``) out of
	the review queue until an admin approves the account — at which point
	``approve_request`` releases it and re-assigns ownership to the new member.
	Rate limited per IP (SEC-004)."""
	from frappe.utils import validate_email_address

	from anticipatory_action.api.anticipatory_action import _insert_submission

	acc = frappe.parse_json(account) if isinstance(account, str) else (account or {})
	first_name = (acc.get("first_name") or "").strip()
	email = (acc.get("email") or "").strip().lower()
	if not first_name or not email:
		return {"success": False, "error": "Your name and email are required to submit."}
	if not validate_email_address(email):
		return {"success": False, "error": "Please enter a valid email address."}

	# A returning visitor whose email already has an account is steered to sign in
	# rather than filing another access request (platform-owner request). Nothing is
	# created — no held submission, no duplicate request — so they land in the
	# authenticated flow where they can submit directly and see their own history.
	if _has_account(email):
		return {
			"success": False, "already_registered": True,
			"error": ("An account with this email already exists. "
					  "Please sign in to submit your anticipatory action."),
		}

	# A submission's whole point is its intervention rows. Reject an empty one up
	# front — BEFORE creating the sign-up request — so a hollow submission neither
	# files a held record nor leaves an orphan access request behind.
	sub = frappe.parse_json(submission) if isinstance(submission, str) else (submission or {})
	if not (isinstance(sub, dict) and (sub.get("anticipatory_action_details") or [])):
		return {"success": False, "error": "Please add at least one anticipatory action entry before submitting."}

	# 1) sign-up request. Call the enumeration-safe core directly (not the
	#    rate-limited public endpoint) so one guest checkout isn't charged two
	#    per-IP limits. It no-ops on a repeat/known email — the flow below then
	#    behaves identically whether or not the email is already registered
	#    (SEC-005) and never creates a duplicate account.
	req_result = _create_membership_request(
		first_name=first_name, last_name=acc.get("last_name"), email=email,
		phone=acc.get("phone"), organization=acc.get("organization"),
		position=acc.get("position"), message=acc.get("message"),
	)
	if not req_result.get("success"):
		return req_result  # surfaced validation error (bad phone / missing field)
	req_name = frappe.db.get_value(
		"AA Membership Request", {"email": email, "status": "Pending"}, "name"
	)

	# WKF-004: cap how many submissions one email can hold against a pending sign-up.
	# Without this, repeated guest checkouts pile unlimited held rows onto one request,
	# and a single approval silently absorbs them all under the new member's name.
	if frappe.db.count("Anticipatory Action", {"reporter_email": email, "awaiting_account": 1}) >= _GUEST_HELD_CAP:
		return {"success": False, "error": (
			"You already have several submissions waiting for your account to be approved. "
			"Please wait for the approval email, then sign in to add more."
		)}

	# 2) the submission itself, stamped with the reporter's email and held out of
	#    the review queue. Created whether or not the email is already known, so the
	#    response shape is identical either way. (For an already-registered email
	#    there is no Pending request to link to; the reporter should sign in instead.)
	try:
		sub.setdefault("reporter_email", email)
		doc = _insert_submission(frappe.as_json(sub), is_test=0)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "submit_guest_application")
		return {"success": False, "error": "Submission failed. Please try again or contact support."}
	frappe.db.set_value("Anticipatory Action", doc.name, {
		"linked_request": req_name,
		"awaiting_account": 1,
		"reporter_email": email,
	}, update_modified=False)
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def list_requests(status=None):
	_require_account_approver()
	filters = {"status": status} if status else {}
	rows = frappe.get_all(
		"AA Membership Request",
		filters=filters,
		fields=["name", "full_name", "email", "phone", "organization", "position",
				"status", "creation", "reviewed_by", "reviewed_on", "user",
				"pending_info_request"],
		order_by="creation desc",
		limit=500,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def get_request(name):
	_require_account_approver()
	data = frappe.get_doc("AA Membership Request", name).as_dict()
	# Surface any submissions held against this sign-up (guest-checkout flow) so the
	# reviewer can see that an application is waiting on this account being approved.
	data["held_submissions"] = frappe.get_all(
		"Anticipatory Action",
		filters={"linked_request": name, "awaiting_account": 1},
		fields=["name", "implementing_organization", "anticipated_hazard"],
		limit=20,
	)
	return {"success": True, "data": data}


@frappe.whitelist()
def approve_request(name, organization, role=None, notes=None):
	"""Approve a sign-up: provision the AA account (roster record -> System User
	+ welcome email) and mark the request Approved."""
	_require_account_approver()
	req = frappe.get_doc("AA Membership Request", name)
	if req.status == "Approved":
		frappe.throw("This request has already been approved.")
	# Only a System Manager may choose the role; otherwise it is taken from the
	# request's (System-Manager-controlled) Role field, defaulting to member.
	role = (role if _can_set_role() and role else None) or req.role or "Anticipatory Action User"
	_constrain_role(role)
	if not organization or not frappe.db.exists("Anticipatory Action Organization", organization):
		frappe.throw("Please choose a valid organization for this member.")
	if not (req.phone or "").strip():
		frappe.throw("This request has no phone number — edit the request and add one before approving.")
	email = (req.email or "").strip().lower()
	if frappe.db.exists("Anticipatory Action User", {"email": email}):
		frappe.throw("An Anticipatory Action user with this email already exists.")
	if _foreign_roles(email):
		frappe.throw("A user with this email already exists on this site and is managed elsewhere.")

	# The roster requires a last name, but guest checkout collects it as optional, so
	# a request may legitimately have none. Default to "-" (the same placeholder the
	# roster self-heal uses) rather than dead-ending the approval on a raw mandatory
	# error the approver has no UI to fix.
	roster = frappe.get_doc({
		"doctype": "Anticipatory Action User",
		"first_name": req.first_name, "last_name": (req.last_name or "").strip() or "-",
		"email": email, "phone": req.phone, "organization": organization,
		"role": role, "enabled": 1,
	})
	roster.flags.ignore_permissions = True
	with _elevated():
		roster.insert()

	req.status = "Approved"
	req.review_notes = notes
	req.reviewed_by = frappe.session.user
	req.reviewed_on = frappe.utils.now_datetime()
	req.user = roster.user or email
	req.flags.ignore_permissions = True
	req.save()

	# Release any submission held against this sign-up (guest-checkout flow): hand it
	# to the new member and let it into the review queue. If a reviewer previously
	# asked for more information (request_more_info), that message was deliberately
	# held back — the applicant had no account to answer with — so deliver it now:
	# the released submission lands as "Replied" carrying the reviewer's question.
	new_owner = roster.user or email
	info_msg = (req.pending_info_request or "").strip()
	released = frappe.get_all(
		"Anticipatory Action",
		filters={"linked_request": req.name, "awaiting_account": 1},
		pluck="name",
	)
	for held in released:
		frappe.db.set_value("Anticipatory Action", held, {
			"awaiting_account": 0,
			"owner": new_owner,
			"status": "Replied" if info_msg else "Pending",
			"info_request": info_msg or None,
		}, update_modified=False)

	frappe.db.commit()

	# Now that the applicant has a login, send any held "more information" request.
	if info_msg:
		for held in released:
			with contextlib.suppress(Exception):
				send_submission_replied(frappe.get_doc("Anticipatory Action", held), info_msg)
		if not released:
			# No held submission to carry the message (e.g. a public sign-up that was
			# sent back for info): deliver it as a standalone note so it is not lost.
			_email_request_more_info(req, info_msg)

	return {"success": True, "user": roster.user}


@frappe.whitelist()
def request_more_info(name, message=None):
	"""Reviewer asks a sign-up applicant for more information.

	Per the guest-checkout workflow this is NOT emailed while the account is pending
	— an applicant with no account cannot sign in to answer. The message is stored on
	the request and only sent when the account is approved (see approve_request),
	which is also when any held submission is released for the member to revise. The
	request stays Pending so it remains actionable."""
	_require_account_approver()
	msg = (message or "").strip()
	if not msg:
		frappe.throw("Please write the information you need from the applicant.")
	req = frappe.get_doc("AA Membership Request", name)
	if req.status != "Pending":
		frappe.throw("Only a pending request can be sent back for more information.")
	req.pending_info_request = msg
	req.flags.ignore_permissions = True
	req.save()
	frappe.db.commit()
	return {"success": True}


@frappe.whitelist()
def reject_request(name, notes=None):
	"""Decline a sign-up. A reason is required and is emailed to the applicant."""
	_require_account_approver()
	reason = (notes or "").strip()
	if not reason:
		frappe.throw("Please provide a reason for rejection — it is shared with the applicant.")
	req = frappe.get_doc("AA Membership Request", name)
	if req.status == "Approved":
		frappe.throw("This request has already been approved and cannot be rejected.")
	req.status = "Rejected"
	req.review_notes = reason
	req.reviewed_by = frappe.session.user
	req.reviewed_on = frappe.utils.now_datetime()
	req.flags.ignore_permissions = True
	req.save()

	# Discard any submission held against this now-declined sign-up: it has no owner
	# and would otherwise linger forever awaiting an account that will never exist.
	# Held submissions are unsubmitted drafts (docstatus 0), so deletion is clean.
	for held in frappe.get_all(
		"Anticipatory Action",
		filters={"linked_request": req.name, "awaiting_account": 1},
		pluck="name",
	):
		with contextlib.suppress(Exception):
			frappe.delete_doc("Anticipatory Action", held, ignore_permissions=True, force=True)

	frappe.db.commit()
	_email_request_rejected(req, reason)
	return {"success": True}


def _email_request_received(req):
	"""Acknowledge a new access request so the applicant knows it arrived."""
	if not (req.email or "").strip():
		return
	try:
		name = frappe.utils.escape_html((req.first_name or "there").strip())
		body = (
			"<p>Dear " + name + ",</p>"
			"<p>Thank you for requesting access to the Kenya Anticipatory Action platform. This "
			"confirms that your request has been received.</p>"
			"<p>The National Technical Working Group (TWG) Secretariat is now reviewing your request "
			"and will respond in due course. If your request is approved, you'll receive a follow-up "
			"email with a secure link to set your password and sign in.</p>"
			"<p>There's nothing further you need to do in the meantime.</p>"
		)
		html = aa_email_html(
			"Thank you for your interest", body,
			chip="Request received", chip_tone="slate",
			sign_off='Questions? Write to us at <a href="mailto:' + AA_INBOX + '" style="color:#CC0000">' + AA_INBOX + '</a>.',
		)
		aa_sendmail([req.email], "We've received your access request", html)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "request_received email")


def _email_request_admins(req):
	"""Alert the people who action sign-ups that a new access request has arrived: a
	branded email to the AA inbox and every account approver, plus an in-app
	notification so it surfaces in the admin console. Fully wrapped so a mail hiccup
	never fails the applicant's request."""
	try:
		from anticipatory_action.api.aa_email import portal_url

		# Everyone who can act on a sign-up: every enabled AA Admin, plus Approvers an
		# admin has granted the account-approval capability.
		approvers = [
			a for a in frappe.get_all(
				"Anticipatory Action User",
				filters={"enabled": 1, "role": ["in", [
					"Anticipatory Action Admin", "Anticipatory Action Approver"]]},
				fields=["email", "user", "role", "can_approve_accounts"],
			)
			if a.role == "Anticipatory Action Admin" or a.can_approve_accounts
		]

		full_name = ((req.first_name or "") + " " + (req.last_name or "")).strip() or (req.email or "someone")
		body = (
			"<p>A new request for access to the Kenya Anticipatory Action platform has just come in. "
			"Open the admin console to approve it, decline it, or ask the applicant for more "
			"information.</p>"
		)
		rows = [
			("Name", frappe.utils.escape_html(full_name)),
			("Email", frappe.utils.escape_html(req.email or "-")),
			("Phone", frappe.utils.escape_html(req.phone or "-")),
			("Organisation", frappe.utils.escape_html(req.organization or "-")),
			("Position", frappe.utils.escape_html(req.position or "-")),
		]
		if (req.message or "").strip():
			rows.append(("Message", frappe.utils.escape_html(req.message)))
		html = aa_email_html(
			"New access request", body, rows=rows,
			cta_label="Review in the admin console", cta_url=portal_url("/aa-admin"),
			chip="Action needed", chip_tone="amber",
		)
		recipients = sorted({e for e in ([AA_INBOX] + [(a.email or "").strip() for a in approvers]) if e})
		if recipients:
			aa_sendmail(recipients, "New access request - " + full_name, html)

		for a in approvers:
			login = (a.user or "").strip()
			if not login:
				continue
			with contextlib.suppress(Exception):
				frappe.get_doc({
					"doctype": "Notification Log",
					"subject": "New access request: " + full_name,
					"email_content": full_name + " has requested access to the AA platform.",
					"for_user": login, "type": "Alert",
					"document_type": "AA Membership Request", "document_name": req.name,
				}).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "email_request_admins")


def _email_request_more_info(req, message):
	"""Deliver a reviewer's 'more information' request to an applicant at approval
	time. Used only when there is no held submission to carry the message (e.g. a
	public sign-up that was sent back for info); the guest-checkout path carries the
	message on the released submission via send_submission_replied instead."""
	if not (req.email or "").strip():
		return
	try:
		from anticipatory_action.api.aa_email import portal_url

		name = frappe.utils.escape_html((req.first_name or "there").strip())
		body = (
			"<p>Dear " + name + ",</p>"
			"<p>Your access to the Kenya Anticipatory Action platform has been approved. Before the "
			"National TWG Secretariat finishes reviewing your request, we'd be grateful if you could "
			"help us with the following:</p>"
			'<div style="margin:16px 0;padding:13px 16px;background:#FFFBEB;border-left:3px solid #B45309;'
			'color:#5c3a10;font-size:13.5px;line-height:1.55;border-radius:0 6px 6px 0">'
			+ frappe.utils.escape_html(message or "-").replace("\n", "<br/>") +
			'</div>'
			"<p>You can reply to this email, or sign in to the portal to continue.</p>"
		)
		html = aa_email_html(
			"A little more information, please", body,
			cta_label="Open the portal", cta_url=portal_url("/aa-portal"),
			chip="Action needed", chip_tone="amber",
		)
		aa_sendmail([req.email], "More information needed", html)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "email_request_more_info")


def _email_request_rejected(req, reason):
	"""Notify an applicant that their access request was not approved."""
	if not (req.email or "").strip():
		return
	try:
		name = frappe.utils.escape_html((req.first_name or "there").strip())
		body = (
			"<p>Dear " + name + ",</p>"
			"<p>Thank you for your interest in the Kenya Anticipatory Action platform. After careful "
			"review, the National TWG Secretariat is unable to approve your access request at this "
			"time.</p>"
			'<div style="margin:16px 0;padding:13px 16px;background:#FEF2F2;border-left:3px solid #CC0000;'
			'color:#5b1e1e;font-size:13.5px;line-height:1.55;border-radius:0 6px 6px 0">'
			'<span style="display:block;font-size:11px;font-weight:700;letter-spacing:0.06em;'
			'text-transform:uppercase;color:#6B7280;margin-bottom:5px">Reason</span>'
			+ frappe.utils.escape_html(reason or "-") +
			'</div>'
			"<p>If you believe this was made in error, or you can provide further information to "
			'support your request, please reply to this email or contact <a href="mailto:' + AA_INBOX
			+ '" style="color:#CC0000">' + AA_INBOX + "</a>. We'd be glad to take another look.</p>"
		)
		html = aa_email_html(
			"Regarding your access request", body,
			chip="Not approved", chip_tone="red",
		)
		aa_sendmail([req.email], "An update on your access request", html)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "reject_request email")
