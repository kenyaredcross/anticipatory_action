"""Block every non-Anticipatory-Action module on existing AA accounts so the
desk shows only the Anticipatory Action workspace(s), and land each account on
its role's workspace. New accounts are confined by the controller; this brings
already-provisioned ones in line."""

import frappe

AA_MODULE = "Anticipatory Action"


def _workspace_for(role):
	# DATA-001: members land on the "Anticipatory Actions" (plural) workspace. On a
	# fresh migrate the plural may not be imported yet when this patch runs, so fall
	# back to the legacy singular — rename_member_workspace (later in the same migrate)
	# deletes the singular and migrates any user still on it to the plural, so the end
	# state is correct in every ordering, and we no longer hard-code a name that a
	# later patch deletes.
	if role == "Anticipatory Action Admin":
		return "Anticipatory Action Admin"
	for ws in ("Anticipatory Actions", "Anticipatory Action"):
		if frappe.db.exists("Workspace", ws):
			return ws
	return "Anticipatory Actions"


def execute():
	mods = [m for m in frappe.get_all("Module Def", pluck="name") if m != AA_MODULE]
	for r in frappe.get_all("Anticipatory Action User", fields=["user", "email", "role"]):
		u = r.user or r.email
		if not u or not frappe.db.exists("User", u):
			continue
		user = frappe.get_doc("User", u)
		user.set("block_modules", [{"module": m} for m in mods])
		ws = _workspace_for(r.role)
		if frappe.db.exists("Workspace", ws):
			user.default_workspace = ws
		user.flags.ignore_permissions = True
		user.save()
	frappe.db.commit()
