import frappe
from frappe.utils import format_date, now
from frappe.utils.pdf import get_pdf


def build_submission_pdf(doc):
	"""Generate a PDF for the anticipatory action submission and return bytes."""
	html = _build_html(doc)
	return get_pdf(html, options={
		"disable-external-links": "",
		"disable-javascript": "",
		"encoding": "UTF-8",
	})


def _val(v, fallback="—"):
	return v if v else fallback


def _fmt_date(d):
	return format_date(d, "d MMMM yyyy") if d else "—"


def _fmt_num(n):
	try:
		return f"{int(n):,}" if n else "—"
	except Exception:
		return str(n)


def _fmt_kes(n):
	try:
		return f"KES {int(n):,}" if n else "—"
	except Exception:
		return str(n)


def _field(label, value):
	return f"""
	<div style="margin-bottom:10px;">
		<div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#6B7280;margin-bottom:3px;">{label}</div>
		<div style="font-size:12px;color:#111827;">{value}</div>
	</div>"""


def _section(title, body):
	return f"""
	<div style="margin-bottom:24px;">
		<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:#374151;
			padding-bottom:6px;border-bottom:1.5px solid #D1D5DB;margin-bottom:14px;">{title}</div>
		{body}
	</div>"""


def _grid(*fields):
	rows = ""
	items = list(fields)
	for i in range(0, len(items), 2):
		pair = items[i:i+2]
		if len(pair) == 1:
			pair.append("")
		rows += f"<tr>{''.join(f'<td style=\"width:50%;vertical-align:top;padding-right:20px;\">{c}</td>' for c in pair)}</tr>"
	return f'<table width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def _build_html(doc):
	# ── Section 1: Organisation ──────────────────────────────────────────────
	org_type = _val(doc.entity_or_organization_type)
	if doc.other_organization_entity:
		org_type += f" — {doc.other_organization_entity}"

	sec1 = _grid(
		_field("Organization Name", _val(doc.implementing_organization)),
		_field("Organization Type", org_type),
		_field("Funding Source", _val(doc.funding_source)),
		_field("Reporting Person", _val(doc.reporting_person)),
		_field("Email", _val(doc.reporter_email)),
		_field("Phone", _val(doc.reporter_phone_number)),
	)

	# ── Section 2: Hazard ────────────────────────────────────────────────────
	hazard = _val(doc.anticipated_hazard)
	if doc.other_anticipated_hazards:
		hazard += f" — {doc.other_anticipated_hazards}"

	partners = _val(doc.implementing_partners)
	if doc.other_implementing_partners:
		partners += f": {doc.other_implementing_partners}"

	sec2 = _grid(
		_field("Hazard Type", hazard),
		_field("Implementing Partners", partners),
		_field("Activation Start Date", _fmt_date(doc.activation_start_date)),
		_field("Proposed End Date", _fmt_date(doc.activation_end_date)),
	)

	# ── Section 3: Action Details table ──────────────────────────────────────
	if doc.anticipatory_action_details:
		badge_colors = {
			"planned":  "background:#F3F4F6;color:#374151;",
			"ongoing":  "background:#E5E7EB;color:#111827;",
			"complete": "background:#D1FAE5;color:#065F46;",
		}
		rows_html = ""
		for i, row in enumerate(doc.anticipatory_action_details):
			bg = "#F9FAFB" if i % 2 == 0 else "#ffffff"
			loc = f"<strong>{row.county}</strong>"
			if row.subcounty:
				loc += f"<br><span style='color:#6B7280;font-size:10px;'>{row.subcounty}</span>"
			s = (row.status_of_the_early_action or "Planned").lower()
			badge_style = badge_colors.get(s, badge_colors["planned"])
			badge = f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:700;{badge_style}">{row.status_of_the_early_action or "Planned"}</span>'
			rows_html += f"""
			<tr style="background:{bg};">
				<td style="padding:7px 10px;vertical-align:top;border-bottom:1px solid #E5E7EB;font-size:11px;">{loc}</td>
				<td style="padding:7px 10px;vertical-align:top;border-bottom:1px solid #E5E7EB;font-size:11px;">{_val(row.sector)}</td>
				<td style="padding:7px 10px;vertical-align:top;border-bottom:1px solid #E5E7EB;font-size:11px;">{_val(row.describe_the_anticipatory_action_intervention)}</td>
				<td style="padding:7px 10px;vertical-align:top;border-bottom:1px solid #E5E7EB;font-size:11px;text-align:right;">{_fmt_kes(row.amount_for_anticipatory_action_kes)}</td>
				<td style="padding:7px 10px;vertical-align:top;border-bottom:1px solid #E5E7EB;font-size:11px;text-align:right;">{_fmt_num(row.number_of_people_targeted)}</td>
				<td style="padding:7px 10px;vertical-align:top;border-bottom:1px solid #E5E7EB;font-size:11px;">{badge}</td>
			</tr>"""

		details_table = f"""
		<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:11px;">
			<thead>
				<tr style="background:#374151;color:#ffffff;">
					<th style="padding:8px 10px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.04em;">County / Sub-county</th>
					<th style="padding:8px 10px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.04em;">Sector</th>
					<th style="padding:8px 10px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.04em;">Intervention</th>
					<th style="padding:8px 10px;text-align:right;font-size:10px;text-transform:uppercase;letter-spacing:0.04em;">Budget</th>
					<th style="padding:8px 10px;text-align:right;font-size:10px;text-transform:uppercase;letter-spacing:0.04em;">People</th>
					<th style="padding:8px 10px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.04em;">Status</th>
				</tr>
			</thead>
			<tbody>{rows_html}</tbody>
		</table>"""
		sec3 = _section("Anticipatory Action Details", details_table)
	else:
		sec3 = ""

	# ── Section 4: Additional Information ────────────────────────────────────
	additional = ""
	if doc.triggers_and_thresholds:
		additional += _field("Triggers &amp; Thresholds", doc.triggers_and_thresholds)
	if doc.lessons_learnt:
		additional += _field("Key Lessons Learnt", doc.lessons_learnt)
	if doc.challenges:
		additional += _field("Challenges", doc.challenges)
	if doc.recommendations:
		additional += _field("Recommendations", doc.recommendations)
	sec4 = _section("Additional Information", additional) if additional else ""

	# ── Assemble ─────────────────────────────────────────────────────────────
	return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #111827; background: #fff; }}
</style>
</head>
<body>
<div style="padding:32px 40px;">

  <!-- Header -->
  <div style="padding-bottom:14px;border-bottom:3px solid #374151;margin-bottom:22px;text-align:center;">
    <div style="font-size:18px;font-weight:700;color:#111827;">Anticipatory Action</div>
    <div style="font-size:11px;color:#6B7280;margin-top:4px;">Submission Record &middot; Data Collection &amp; Monitoring Platform</div>
  </div>

  <!-- Reference banner -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F9FAFB;border:1px solid #D1D5DB;border-radius:6px;margin-bottom:22px;">
    <tr>
      <td style="padding:12px 18px;">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#9CA3AF;">Reference Number</div>
        <div style="font-size:16px;font-weight:700;color:#111827;margin-top:4px;">{doc.name}</div>
      </td>
      <td style="padding:12px 18px;text-align:right;">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:#9CA3AF;">Submitted on</div>
        <div style="font-size:11px;color:#6B7280;margin-top:4px;">{_fmt_date(doc.creation)}</div>
      </td>
    </tr>
  </table>

  {_section("Implementing Organization", sec1)}
  {_section("Hazard &amp; Anticipatory Actions", sec2)}
  {sec3}
  {sec4}

  <!-- Footer -->
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:32px;padding-top:12px;border-top:1px solid #E5E7EB;">
    <tr>
      <td style="font-size:10px;color:#9CA3AF;">Made by <strong style="color:#6B7280;">Kenya Red Cross Digital Transformation</strong></td>
      <td style="font-size:10px;color:#9CA3AF;text-align:right;">Auto-generated on {_fmt_date(now())}</td>
    </tr>
  </table>

</div>
</body>
</html>"""
