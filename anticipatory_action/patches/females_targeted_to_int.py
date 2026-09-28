"""Prepare `number_of_females_targeted` for its Data -> Int change (M15).

Runs before the model sync. Frappe creates Int columns as `int(11) NOT NULL
DEFAULT 0`, and MariaDB in strict mode refuses that ALTER while any row holds
NULL, an empty string, non-numeric text or a number too large for int(11)
("Data truncated for column ... at row 1"). So every value is normalised to a
whole-number string first:

* thousands separators / spaces are dropped ("1,200" -> "1200");
* NULL, blank and non-numeric text become "0" - the value the new NOT NULL
  column would hold for "not given" anyway (it was never a usable count, and
  the dashboards already ignored it);
* values beyond int(11) become "0" - no real count of people is that large.

The ALTER in the same sync also rewrites `amount_for_anticipatory_action_kes`
as NOT NULL, so any legacy NULL amounts are set to 0 for the same reason.

Idempotent: a no-op once the column is already an integer.
"""

import frappe

TABLE = "tabAnticipatory Action Details"
INT_MAX = 2147483647


def execute():
	if not frappe.db.table_exists("Anticipatory Action Details"):
		return
	col = frappe.db.sql(
		"""select data_type from information_schema.columns
		where table_schema = database() and table_name = %s and column_name = 'number_of_females_targeted'""",
		TABLE,
	)
	if not col or col[0][0].lower() in ("int", "bigint"):
		return  # already numeric (fresh install or re-run)
	clean(TABLE)


def clean(table):
	"""Normalise the columns in ``table`` (split out so it can be exercised on a copy)."""
	frappe.db.sql(
		f"""update `{table}`
		set number_of_females_targeted = replace(replace(trim(number_of_females_targeted), ',', ''), ' ', '')
		where number_of_females_targeted is not null"""
	)
	frappe.db.sql(
		f"""update `{table}` set number_of_females_targeted = '0'
		where number_of_females_targeted is null
			or number_of_females_targeted not regexp '^[0-9]+$'
			or length(number_of_females_targeted) > 10
			or cast(number_of_females_targeted as unsigned) > {INT_MAX}"""
	)
	frappe.db.sql(
		f"""update `{table}` set amount_for_anticipatory_action_kes = 0
		where amount_for_anticipatory_action_kes is null"""
	)
