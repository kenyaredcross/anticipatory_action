import frappe

from anticipatory_action.api.portal import public_url


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	reports = frappe.get_all(
		"Anticipatory Report",
		# Public and not taken down by a reviewer. (remove_report / Private already
		# clear `published`; filtering them too keeps this page safe if they drift.)
		filters={"published": 1, "removed": ["!=", 1], "visibility": ["!=", "Private"]},
		fields=["year", "month", "title", "description", "category", "source", "key_words", "link", "attachment"],
		order_by="year desc, month asc"
	)
	for r in reports:
		r.url = public_url(r.link) or public_url(r.attachment)
	context.reports = reports

	# Build unique category and year lists for filter UI
	context.categories = sorted(set(
		r.category for r in context.reports if r.category
	))
	context.years = sorted(set(
		str(r.year) for r in context.reports if r.year
	), reverse=True)
