# Copyright (c) 2025, Kelvin Njenga and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_years, cint, flt, formatdate, getdate, nowdate

_EARLIEST_START = getdate("2000-01-01")
_COUNT_FIELDS = (
	"number_of_people_targeted", "number_of_hh_targeted", "number_of_males_targeted",
	"number_of_females_targeted", "number_of_livestock_targeted", "number_of_wildlife_targeted",
)

# Fields only the review workflow may set. Members change a submission through the
# portal API, which runs under ignore_permissions after its own ownership checks;
# a direct desk / REST save by a non-reviewer must never move these, or a member
# could approve their own submission or pull it out of the queue.
_REVIEW_FIELDS = (
	"status", "reason_for_rejection", "info_request", "awaiting_account",
	"is_test", "test_batch", "linked_request", "is_update",
)
_NEW_DOC_DEFAULTS = {"status": "Pending"}


def _norm(v):
	return None if v in (None, "", 0) else v


class AnticipatoryAction(Document):
	# WKF-002: the approval email to the reporter (branded, with the same PDF, and
	# correctly skipping test submissions) is sent by the on_submit hook
	# `anticipatory_action.api.aa_email.send_submission_approved`. The old controller
	# on_submit here sent a SECOND, unbranded copy via a plain frappe.sendmail and did
	# not check is_test — so approving a real submission double-emailed the reporter and
	# approving a test submission emailed the (possibly forged) reporter_email. Removed
	# so approval sends exactly one branded email on real submissions and none on tests.

	def validate(self):
		self._guard_review_fields()
		self._validate_dates()
		self._validate_figures()

	def _validate_dates(self):
		if not self.activation_start_date:
			return
		start = getdate(self.activation_start_date)
		if start < _EARLIEST_START:
			frappe.throw(f"The activation start date looks wrong ({formatdate(start)}). Please check the year.")
		if start > add_years(getdate(nowdate()), 2):
			frappe.throw("The activation start date is more than two years away. Please check the year.")
		if self.activation_end_date and getdate(self.activation_end_date) < start:
			frappe.throw("The proposed end date can't be before the activation start date.")

	def _validate_figures(self):
		"""Counts and money must be whole, non-negative numbers, and the breakdowns
		can't exceed the people targeted (they feed the public dashboards)."""
		for row in self.get("anticipatory_action_details") or []:
			where = f"Entry {row.idx}" + (f" ({row.county})" if row.county else "")
			for f in _COUNT_FIELDS + ("amount_for_anticipatory_action_kes",):
				if flt(row.get(f)) < 0:
					frappe.throw(f"{where}: {row.meta.get_label(f)} can't be negative.")
			people = cint(row.number_of_people_targeted)
			males, females = cint(row.number_of_males_targeted), cint(row.number_of_females_targeted)
			if people and males + females > people:
				frappe.throw(
					f"{where}: males ({males:,}) and females ({females:,}) add up to more than the "
					f"people targeted ({people:,})."
				)
			if people and cint(row.number_of_hh_targeted) > people:
				frappe.throw(f"{where}: households targeted can't be more than people targeted.")

	def _guard_review_fields(self):
		if self.flags.ignore_permissions:
			return  # trusted server-side path (portal / public endpoints) — already guarded
		from anticipatory_action.api.permissions import _can_review

		if _can_review():
			return
		before = self.get_doc_before_save()
		for f in _REVIEW_FIELDS:
			# Existing doc: the field must be unchanged. New doc: blank or its default.
			allowed = {_norm(before.get(f))} if before else {None, _norm(_NEW_DOC_DEFAULTS.get(f))}
			if _norm(self.get(f)) not in allowed:
				frappe.throw(
					f"You are not allowed to change {self.meta.get_label(f)} on a submission.",
					frappe.PermissionError,
				)
