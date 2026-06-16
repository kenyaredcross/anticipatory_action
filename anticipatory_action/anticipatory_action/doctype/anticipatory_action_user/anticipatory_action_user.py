# Copyright (c) 2025, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# The only roles an Anticipatory Action account may ever hold. Keeping this
# narrow is what stops an AA Admin from minting System Managers or touching
# users that belong to the other projects on this shared site.
AA_ROLES = (
	"Anticipatory Action User",
	"Anticipatory Action Approver",
	"Anticipatory Action Admin",
)


class AnticipatoryActionUser(Document):
	def validate(self):
		self.full_name = f"{(self.first_name or '').strip()} {(self.last_name or '').strip()}".strip()
		if self.role not in AA_ROLES:
			frappe.throw("Invalid role for an Anticipatory Action user.")
		if self.enabled is None:
			self.enabled = 1

	def after_insert(self):
		# Create the backing login account exactly once, on first save.
		self._sync_user(create=True)

	def on_update(self):
		# Keep the linked account in step on edits — but never create a second one.
		if self.user:
			self._sync_user(create=False)

	def _sync_user(self, create):
		"""Idempotently mirror this roster record onto its Frappe User.

		On create we provision a System User and let Frappe send the standard
		welcome / set-password email. On update we only sync the mutable bits.
		Role membership is reconciled so a role switch (User <-> Admin) doesn't
		leave the old role behind, while any non-AA roles are left untouched.
		"""
		if frappe.db.exists("User", self.email):
			user = frappe.get_doc("User", self.email)
		elif create:
			user = frappe.new_doc("User")
			user.email = self.email
			user.send_welcome_email = 1
		else:
			return

		user.first_name = self.first_name
		user.last_name = self.last_name
		user.user_type = "System User"
		user.enabled = 1 if self.enabled else 0

		# Reconcile AA role membership: keep the selected role + every non-AA
		# role, drop the *other* AA role if this is a switch.
		kept = [r for r in user.get("roles", []) if r.role not in AA_ROLES or r.role == self.role]
		user.set("roles", kept)
		if self.role not in {r.role for r in kept}:
			user.append("roles", {"role": self.role})

		# Confine the desk to just the Anticipatory Action workspace(s).
		_confine_modules(user, self.role)

		user.flags.ignore_permissions = True
		user.save()

		if not self.user:
			self.db_set("user", user.name)


# The module these accounts are allowed to see on the desk; everything else is
# blocked so they land on (and only see) their Anticipatory Action workspace.
AA_MODULE = "Anticipatory Action"


def _workspace_for(role):
	"""Members and admins land on different, role-scoped workspaces — so a member
	never sees the admin-only links (Organizations, Contact, Admin Console).
	Approvers are admin-adjacent, so they share the admin workspace (the web
	console at /aa-admin is where their real, scoped tools live)."""
	admin_like = {"Anticipatory Action Admin", "Anticipatory Action Approver"}
	return "Anticipatory Action Admin" if role in admin_like else "Anticipatory Action"


def _confine_modules(user, role=None):
	"""Block every module except Anticipatory Action on an AA account, and land
	them on their AA workspace, so the desk shows only AA work. Idempotent."""
	all_modules = frappe.get_all("Module Def", pluck="name")
	desired = {m for m in all_modules if m != AA_MODULE}
	current = {b.module for b in user.get("block_modules", [])}
	if current != desired:
		user.set("block_modules", [{"module": m} for m in sorted(desired)])
	ws = _workspace_for(role)
	if frappe.db.exists("Workspace", ws):
		user.default_workspace = ws
