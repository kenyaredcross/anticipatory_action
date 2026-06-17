import frappe
from frappe.utils import strip_html


@frappe.whitelist(allow_guest=True)
def submit_anticipatory_action(data):
	try:
		d = frappe.parse_json(data)

		doc = frappe.get_doc({
			"doctype": "Anticipatory Action",
			"implementing_organization": d.get("implementing_organization"),
			"entity_or_organization_type": d.get("entity_or_organization_type"),
			"other_organization_entity": d.get("other_organization_entity"),
			"funding_source": d.get("funding_source"),
			"reporting_person": d.get("reporting_person"),
			"reporter_email": d.get("reporter_email"),
			"reporter_phone_number": d.get("reporter_phone_number"),
			"anticipated_hazard": d.get("anticipated_hazard"),
			"other_anticipated_hazards": d.get("other_anticipated_hazards"),
			"implementing_partners": d.get("implementing_partners"),
			"other_implementing_partners": d.get("other_implementing_partners"),
			"activation_start_date": d.get("activation_start_date"),
			"activation_end_date": d.get("activation_end_date"),
			"triggers_and_thresholds": d.get("triggers_and_thresholds"),
			"lessons_learnt": d.get("lessons_learnt"),
			"challenges": d.get("challenges"),
			"recommendations": d.get("recommendations"),
			"supporting_materials": d.get("supporting_materials"),
			"email_me_a_copy": d.get("email_me_a_copy", 0),
			"anticipatory_action_details": [
				{
					"doctype": "Anticipatory Action Details",
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
				for row in (d.get("anticipatory_action_details") or [])
			]
		})

		# Save as a Draft (not submitted) so the reporter can edit or withdraw
		# it from their portal while it is still Pending. An AA Admin submits it
		# when they approve — see anticipatory_action.api.portal.set_submission_status.
		doc.flags.ignore_permissions = True
		doc.insert()
		frappe.db.commit()

		return {"success": True, "name": doc.name}

	except Exception:
		frappe.log_error(frappe.get_traceback(), "submit_anticipatory_action")
		return {"success": False, "error": "Submission failed. Please try again or contact support."}


@frappe.whitelist(allow_guest=True)
def get_form_meta():
	"""Return Select field options for the public submission form."""
	def get_options(doctype, fieldname):
		meta = frappe.get_meta(doctype)
		field = meta.get_field(fieldname)
		if not field or not field.options:
			return []
		return [o for o in field.options.split('\n') if o.strip()]

	county_records = frappe.db.get_all("Counties", fields=["county"], order_by="county asc")
	county_list = [c["county"] for c in county_records if c.get("county")]
	if not county_list:
		county_list = get_options("Anticipatory Action Details", "county")

	return {
		"success": True,
		"entity_or_organization_type": get_options("Anticipatory Action", "entity_or_organization_type"),
		"anticipated_hazard":          get_options("Anticipatory Action", "anticipated_hazard"),
		"implementing_partners":       get_options("Anticipatory Action", "implementing_partners"),
		"county":                      county_list,
		"sector":                      get_options("Anticipatory Action Details", "sector"),
		"status_of_the_early_action":  get_options("Anticipatory Action Details", "status_of_the_early_action"),
	}


@frappe.whitelist(allow_guest=False)
def get_anticipatory_action_data(limit=100):
	try:
		limit = int(limit)

		anticipatory_actions = frappe.db.get_all(
			"Anticipatory Action",
			# Power BI / dashboard feed: only approved (and therefore submitted)
			# activations count towards the published metrics.
			filters={"status": "Approved", "docstatus": 1},
			fields=[
				"name",
				"implementing_organization", "entity_or_organization_type",
				"other_organization_entity", "funding_source", "reporting_person", "reporter_email",
				"reporter_phone_number", "anticipated_hazard", "other_anticipated_hazards",
				"implementing_partners", "other_implementing_partners", "activation_start_date",
				"activation_end_date", "triggers_and_thresholds", "lessons_learnt", "challenges",
				"recommendations", "supporting_materials", "email_me_a_copy"
			],
			limit=limit,
			order_by="modified desc"
		)

		for aa in anticipatory_actions:
			aa["anticipatory_action_details"] = frappe.db.get_all(
				"Anticipatory Action Details",
				filters={"parent": aa["name"]},
				fields=[
					"subcounty_level", "county", "subcounty", "sector",
					"amount_for_anticipatory_action_kes",
					"describe_the_anticipatory_action_intervention",
					"number_of_people_targeted", "number_of_hh_targeted",
					"number_of_males_targeted", "number_of_females_targeted",
				]
			)

		return {"success": True, "data": _sanitize(anticipatory_actions)}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "get_anticipatory_action_data")
		return {"success": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def get_public_metrics():
	"""Public, org-wide headline numbers for the encourage-submissions page.

	Approved activations only: total approved submissions, funds committed (KES),
	people targeted, counties reached and a per-hazard breakdown. Nothing here is
	row-level sensitive, so it is safe for anonymous visitors."""
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

	hazards = frappe.db.sql(
		"""
		SELECT COALESCE(NULLIF(p.anticipated_hazard,''),'Unspecified') AS hazard,
			   COUNT(DISTINCT p.name) AS activations
		FROM `tabAnticipatory Action` p
		WHERE p.status = 'Approved'
		GROUP BY hazard
		ORDER BY activations DESC
		""",
		as_dict=True,
	)

	return {
		"success": True,
		"approved_submissions": frappe.db.count("Anticipatory Action", {"status": "Approved"}),
		"funds_committed_kes": float(t.get("funds") or 0),
		"people_targeted": int(t.get("people") or 0),
		"counties_reached": int(t.get("counties") or 0),
		"organizations": frappe.db.count("Anticipatory Action Organization"),
		"hazards": [{"hazard": h.hazard, "activations": int(h.activations or 0)} for h in hazards],
	}


def _sanitize(data):
	if isinstance(data, dict):
		return {k: _sanitize(v) for k, v in data.items()}
	elif isinstance(data, list):
		return [_sanitize(i) for i in data]
	elif isinstance(data, str):
		return strip_html(data).strip()
	return data
