"""Branded, self-contained HTML email for Anticipatory Action.

All AA-originated mail (account welcome, sign-up acknowledgements, pillar
enquiries) goes through here so it carries the AA masthead + Kenya Red Cross
footer and links to the AA portal — never the Frappe desk.

Sending is centralised in ``aa_sendmail``, which stamps the AA sender so the
mail is visibly *from* Anticipatory Action and never changes the parent
(redhive) site's default outgoing identity. Until a dedicated AA email account
is wired up it falls back to the site default; set ``aa_email_sender`` in
site_config (e.g. "Anticipatory Action <aa@anticipatoryaction.ndoc.go.ke>") to
switch the From address on once the mailbox exists.
"""

import frappe
from frappe.utils import escape_html, get_url

AA_RED = "#CC0000"

# The central AA inbox that is copied on enquiries / sign-ups (a real mailbox; it
# stays on the ndoc.go.ke domain regardless of the NDRMA display rebrand).
AA_INBOX = "aadashboard@ndoc.go.ke"

# Default From identity for branded AA mail. The email part must match the Email
# ID of an enabled outgoing Email Account (here: the "Anticipatory TWG Team"
# account, aadashboard@ndoc.go.ke) so Frappe routes through it — keeping AA mail
# separate from the site's default (redhive) account with zero configuration.
AA_DEFAULT_SENDER = "Anticipatory Action <aadashboard@ndoc.go.ke>"


def aa_sender():
	"""The AA From identity. Precedence:
	1. the Anticipatory Action Settings field (UI / browser-console settable — handy
	   on Frappe Cloud), then
	2. the ``aa_email_sender`` site_config key, then
	3. the built-in default above — so branded AA mail works out of the box with no
	   configuration after deploy."""
	try:
		val = frappe.db.get_single_value("Anticipatory Action Settings", "aa_email_sender")
		if val and val.strip():
			return val.strip()
	except Exception:
		pass
	return frappe.conf.get("aa_email_sender") or AA_DEFAULT_SENDER


def portal_url(path="/aa-portal"):
	return get_url(path)


def aa_email_html(heading, body_html, rows=None, cta_label=None, cta_url=None, sign_off=None):
	"""Wrap content in the AA-branded shell. ``body_html`` is trusted HTML;
	``rows`` is an optional list of (label, value-html) summary pairs."""
	logo = get_url("/aadashboard.png")
	rows_html = ""
	if rows:
		cells = "".join(
			'<tr>'
			'<td style="padding:7px 12px 7px 0;color:#6B7280;font-size:13px;width:44%;vertical-align:top">' + escape_html(k) + '</td>'
			'<td style="padding:7px 0;color:#111827;font-size:13px;font-weight:600">' + (v or "-") + '</td>'
			'</tr>'
			for k, v in rows
		)
		rows_html = '<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;margin:18px 0">' + cells + '</table>'
	cta = ""
	if cta_label and cta_url:
		cta = (
			'<div style="margin:26px 0 6px"><a href="' + cta_url + '" '
			'style="display:inline-block;background:' + AA_RED + ';color:#ffffff;text-decoration:none;'
			'font-weight:700;font-size:14px;padding:12px 26px;border-radius:6px">' + escape_html(cta_label) + '</a></div>'
		)
	sign = ('<p style="margin:18px 0 0">' + sign_off + '</p>') if sign_off else ""
	return (
		'<div style="background:#F3F4F6;padding:24px 0;font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif">'
		'<table cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;margin:0 auto;background:#ffffff;border-radius:10px;overflow:hidden">'
		'<tr><td style="padding:20px 28px;border-bottom:3px solid ' + AA_RED + '">'
		'<table cellpadding="0" cellspacing="0"><tr>'
		'<td style="vertical-align:middle;padding-right:14px"><img src="' + logo + '" alt="NDRMA" style="height:46px;display:block" /></td>'
		'<td style="vertical-align:middle;font-size:16px;font-weight:700;color:#111827">Anticipatory Action</td>'
		'</tr></table></td></tr>'
		'<tr><td style="padding:26px 28px;color:#374151;font-size:14.5px;line-height:1.65">'
		'<h2 style="margin:0 0 12px;font-size:19px;color:#111827">' + escape_html(heading) + '</h2>'
		+ body_html + rows_html + cta + sign +
		'</td></tr>'
		'<tr><td style="padding:16px 28px;background:#F9FAFB;border-top:1px solid #E5E7EB;color:#9CA3AF;font-size:12px;line-height:1.6">'
		'Kenya Anticipatory Action &mdash; National Technical Working Group.<br/>'
		'Developed and maintained by Kenya Red Cross.'
		'</td></tr>'
		'</table></div>'
	)


def aa_sendmail(recipients, subject, message, **kwargs):
	"""Send branded AA mail. Stamps the AA sender when one is configured, and
	never raises (logs instead) so a mail hiccup can't break the action that
	triggered it. With no AA email account / SMTP configured yet this simply
	queues or no-ops — by design (templates are ready; sending is flipped on
	later by configuring the account)."""
	if not recipients:
		return
	args = {"recipients": recipients, "subject": subject, "message": message}
	sender = aa_sender()
	if sender:
		args["sender"] = sender
	args.update(kwargs)
	try:
		frappe.sendmail(**args)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "aa_sendmail")
