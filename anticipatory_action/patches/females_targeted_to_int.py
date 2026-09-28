"""Prepare `number_of_females_targeted` for its Data -> Int change (M15).

Runs before the model sync. MariaDB refuses to ALTER a varchar column to int while
it holds non-numeric text (including blanks) in strict mode, so normalise first:
drop thousands separators / spaces, keep whole numbers, and clear anything else
(it was never a usable count, and the dashboards already ignored it).
"""

import frappe


def execute():
	table = "tabAnticipatory Action Details"
	if not frappe.db.table_exists("Anticipatory Action Details"):
		return
	col = frappe.db.sql(
		"""select data_type from information_schema.columns
		where table_schema = database() and table_name = %s and column_name = 'number_of_females_targeted'""",
		table,
	)
	if not col or col[0][0].lower() in ("int", "bigint"):
		return  # already numeric (fresh install or re-run)
	frappe.db.sql(
		f"""update `{table}`
		set number_of_females_targeted = replace(replace(trim(number_of_females_targeted), ',', ''), ' ', '')
		where number_of_females_targeted is not null"""
	)
	frappe.db.sql(
		f"""update `{table}` set number_of_females_targeted = null
		where number_of_females_targeted is not null and number_of_females_targeted not regexp '^[0-9]+$'"""
	)
