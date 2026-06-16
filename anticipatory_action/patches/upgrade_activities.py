"""Upgrade Anticipatory Activity records to the richer schema.

Adds start/end dates, a Select status and a public/private flag. Existing rows:
* copy the legacy single `date` into `start_date`,
* default to published (public) so nothing silently disappears,
* normalise the old free-text status into the new Select values.
"""

import frappe

# old free-text status -> new Select value
_STATUS_MAP = {
	"planned": "Planned", "not started": "Planned", "not-started": "Planned", "to do": "Planned",
	"ongoing": "Ongoing", "in progress": "Ongoing", "in-progress": "Ongoing", "active": "Ongoing",
	"completed": "Completed", "complete": "Completed", "done": "Completed",
	"on hold": "On Hold", "on-hold": "On Hold", "delayed": "On Hold", "paused": "On Hold",
	"cancelled": "Cancelled", "canceled": "Cancelled", "dropped": "Cancelled",
}

_VALID = {"Planned", "Ongoing", "Completed", "On Hold", "Cancelled"}


def execute():
	frappe.reload_doctype("Anticipatory Activity", force=True)

	for row in frappe.get_all(
		"Anticipatory Activity",
		fields=["name", "date", "start_date", "status", "published"],
	):
		updates = {}
		if not row.start_date and row.date:
			updates["start_date"] = row.date
		if row.published is None:
			updates["published"] = 1
		raw = (row.status or "").strip()
		if raw not in _VALID:
			updates["status"] = _STATUS_MAP.get(raw.lower(), "Planned")
		if updates:
			frappe.db.set_value("Anticipatory Activity", row.name, updates, update_modified=False)

	frappe.db.commit()
