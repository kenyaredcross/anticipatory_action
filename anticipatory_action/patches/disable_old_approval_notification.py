import frappe


def execute():
	"""The submission-approval email is now sent in code (via the on_submit
	doc_event ``send_submission_approved``), attaching the same form-style PDF the
	portal download produces and using the configured AA sender. Disable the old
	standard "AA Submission Approved" Notification so reporters don't get two
	emails. We save the doc (not a raw db_set) so the cached notification map is
	refreshed, then clear caches to be safe."""
	if not frappe.db.exists("Notification", "AA Submission Approved"):
		return
	notif = frappe.get_doc("Notification", "AA Submission Approved")
	if notif.enabled:
		notif.enabled = 0
		notif.flags.ignore_permissions = True
		notif.save()
	frappe.clear_cache()
