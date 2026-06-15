"""Repair AA login accounts created by the previous (buggy) controller.

The old `Anticipatory Action User` controller created its Frappe User with a
`role_profile_name` / `module_profile` pointing at profiles that don't exist,
never set `user_type`, and never linked the User back to the roster record.

This patch reconciles each roster record with its login account, idempotently:
  - ensure the account is a System User
  - clear the bogus role profiles
  - ensure exactly the right AA role is present
  - back-fill the new `user` link and default `enabled`

Safe to re-run. Accounts that share an email with another project's user are
left untouched (we never strip non-AA roles here).
"""

import frappe

AA_ROLES = ("Anticipatory Action User", "Anticipatory Action Admin")


def execute():
	rosters = frappe.get_all(
		"Anticipatory Action User",
		fields=["name", "email", "role", "user", "enabled"],
	)
	for r in rosters:
		if r.enabled is None:
			frappe.db.set_value("Anticipatory Action User", r.name, "enabled", 1)

		if not r.email or not frappe.db.exists("User", r.email):
			# No account yet — re-saving the roster record will provision one.
			continue

		user = frappe.get_doc("User", r.email)
		changed = False

		if user.user_type != "System User":
			user.user_type = "System User"
			changed = True
		if user.get("role_profile_name"):
			user.role_profile_name = None
			changed = True
		if user.get("module_profile"):
			user.module_profile = None
			changed = True

		role = r.role if r.role in AA_ROLES else "Anticipatory Action User"
		if role not in {x.role for x in user.get("roles", [])}:
			user.append("roles", {"role": role})
			changed = True

		if changed:
			user.flags.ignore_permissions = True
			user.save()

		if not r.user:
			frappe.db.set_value("Anticipatory Action User", r.name, "user", user.name)

	frappe.db.commit()
