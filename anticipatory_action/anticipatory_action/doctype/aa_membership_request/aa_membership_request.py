# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AAMembershipRequest(Document):
	def validate(self):
		self.full_name = f"{(self.first_name or '').strip()} {(self.last_name or '').strip()}".strip()
