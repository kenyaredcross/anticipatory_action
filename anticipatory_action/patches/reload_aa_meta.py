"""Make sure hand-edited AA metadata lands on every deploy.

`bench migrate` can skip re-importing a doctype/workspace when it thinks the
file is unchanged, so the System-Manager-only role field and the renamed
workspace shortcuts may not apply. Forcing a reload (which imports the file and
bypasses the save-time route-conflict check) guarantees they land."""

import frappe


def execute():
	for dt in ("anticipatory_action_user", "aa_membership_request"):
		try:
			frappe.reload_doc("Anticipatory Action", "doctype", dt, force=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "reload_aa_meta:doctype:" + dt)

	for ws in ("anticipatory_action", "anticipatory_action_admin"):
		try:
			frappe.reload_doc("Anticipatory Action", "workspace", ws, force=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "reload_aa_meta:workspace:" + ws)

	frappe.db.commit()
