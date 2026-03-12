import frappe
from frappe import _
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

		doc.flags.ignore_permissions = True
		doc.insert()
		frappe.db.commit()

		if d.get("email_me_a_copy") and d.get("reporter_email"):
			_send_submission_email(doc)

		return {"success": True, "name": doc.name}

	except Exception:
		frappe.log_error(frappe.get_traceback(), "submit_anticipatory_action")
		return {"success": False, "error": "Submission failed. Please try again or contact support."}


def _send_submission_email(doc):
	try:
		pdf_data = frappe.get_print(
			doctype="Anticipatory Action",
			name=doc.name,
			print_format="Anticipatory Action Submission",
			as_pdf=True,
		)
		frappe.sendmail(
			recipients=[doc.reporter_email],
			subject=f"Anticipatory Action Submission Received \u2013 Reference {doc.name}",
			template="Anticipatory Action Submission",
			args={"doc": doc},
			attachments=[{
				"fname": f"Anticipatory_Action_{doc.name}.pdf",
				"fcontent": pdf_data,
			}],
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "send_submission_email")

@frappe.whitelist(allow_guest=True)
def get_form_meta():
    """Return Select field options for the public submission form, sourced from doctype metadata."""
    def get_options(doctype, fieldname):
        meta = frappe.get_meta(doctype)
        field = meta.get_field(fieldname)
        if not field or not field.options:
            return []
        return [o for o in field.options.split('\n') if o.strip()]

    # Counties: prefer live records from the Counties doctype; fall back to Select field options
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


def sanitize_output(data):
    """ Remove all HTML tags from the doctypes payload"""

    if isinstance(data, dict):
        return {k : sanitize_output(v) for k, v in data.items()}


    elif isinstance(data, list):
        return [sanitize_output(i) for i in data]
    
    elif isinstance(data, str):
        return strip_html(data).strip()    

    return data



@frappe.whitelist(allow_guest = False)
def get_anticipatory_action_data(limit=100):
    try:
        limit = int(limit)

        anticipatory_actions = frappe.db.get_all(
            "Anticipatory Action",
            fields = [
                "name",
                "implementing_organization", "entity_or_organization_type",
                "other_organization_entity","funding_source","reporting_person","reporter_email",
                "reporter_phone_number","anticipated_hazard","other_anticipated_hazards",
                "implementing_partners", "other_implementing_partners", "activation_start_date",
                "activation_end_date", "triggers_and_thresholds","lessons_learnt", "challenges",
                "recommendations", "supporting_materials","email_me_a_copy"

            ], 
            limit = limit,
            order_by = "modified desc"
        )

        

        for aa in anticipatory_actions:
            parent = aa["name"]
            aa["anticipatory_action_details"] = frappe.db.get_all(
                "Anticipatory Action Details",
                filters = {"parent": parent}, 
                fields = [
                    "subcounty_level", "county", "subcounty", "sector", "amount_for_anticipatory_action_kes", "describe_the_anticipatory_action_intervention", "number_of_people_targeted", "number_of_hh_targeted", "number_of_males_targeted", "number_of_females_targeted",

                ]
            )

        anticipatory_actions = sanitize_output(anticipatory_actions)

        return {"success": True, "data": anticipatory_actions}


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "API get_anticipatory_action")
        return {"success":False, "error": str(e)}
