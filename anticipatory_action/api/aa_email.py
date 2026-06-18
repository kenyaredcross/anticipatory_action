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

# The brand name shown in the From of every AA email. The mailbox in front of it
# is whichever Email Account is configured (see aa_sender) — so AA mail can be sent
# through a well-delivering account (e.g. the redcross/Office 365 one) while still
# reading as "Anticipatory Action <that-address>".
AA_DISPLAY_NAME = "Anticipatory Action"


def _branded(email_id):
	return "{0} <{1}>".format(AA_DISPLAY_NAME, email_id) if email_id else None


def aa_sender():
	"""The From identity for branded AA mail. Precedence:
	1. the Email Account chosen on the Anticipatory Action Settings page (a Link —
	   set it in the UI), rendered as "Anticipatory Action <its email>";
	2. the ``aa_email_sender`` site_config value (a full "Name <email>" string);
	3. the site's default outgoing account, still AA-branded — so mail keeps
	   delivering even with nothing configured.
	Returns None only if nothing is set and there is no default outgoing account
	(then Frappe falls back to its own default)."""
	# 1. UI-chosen Email Account (the Link field stores the account's name).
	try:
		acct = frappe.db.get_single_value("Anticipatory Action Settings", "aa_email_sender")
		if acct:
			return _branded(frappe.db.get_value("Email Account", acct, "email_id"))
	except Exception:
		pass
	# 2. site_config override (full "Name <email>" string).
	conf = frappe.conf.get("aa_email_sender")
	if conf:
		return conf
	# 3. Fall back to the site default outgoing account, still AA-branded.
	try:
		return _branded(frappe.db.get_value(
			"Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, "email_id"))
	except Exception:
		return None


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


def send_submission_approved(doc, method=None):
	"""on_submit handler for Anticipatory Action: when a submission is approved,
	email the reporter a branded confirmation with the SAME form-style PDF the
	portal download produces (build_submission_pdf), sent through the AA sender.

	Replaces the old "AA Submission Approved" Notification (which attached a
	different print format). Fully wrapped so a mail/PDF hiccup can never roll back
	the approval transaction."""
	try:
		if doc.get("status") != "Approved" or doc.get("is_test"):
			return
		to = (doc.get("reporter_email") or "").strip()
		if not to:
			return
		name = escape_html(doc.get("reporting_person") or "there")
		body = (
			"<p>Dear " + name + ",</p>"
			"<p>Good news — your Anticipatory Action submission has been reviewed and "
			"<strong>approved</strong> by the TWG Secretariat. A copy is attached as a PDF "
			"for your records.</p>"
		)
		rows = [
			("Reference", escape_html(doc.get("name") or "-")),
			("Organisation", escape_html(doc.get("implementing_organization") or "-")),
			("Hazard", escape_html(doc.get("anticipated_hazard") or "-")),
			("Activation date", escape_html(str(doc.get("activation_start_date") or "-"))),
		]
		html = aa_email_html(
			"Your submission has been approved", body, rows=rows,
			cta_label="Open your portal", cta_url=portal_url("/aa-portal"),
			sign_off='Questions? Contact <a href="mailto:' + AA_INBOX + '" style="color:#CC0000">' + AA_INBOX + '</a>.',
		)
		attachments = None
		try:
			from anticipatory_action.anticipatory_action.doctype.anticipatory_action.pdf import build_submission_pdf
			pdf = build_submission_pdf(doc)
			if pdf:
				attachments = [{"fname": (doc.get("name") or "submission") + ".pdf", "fcontent": pdf}]
		except Exception:
			frappe.log_error(frappe.get_traceback(), "approved email pdf")
		aa_sendmail(
			[to],
			"Your Anticipatory Action submission has been approved - " + (doc.get("name") or ""),
			html,
			attachments=attachments,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "send_submission_approved")
