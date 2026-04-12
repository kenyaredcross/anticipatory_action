import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	context.organizations = frappe.get_all(
		"Anticipatory Action Organization",
		fields=["name", "name_of_organization", "type_of_organization",
				"primary_contact_person_name", "primary_email_contact",
				"primary_phone_contact", "organization_email",
				"organization_website"],
		order_by="type_of_organization asc, name_of_organization asc"
	)
