# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from anticipatory_action.api.scheduling import auto_set_status


class AnticipatoryActivity(Document):
	def validate(self):
		auto_set_status(self)
