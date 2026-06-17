# Copyright (c) 2026, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AnticipatoryActionSettings(Document):
	pass


def testing_enabled():
	"""Is the test / dissemination environment currently switched on?"""
	try:
		return bool(frappe.db.get_single_value("Anticipatory Action Settings", "testing_enabled"))
	except Exception:
		return False
