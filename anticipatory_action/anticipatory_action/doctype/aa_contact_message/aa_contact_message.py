# Copyright (c) 2026, KRCS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AAContactMessage(Document):
	def before_insert(self):
		if not self.submitted_on:
			self.submitted_on = now_datetime()
