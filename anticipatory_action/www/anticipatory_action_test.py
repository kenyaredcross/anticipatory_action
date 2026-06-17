import frappe

from anticipatory_action.anticipatory_action.doctype.anticipatory_action_settings.anticipatory_action_settings import (
	testing_enabled,
)


def get_context(context):
	context.no_cache = 1

	# This route is only live while an admin has the test / dissemination
	# environment switched on. When it is off the URL is effectively disabled
	# and visitors are bounced to the real form.
	if not testing_enabled():
		frappe.local.flags.redirect_location = "/aa"
		raise frappe.Redirect

	# The test form needs no account step - anyone (including guests) can fill
	# it in and submit. Treat everyone as a guest so the template skips the
	# logged-in / edit-mode plumbing.
	context.is_logged_in = False
	context.reporter_name = ""
	context.reporter_email = ""
	context.reporter_phone = ""
