import frappe
from frappe.utils import getdate, nowdate

# Roles that get the full operational picture (approvals, users, messages).
ADMIN_ROLES = {"Anticipatory Action Admin", "System Manager"}


def _is_admin():
	return bool(ADMIN_ROLES.intersection(frappe.get_roles()))


@frappe.whitelist()
def get_summary():
	"""Live, role-aware counters for the AA Operations Console overview.

	These are lightweight summary counts — they intentionally ignore row-level
	permissions for speed. Actual data access stays gated by the permissioned
	list/form views that each section opens.
	"""
	is_admin = _is_admin()

	totals = frappe.db.sql(
		"""
		SELECT
			COALESCE(SUM(d.number_of_people_targeted), 0)         AS people,
			COALESCE(SUM(d.number_of_hh_targeted), 0)             AS households,
			COALESCE(SUM(d.amount_for_anticipatory_action_kes),0) AS funds,
			COUNT(DISTINCT NULLIF(d.county, ''))                  AS counties
		FROM `tabAnticipatory Action Details` d
		JOIN `tabAnticipatory Action` p ON d.parent = p.name
		WHERE p.status = 'Approved'
		""",
		as_dict=True,
	)
	t = totals[0] if totals else {}

	# Held guest-checkout submissions (awaiting account approval) are not yet part
	# of the register, so they are excluded from the headline counts.
	_live = {"awaiting_account": ["!=", 1]}
	data = {
		"is_admin": is_admin,
		"activations_total": frappe.db.count("Anticipatory Action", _live),
		"activations_pending": frappe.db.count("Anticipatory Action", {"status": "Pending", **_live}),
		"activations_approved": frappe.db.count("Anticipatory Action", {"status": "Approved"}),
		"people_reached": int(t.get("people") or 0),
		"households": int(t.get("households") or 0),
		"funds_kes": float(t.get("funds") or 0),
		"counties_active": int(t.get("counties") or 0),
		"organizations": frappe.db.count("Anticipatory Action Organization"),
		"documents": frappe.db.count("Anticipatory Action Reference Documents"),
		"activities": frappe.db.count("Anticipatory Activity"),
		"reports": frappe.db.count("Anticipatory Report"),
		"hazards": _hazard_breakdown(),
		"recent": _recent_activations(),
	}

	if is_admin:
		data["messages_new"] = frappe.db.count("AA Contact Message", {"status": "New"})
		data["users"] = frappe.db.count("Anticipatory Action User")
		data["requests_new"] = frappe.db.count("AA Membership Request", {"status": "Pending"})

	return data


def _hazard_breakdown():
	"""Approved activations grouped by hazard, with people targeted."""
	rows = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(p.anticipated_hazard, ''), 'Unspecified') AS hazard,
			COUNT(DISTINCT p.name)                                    AS activations,
			COALESCE(SUM(d.number_of_people_targeted), 0)             AS people
		FROM `tabAnticipatory Action` p
		LEFT JOIN `tabAnticipatory Action Details` d ON d.parent = p.name
		WHERE p.status = 'Approved'
		GROUP BY hazard
		ORDER BY activations DESC, people DESC
		""",
		as_dict=True,
	)
	return [
		{"hazard": r.hazard, "activations": int(r.activations or 0), "people": int(r.people or 0)}
		for r in rows
	]


def _recent_activations():
	return frappe.get_all(
		"Anticipatory Action",
		fields=["name", "implementing_organization", "anticipated_hazard", "status", "modified"],
		order_by="modified desc",
		limit=6,
	)


@frappe.whitelist()
def get_situation():
	"""County-level situation picture, derived purely from approved activations.

	Each county aggregates the hazards being anticipated there, the estimated
	people targeted, the number of activations, and the spread of early-action
	delivery status (Planned / Ongoing / Complete).
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			d.county                                                   AS county,
			COALESCE(NULLIF(p.anticipated_hazard,''),'Unspecified')    AS hazard,
			COALESCE(NULLIF(d.status_of_the_early_action,''),'Planned') AS ea_status,
			COALESCE(SUM(d.number_of_people_targeted), 0)              AS people,
			COUNT(DISTINCT p.name)                                     AS activations
		FROM `tabAnticipatory Action Details` d
		JOIN `tabAnticipatory Action` p ON d.parent = p.name
		WHERE p.status = 'Approved' AND IFNULL(d.county, '') != ''
		GROUP BY d.county, hazard, ea_status
		ORDER BY d.county
		""",
		as_dict=True,
	)

	counties = {}
	for r in rows:
		c = counties.setdefault(
			r.county,
			{
				"county": r.county,
				"people": 0,
				"hazards": set(),
				"ea": {"Planned": 0, "Ongoing": 0, "Complete": 0},
			},
		)
		c["people"] += int(r.people or 0)
		c["hazards"].add(r.hazard)
		c["ea"][r.ea_status] = c["ea"].get(r.ea_status, 0) + int(r.activations or 0)

	# distinct activation count per county
	act = frappe.db.sql(
		"""
		SELECT d.county AS county, COUNT(DISTINCT p.name) AS n
		FROM `tabAnticipatory Action Details` d
		JOIN `tabAnticipatory Action` p ON d.parent = p.name
		WHERE p.status = 'Approved' AND IFNULL(d.county,'') != ''
		GROUP BY d.county
		""",
		as_dict=True,
	)
	act_map = {r.county: int(r.n or 0) for r in act}

	out = []
	for c in counties.values():
		ea = c["ea"]
		if ea.get("Ongoing"):
			level = "Ongoing"
		elif ea.get("Planned"):
			level = "Planned"
		elif ea.get("Complete"):
			level = "Complete"
		else:
			level = "Planned"
		out.append(
			{
				"county": c["county"],
				"people": c["people"],
				"activations": act_map.get(c["county"], 0),
				"hazards": sorted(c["hazards"]),
				"level": level,
				"ea": ea,
			}
		)

	out.sort(key=lambda x: (-x["people"], x["county"]))
	return out


@frappe.whitelist()
def get_activations(status=None, hazard=None, county=None):
	"""Activation register with per-record people + funds aggregates."""
	# Never surface submissions still held against a pending sign-up request.
	conditions = ["(p.awaiting_account = 0 OR p.awaiting_account IS NULL)"]
	values = {}
	if status:
		conditions.append("p.status = %(status)s")
		values["status"] = status
	if hazard:
		conditions.append("p.anticipated_hazard = %(hazard)s")
		values["hazard"] = hazard
	if county:
		conditions.append(
			"p.name IN (SELECT parent FROM `tabAnticipatory Action Details` WHERE county = %(county)s)"
		)
		values["county"] = county

	where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

	return frappe.db.sql(
		f"""
		SELECT
			p.name                                        AS name,
			p.implementing_organization                   AS organization,
			p.entity_or_organization_type                 AS entity_type,
			p.anticipated_hazard                          AS hazard,
			p.status                                      AS status,
			p.activation_start_date                       AS start_date,
			p.activation_end_date                         AS end_date,
			p.funding_source                              AS funding_source,
			p.creation                                    AS submitted_on,
			p.modified                                    AS modified,
			p.is_update                                   AS is_update,
			p.amended_from                                AS amended_from,
			COALESCE(SUM(d.number_of_people_targeted), 0) AS people,
			COALESCE(SUM(d.amount_for_anticipatory_action_kes), 0) AS funds,
			GROUP_CONCAT(DISTINCT NULLIF(d.county, '')
				ORDER BY d.county SEPARATOR ', ')         AS counties
		FROM `tabAnticipatory Action` p
		LEFT JOIN `tabAnticipatory Action Details` d ON d.parent = p.name
		{where}
		GROUP BY p.name
		ORDER BY p.modified DESC
		LIMIT 200
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
def get_events():
	"""Programme events / milestones, sourced from the TWG activities tracker.

	Split into upcoming (today onward) and past, so the console reads like an
	operations calendar.
	"""
	rows = frappe.get_all(
		"Anticipatory Activity",
		fields=["name", "start_date", "end_date", "date", "pillar", "activity",
				"activity_reference", "milestone", "status"],
		order_by="start_date desc",
		limit=300,
	)

	today = getdate(nowdate())
	upcoming, past = [], []
	for r in rows:
		# prefer the new start_date, fall back to the legacy single date
		r.date = r.start_date or r.date
		bucket = upcoming if (r.date and getdate(r.date) >= today) else past
		bucket.append(r)

	# upcoming should read soonest-first
	upcoming.sort(key=lambda r: getdate(r.date) if r.date else today)
	return {"upcoming": upcoming, "past": past}


@frappe.whitelist()
def get_reports():
	"""Unified reports + publications library.

	Merges the curated Reports register with formal Reference Documents into a
	single, newest-first list with normalised fields.
	"""
	library = []

	# The portal is members-only, so it shows both Public and Private reports;
	# only reviewer-removed ones are hidden.
	for r in frappe.get_all(
		"Anticipatory Report",
		filters={"removed": ["!=", 1]},
		fields=["name", "title", "description", "category", "source", "key_words", "link", "attachment", "year", "month", "visibility"],
		limit=500,
	):
		library.append(
			{
				"kind": "report",
				"name": r.name,
				"title": r.title or "Untitled report",
				"description": r.description,
				"category": r.category or "Report",
				"source": r.source,
				"keywords": r.key_words,
				"url": r.link or r.attachment,
				"year": r.year,
				"month": r.month,
				"visibility": r.visibility or "Public",
				"sort": r.year or 0,
			}
		)

	for d in frappe.get_all(
		"Anticipatory Action Reference Documents",
		fields=[
			"name",
			"title",
			"type",
			"publication_date",
			"publishing_authority",
			"publication_url",
			"attach_publication",
		],
		order_by="publication_date desc",
		limit=500,
	):
		year = getdate(d.publication_date).year if d.publication_date else None
		library.append(
			{
				"kind": "publication",
				"name": d.name,
				"title": d.title or "Untitled publication",
				"description": None,
				"category": d.type or "Publication",
				"source": d.publishing_authority,
				"keywords": None,
				"url": d.publication_url or d.attach_publication,
				"year": year,
				"month": None,
				"sort": year or 0,
			}
		)

	library.sort(key=lambda x: x.get("sort") or 0, reverse=True)
	return library
