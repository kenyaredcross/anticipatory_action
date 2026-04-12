import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	context.reports = frappe.get_all(
		"Anticipatory Reports Table",
		fields=["year", "month", "title", "description", "category", "source", "key_words", "link"],
		order_by="year desc, month asc"
	)

	# Build unique category and year lists for filter UI
	context.categories = sorted(set(
		r.category for r in context.reports if r.category
	))
	context.years = sorted(set(
		str(r.year) for r in context.reports if r.year
	), reverse=True)
