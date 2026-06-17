import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	# Public profile only: deliberately NOT exposing the contact person, their email
	# or phone, or the organisation's phone/email. Only institutional, non-personal
	# details (website + location) are shown publicly.
	orgs = frappe.get_all(
		"Anticipatory Action Organization",
		fields=["name", "name_of_organization", "type_of_organization", "about", "narrative",
				"logo", "pillars_involved", "aa_support", "organization_website", "address",
				"show_on_website"],
		order_by="type_of_organization asc, name_of_organization asc"
	)
	# Show orgs unless explicitly hidden (show_on_website == 0). The newly-added
	# field is NULL on existing rows, which we treat as visible.
	context.organizations = [o for o in orgs if o.get("show_on_website") != 0]
