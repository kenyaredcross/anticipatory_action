import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	orgs = frappe.get_all(
		"Anticipatory Action Organization",
		fields=["name", "name_of_organization", "type_of_organization", "about", "logo",
				"pillars_involved", "primary_contact_person_name", "primary_email_contact",
				"primary_phone_contact", "organization_email", "organization_phone",
				"organization_website", "address", "show_on_website"],
		order_by="type_of_organization asc, name_of_organization asc"
	)
	# Show orgs unless explicitly hidden (show_on_website == 0). The newly-added
	# field is NULL on existing rows, which we treat as visible.
	context.organizations = [o for o in orgs if o.get("show_on_website") != 0]
