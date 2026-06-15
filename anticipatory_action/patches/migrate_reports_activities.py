"""Promote reports & activities from child-table rows into standalone DocTypes.

Copies every `Anticipatory Reports Table` row into an `Anticipatory Report`
and every `AA TWG Activities Table` row into an `Anticipatory Activity`.

Idempotent: only runs while the target doctype is still empty, so re-running
(e.g. during development) won't create duplicates. The old wrapper/child
doctypes are left in place but are no longer written to.
"""

import frappe


def execute():
	if frappe.db.count("Anticipatory Report") == 0 and frappe.db.exists("DocType", "Anticipatory Reports Table"):
		for r in frappe.get_all(
			"Anticipatory Reports Table",
			fields=["year", "month", "title", "description", "category", "source", "key_words", "link"],
		):
			doc = frappe.get_doc({
				"doctype": "Anticipatory Report",
				"title": (r.title or "Untitled report"),
				"category": r.category or "Report",
				"year": r.year,
				"month": r.month,
				"description": r.description,
				"source": r.source,
				"key_words": r.key_words,
				"link": r.link,
				"published": 1,
			})
			doc.flags.ignore_permissions = True
			doc.insert()

	if frappe.db.count("Anticipatory Activity") == 0 and frappe.db.exists("DocType", "AA TWG Activities Table"):
		for a in frappe.get_all(
			"AA TWG Activities Table",
			fields=["date", "pillar", "activity", "activity_reference", "milestone", "status"],
		):
			if not (a.activity or "").strip():
				continue
			doc = frappe.get_doc({
				"doctype": "Anticipatory Activity",
				"activity": a.activity,
				"date": a.date,
				"pillar": a.pillar,
				"activity_reference": a.activity_reference,
				"milestone": a.milestone,
				"status": a.status,
			})
			doc.flags.ignore_permissions = True
			doc.insert()

	frappe.db.commit()
