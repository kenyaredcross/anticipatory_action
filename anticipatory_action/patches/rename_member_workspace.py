import frappe


def execute():
	"""Remove the old member workspace named exactly "Anticipatory Action".

	It collided with the DocType of the same name on the desk route. The
	replacement ships as the "Anticipatory Actions" workspace (plural) and is
	imported from the app's workspace/ folder on this same migrate.
	"""
	old = "Anticipatory Action"
	if frappe.db.exists("Workspace", old):
		try:
			frappe.delete_doc("Workspace", old, force=True, ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "rename_member_workspace")

	# Point any AA member still defaulted to the old workspace at the new one.
	if frappe.db.has_column("User", "default_workspace"):
		frappe.db.sql(
			"""UPDATE `tabUser` SET default_workspace = %s WHERE default_workspace = %s""",
			("Anticipatory Actions", old),
		)
