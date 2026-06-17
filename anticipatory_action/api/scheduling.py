"""Date-driven status for activities and events.

Status is derived from the start/end dates:
- before the start date        -> Planned
- between start and end (incl.) -> Ongoing
- after the end date           -> Completed

It is set automatically when a record is saved, and a daily scheduler refreshes
every record so a status flips on its own once the end date passes. Manual
statuses (On Hold / Cancelled) are always left untouched.
"""

import frappe
from frappe.utils import getdate, nowdate

MANUAL_STATUSES = ("On Hold", "Cancelled")

# (doctype, start fieldname, end fieldname) for everything that auto-flips.
_DATED_DOCTYPES = (
	("Anticipatory Activity", "start_date", "end_date"),
	("AA Event", "start_date", "end_date"),
)


def derive_status(start_date, end_date):
	"""Return Planned / Ongoing / Completed from the dates, or None if no start."""
	if not start_date:
		return None
	today = getdate(nowdate())
	start = getdate(start_date)
	end = getdate(end_date) if end_date else None
	if today < start:
		return "Planned"
	if end and today > end:
		return "Completed"
	return "Ongoing"


def auto_set_status(doc):
	"""Controller hook: set the document's status from its dates on save,
	unless an operator has parked it On Hold or Cancelled it."""
	if doc.get("status") in MANUAL_STATUSES:
		return
	new = derive_status(doc.get("start_date"), doc.get("end_date"))
	if new:
		doc.status = new


def refresh_statuses():
	"""Daily scheduler: flip statuses as dates pass, across activities + events."""
	for doctype, start_f, end_f in _DATED_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		rows = frappe.get_all(
			doctype,
			filters={"status": ["not in", MANUAL_STATUSES]},
			fields=["name", start_f, end_f, "status"],
			limit=5000,
		)
		for r in rows:
			new = derive_status(r.get(start_f), r.get(end_f))
			if new and new != r.get("status"):
				frappe.db.set_value(doctype, r["name"], "status", new, update_modified=False)
	frappe.db.commit()
