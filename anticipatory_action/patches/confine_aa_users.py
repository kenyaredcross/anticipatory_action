"""Block every non-Anticipatory-Action module on existing AA accounts so the
desk shows only the Anticipatory Action workspace(s), and land each account on
its role's workspace. New accounts are confined by the controller; this brings
already-provisioned ones in line."""

import frappe

AA_MODULE = "Anticipatory Action"


def _workspace_for(role):
	return "Anticipatory Action Admin" if role == "Anticipatory Action Admin" else "Anticipatory Action"


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
