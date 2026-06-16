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
from frappe.utils import strip_html

from anticipatory_action.api.anticipatory_action import _sanitize
from anticipatory_action.api.permissions import _can_review, _is_admin

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


def _constrain_role(role):
	if role not in AA_ROLES:
		frappe.throw("Invalid role.", frappe.PermissionError)
	return role


def _can_set_role():
	"""Only System Managers may decide a member's role; AA Admins cannot pick or
	escalate it (everyone they create / approve becomes a plain member)."""
	return "System Manager" in frappe.get_roles()


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
	"email_me_a_copy",
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


def _editable(doc):
	"""A submission can still be changed while it is a Draft and not yet approved."""
	return doc.docstatus == 0 and (doc.status or "Pending") in ("Pending", "Not Approved")


@frappe.whitelist()
def get_my_submissions():
	"""The signed-in reporter's own submissions, newest first, with detail rows."""
	_require_login()
	rows = frappe.get_all(
		"Anticipatory Action",
		filters={"owner": frappe.session.user},
		fields=[
			"name", "implementing_organization", "anticipated_hazard",
			"activation_start_date", "activation_end_date", "status",
			"reason_for_rejection", "docstatus", "modified", "creation",
		],
		order_by="modified desc",
		limit=200,
	)
	for r in rows:
		r["can_edit"] = int(r.get("docstatus") == 0 and (r.get("status") or "Pending") in ("Pending", "Not Approved"))
		r["details"] = frappe.get_all(
			"Anticipatory Action Details",
			filters={"parent": r["name"]},
			fields=["county", "sector", "number_of_people_targeted", "amount_for_anticipatory_action_kes", "status_of_the_early_action"],
			order_by="idx asc",
		)
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
	data["can_edit"] = int(_editable(doc))
	data["anticipatory_action_details"] = [
		{f: row.get(f) for f in _DETAIL_FIELDS if f != "name"}
		for row in doc.get("anticipatory_action_details", [])
	]
	return {"success": True, "data": _sanitize(data)}


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
	for f in _PARENT_FIELDS:
		if f in d:
			doc.set(f, d.get(f))

	doc.set("anticipatory_action_details", [])
	for row in (d.get("anticipatory_action_details") or []):
		doc.append("anticipatory_action_details", _detail_row(row))

	doc.status = "Pending"
	doc.reason_for_rejection = None
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
	if doc.owner != frappe.session.user and not _can_review():
		frappe.throw("You can only download your own submissions.", frappe.PermissionError)

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
				"last_name": ud.get("last_name") or "", "email": email,
				"phone": ud.get("phone") or "0000000000", "organization": org,
				"role": role, "enabled": 1})
			doc.flags.ignore_permissions = True
			doc.insert()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ensure_roster_for_aa_users")
	frappe.db.commit()


@frappe.whitelist()
def list_aa_users(search=None):
	"""Every AA member (anyone holding an AA role), with their roster details.
	Self-heals missing roster records so legacy / desk-created users show up too."""
	_require_admin()
	try:
		_ensure_roster_for_aa_users()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "list_aa_users self-heal")
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"full_name": ["like", like], "email": ["like", like]}
	users = frappe.get_all(
		"Anticipatory Action User",
		or_filters=or_filters,
		fields=[
			"name", "full_name", "first_name", "last_name", "email", "phone",
			"organization", "role", "user", "enabled", "creation",
		],
		order_by="creation desc",
		limit=1000,
	)
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
		role = "Anticipatory Action User"  # AA Admins can only create members
	_constrain_role(role)
	email = (email or "").strip().lower()
	if not email:
		frappe.throw("Email is required.")
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
	if first_name is not None:
		doc.first_name = first_name
	if last_name is not None:
		doc.last_name = last_name
	if phone is not None:
		doc.phone = phone
	if organization is not None:
		if not frappe.db.exists("Anticipatory Action Organization", organization):
			frappe.throw("Please choose a valid organization.")
		doc.organization = organization
	# Only a System Manager may change the role; AA Admins can edit everything else.
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
	data = {f: doc.get(f) for f in _PARENT_FIELDS}
	data.update({
		"name": doc.name,
		"status": doc.status,
		"reason_for_rejection": doc.reason_for_rejection,
		"docstatus": doc.docstatus,
		"supporting_materials": doc.get("supporting_materials"),
		"owner": doc.owner,
		"creation": str(doc.creation),
		"modified": str(doc.modified),
	})
	data["anticipatory_action_details"] = [
		{f: row.get(f) for f in _DETAIL_FIELDS} for row in doc.get("anticipatory_action_details", [])
	]
	return {"success": True, "data": _sanitize(data)}


@frappe.whitelist()
def set_submission_status(name, status, reason=None):
	"""Approve (submit + lock), reject (keep editable for revision), or reset."""
	_require_approver()
	if status not in ("Pending", "Approved", "Not Approved"):
		frappe.throw("Invalid status.")
	if status == "Not Approved" and not (reason or "").strip():
		frappe.throw("Please provide a reason for rejection.")

	doc = frappe.get_doc("Anticipatory Action", name)
	doc.flags.ignore_permissions = True
	reason_val = reason if status == "Not Approved" else None

	if doc.docstatus == 1:
		# Legacy already-submitted docs: status / reason are the only mutable bits.
		doc.db_set("status", status)
		doc.db_set("reason_for_rejection", reason_val)
	elif status == "Approved":
		doc.status = "Approved"
		doc.reason_for_rejection = None
		doc.submit()
	else:
		doc.status = status
		doc.reason_for_rejection = reason_val
		doc.save()

	frappe.db.commit()
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
				"key_words", "link", "attachment", "published"],
		order_by="year desc, modified desc",
		limit=1000,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def get_report(name):
	_require_approver()
	return {"success": True, "data": frappe.get_doc("Anticipatory Report", name).as_dict()}


@frappe.whitelist()
def add_report(title, year=None, month=None, description=None, category=None,
			   source=None, key_words=None, link=None, attachment=None, published=1):
	_require_approver()
	if not (title or "").strip():
		frappe.throw("Report title is required.")
	if category and category not in ("Report", "Workshop Report"):
		frappe.throw("Invalid category.")
	doc = frappe.get_doc({
		"doctype": "Anticipatory Report",
		"title": title, "year": year or None, "month": month, "description": description,
		"category": category or "Report", "source": source, "key_words": key_words,
		"link": link, "attachment": attachment, "published": _as_bool(published),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_report(name, title=None, year=None, month=None, description=None, category=None,
				  source=None, key_words=None, link=None, attachment=None, published=None):
	_require_approver()
	if category and category not in ("Report", "Workshop Report"):
		frappe.throw("Invalid category.")
	doc = frappe.get_doc("Anticipatory Report", name)
	for field, value in (("title", title), ("year", year), ("month", month), ("description", description),
						 ("category", category), ("source", source), ("key_words", key_words),
						 ("link", link), ("attachment", attachment)):
		if value is not None:
			doc.set(field, value)
	if published is not None:
		doc.published = _as_bool(published)
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
				"milestone", "status", "published", "details"],
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
				 milestone=None, status=None, details=None, published=1):
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
		"status": status or "Planned", "details": details, "published": _as_bool(published),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	frappe.db.commit()
	return {"success": True, "name": doc.name}


@frappe.whitelist()
def update_activity(name, activity=None, start_date=None, end_date=None, pillar=None,
					activity_reference=None, milestone=None, status=None, details=None, published=None):
	_require_approver()
	if pillar and pillar not in _PILLARS:
		frappe.throw("Invalid pillar.")
	if status and status not in _ACTIVITY_STATUSES:
		frappe.throw("Invalid status.")
	doc = frappe.get_doc("Anticipatory Activity", name)
	for field, value in (("activity", activity), ("start_date", start_date), ("end_date", end_date),
						 ("pillar", pillar), ("activity_reference", activity_reference),
						 ("milestone", milestone), ("status", status), ("details", details)):
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
		"pillars": _select_options("Anticipatory Activity", "pillar"),
		"activity_statuses": _select_options("Anticipatory Activity", "status"),
		"roles": sorted(AA_ROLES),
		"caps": {
			"is_admin": _is_admin(),          # manage users, orgs, sign-ups
			"is_system_manager": _can_set_role(),  # may assign roles
		},
	}


# ===========================================================================
# FORM BUILDER (concept preview — read-only)
# ===========================================================================

# The form whose structure the builder previews. Read-only for now: the
# builder shows how the Anticipatory Action submission form is composed
# (sections, fields, properties) but does not yet edit it.
_BUILDER_FORMS = {
	"Anticipatory Action": "Anticipatory Action — Submission",
	"Anticipatory Action Details": "Anticipatory Action — Intervention Detail (row)",
}


@frappe.whitelist()
def get_form_schema(doctype="Anticipatory Action"):
	"""Return the live field layout of a submission form so the admin Form
	Builder can render it. Concept stage: read-only, no mutation."""
	_require_admin()
	if doctype not in _BUILDER_FORMS:
		frappe.throw("Unknown form.")
	meta = frappe.get_meta(doctype)
	fields = [
		{
			"fieldname": df.fieldname,
			"label": df.label,
			"fieldtype": df.fieldtype,
			"options": df.options,
			"reqd": int(df.reqd or 0),
			"read_only": int(df.read_only or 0),
			"hidden": int(df.hidden or 0),
			"in_list_view": int(df.in_list_view or 0),
			"description": df.description,
		}
		for df in meta.fields
	]
	return {
		"success": True,
		"doctype": doctype,
		"label": _BUILDER_FORMS[doctype],
		"forms": [{"doctype": k, "label": v} for k, v in _BUILDER_FORMS.items()],
		"fields": fields,
	}


# ===========================================================================
# SIGN-UP / MEMBERSHIP REQUESTS
# ===========================================================================

@frappe.whitelist(allow_guest=True)
def submit_membership_request(first_name, last_name=None, email=None, phone=None,
							  organization=None, position=None, message=None):
	"""Public self-service sign-up: creates a Pending request for an admin to
	approve or reject. No login account is created until it is approved."""
	from frappe.utils import validate_email_address

	first_name = (first_name or "").strip()
	email = (email or "").strip().lower()
	if not first_name or not email:
		return {"success": False, "error": "Your name and email are required."}
	if not validate_email_address(email):
		return {"success": False, "error": "Please enter a valid email address."}
	if frappe.db.exists("AA Membership Request", {"email": email, "status": "Pending"}):
		return {"success": True, "duplicate": True}
	if frappe.db.exists("Anticipatory Action User", {"email": email}):
		return {"success": False, "error": "An account already exists for this email — try signing in or resetting your password."}
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
		return {"success": True, "name": doc.name}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "submit_membership_request")
		return {"success": False, "error": "Could not submit your request. Please try again."}


@frappe.whitelist()
def list_requests(status=None):
	_require_admin()
	filters = {"status": status} if status else {}
	rows = frappe.get_all(
		"AA Membership Request",
		filters=filters,
		fields=["name", "full_name", "email", "phone", "organization", "position",
				"status", "creation", "reviewed_by", "reviewed_on", "user"],
		order_by="creation desc",
		limit=500,
	)
	return {"success": True, "data": rows}


@frappe.whitelist()
def get_request(name):
	_require_admin()
	return {"success": True, "data": frappe.get_doc("AA Membership Request", name).as_dict()}


@frappe.whitelist()
def approve_request(name, organization, role=None, notes=None):
	"""Approve a sign-up: provision the AA account (roster record -> System User
	+ welcome email) and mark the request Approved."""
	_require_admin()
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

	roster = frappe.get_doc({
		"doctype": "Anticipatory Action User",
		"first_name": req.first_name, "last_name": req.last_name or "",
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
	frappe.db.commit()
	return {"success": True, "user": roster.user}


@frappe.whitelist()
def reject_request(name, notes=None):
	"""Decline a sign-up. A reason is required and is emailed to the applicant."""
	_require_admin()
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
	frappe.db.commit()
	_email_request_rejected(req, reason)
	return {"success": True}


def _email_request_rejected(req, reason):
	"""Notify an applicant that their access request was not approved."""
	if not (req.email or "").strip():
		return
	try:
		name = (req.first_name or "there").strip()
		html = f"""
		<div style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;">
		  <div style="background:#1F2937;border-bottom:3px solid #CC0000;padding:22px 32px;text-align:center;">
		    <img src="{frappe.utils.get_url('/NDOC.png')}" alt="NDOC" height="40" style="height:40px;margin-bottom:8px;" />
		    <p style="margin:0;font-size:18px;font-weight:700;color:#fff;">Anticipatory Action</p>
		    <p style="margin:4px 0 0;font-size:11px;color:#9CA3AF;">Data Collection &amp; Monitoring Platform</p>
		  </div>
		  <div style="padding:30px 32px;color:#374151;font-size:14px;line-height:1.7;">
		    <p style="margin:0 0 14px;font-weight:700;color:#1A1A1A;">Dear {frappe.utils.escape_html(name)},</p>
		    <p style="margin:0 0 18px;">Thank you for your interest in the Kenya Anticipatory Action platform.
		    After review, the TWG Secretariat is unable to approve your access request at this time.</p>
		    <div style="background:#FEF2F2;border-left:3px solid #CC0000;padding:12px 16px;margin:0 0 18px;color:#991B1B;">
		      <strong>Reason:</strong> {frappe.utils.escape_html(reason)}
		    </div>
		    <p style="margin:0;">If you believe this was in error or can provide more information,
		    please reply to this email or contact <a href="mailto:info@ndoc.go.ke" style="color:#CC0000;">info@ndoc.go.ke</a>.</p>
		  </div>
		  <div style="border-top:1px solid #E5E7EB;padding:14px 32px;text-align:center;font-size:11px;color:#9CA3AF;">
		    National Disaster Operations Centre &middot; Anticipatory Action Platform
		  </div>
		</div>"""
		frappe.sendmail(
			recipients=[req.email],
			subject="Your Anticipatory Action access request",
			message=html,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "reject_request email")
