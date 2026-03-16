# Copyright (c) 2025, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from anticipatory_action.anticipatory_action.doctype.anticipatory_action.pdf import build_submission_pdf


class AnticipatoryAction(Document):

	def on_submit(self):
		if self.email_me_a_copy and self.reporter_email:
			self._send_copy_to_user()

	def _send_copy_to_user(self):
		try:
			pdf = build_submission_pdf(self)

			message = frappe.render_template(
				"anticipatory_action/notification/user_email_copy/user_email_copy.html",
				{"doc": self, "frappe": frappe},
			)
			frappe.sendmail(
				recipients=[self.reporter_email],
				subject=f"Anticipatory Action Submission \u2013 Reference {self.name}",
				message=message,
				attachments=[{
					"fname": f"Anticipatory_Action_{self.name}.pdf",
					"fcontent": pdf,
				}],
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "AnticipatoryAction.send_copy_to_user")
