# Copyright (c) 2025, Kelvin Njenga and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AnticipatoryAction(Document):
	# WKF-002: the approval email to the reporter (branded, with the same PDF, and
	# correctly skipping test submissions) is sent by the on_submit hook
	# `anticipatory_action.api.aa_email.send_submission_approved`. The old controller
	# on_submit here sent a SECOND, unbranded copy via a plain frappe.sendmail and did
	# not check is_test \u2014 so approving a real submission double-emailed the reporter and
	# approving a test submission emailed the (possibly forged) reporter_email. Removed
	# so approval sends exactly one branded email on real submissions and none on tests.
	pass
