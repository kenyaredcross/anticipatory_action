import frappe

from anticipatory_action.anticipatory_action.doctype.anticipatory_action_settings.anticipatory_action_settings import (
	testing_enabled,
)


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1

	# This test-data dashboard is only live while an admin has the test /
	# dissemination environment switched on. When it is off the URL is effectively
	# disabled and visitors are bounced to the real Results Dashboard — so the test
	# dashboard goes dark exactly when the test form does.
	if not testing_enabled():
		frappe.local.flags.redirect_location = "/aa-dashboard"
		raise frappe.Redirect
