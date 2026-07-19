import frappe


def get_context(context):
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.success = False
	context.error = None


# NOTE (SEC-008): the contact form POSTs to the single, validated, deduping,
# pillar-routing endpoint anticipatory_action.api.portal.submit_contact. A second
# whitelisted submit_contact used to live here — unvalidated, and leaking the raw
# exception string to the client — but this module's dotted path is hyphenated, so
# /api/method could never import it anyway. It has been removed; do not re-add a
# whitelisted method to a hyphen-named controller.
