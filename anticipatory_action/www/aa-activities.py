import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	context.activities = frappe.get_all(
		"Anticipatory Activity",
		fields=["date", "pillar", "activity", "activity_reference", "milestone", "status"],
		order_by="date desc"
	)

	# Build unique pillar list for filter UI
	context.pillars = sorted(set(
		a.pillar for a in context.activities if a.pillar
	))
