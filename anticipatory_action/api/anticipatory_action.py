import frappe
from frappe import _
from frappe.utils import strip_html

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
                "patner_details_section", "implementing_organization", "entity_or_organization_type",
                "other_organization_entity","funding_source","reporting_person","reporter_email",
                "reporter_phone_number","anticipatory_actions_section","anticipated_hazard","other_anticipated_hazards",
                "implementing_partners", "other_implementing_partners", "activation_start_date",
                "activation_end_date", "triggers_and_thresholds","lessons_learnt", "challenges",
                "recommendations", "supporting_materials","email_me_a_copy"

            ], 
            limit = limit,
            order_by = "modified desc"
        )

        

        for aa in anticipatory_actions:
            parent = aa ["name"]
            aa["anticipatory_action_details"] = frappe.db.get_all(
                "Anticipatory Action Details",
                filters = {"parent": parent}, 
                fields = [
                    "location_section", "subcounty_level", "county", "subcounty", "section_break_zyob", "sector", "amount_for_anticipatory_action_kes", "section_break_vzfw", "describe_the_anticipatory_action_intervention", "targeting_section", "number_of_people_targeted", "number_of_hh_targeted", "column_break_kwdb", "number_of_males_targeted", "number_of_females_targeted",

                ]
            )

        anticipatory_actions = sanitize_output(anticipatory_actions)

        return {"success": True, "data": anticipatory_actions}


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "API get_anticipatory_action")
        return {"success":False, "error": str(e)}
