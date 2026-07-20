"""Branded, self-contained HTML email for Anticipatory Action.

All AA-originated mail (account welcome, sign-up acknowledgements, pillar
enquiries) goes through here so it carries the AA masthead + Kenya Red Cross
footer and links to the AA portal — never the Frappe desk.

Sending is centralised in ``aa_sendmail``. By default the message goes out
through the **site's default outgoing Email Account** — the AA part is purely the
*format* (the branded HTML body), not a separate From address. An admin can
optionally route AA mail through a specific Email Account by setting the
``aa_email_sender`` switcher on the Anticipatory Action Settings page; when that
is blank (the normal case) the default sender is used and mail always sends.
"""

import frappe
from frappe.utils import escape_html, get_url

AA_RED = "#CC0000"

# Status chips shown above an email heading (foreground, background, border).
_CHIP_TONES = {
	"green": ("#065F46", "#ECFDF5", "#A7F3D0"),
	"amber": ("#92400E", "#FFFBEB", "#FDE68A"),
	"red": ("#991B1B", "#FEF2F2", "#FECACA"),
	"slate": ("#334155", "#F1F5F9", "#E2E8F0"),
	"blue": ("#1E40AF", "#EFF6FF", "#BFDBFE"),
}

# The central AA inbox that is copied on enquiries / sign-ups (a real mailbox; it
# stays on the ndoc.go.ke domain regardless of the NDRMA display rebrand).
AA_INBOX = "aadashboard@ndoc.go.ke"

# The brand name applied to the From only when an admin has explicitly chosen an
# Email Account in the AA Settings switcher (see aa_sender). With the switcher
# blank, mail goes out as the site's default outgoing account, unbranded in the
# From — the AA branding is in the message body either way.
AA_DISPLAY_NAME = "Anticipatory Action"


def _branded(email_id):
	return "{0} <{1}>".format(AA_DISPLAY_NAME, email_id) if email_id else None


def aa_sender():
	"""The From identity for AA mail.

	* If an admin has chosen an Email Account in the "Send AA emails via" switcher
	  on the Anticipatory Action Settings page, route mail through it (shown as
	  "Anticipatory Action <its address>").
	* Otherwise return ``None`` so Frappe sends through the **site's default
	  outgoing Email Account** using its own From — i.e. the default email sender.

	Either way the AA branding lives in the message *body*, never depends on a
	separate AA mailbox existing, so mail always sends."""
	try:
		acct = frappe.db.get_single_value("Anticipatory Action Settings", "aa_email_sender")
		if acct:
			email_id = frappe.db.get_value("Email Account", acct, "email_id")
			if email_id:
				return _branded(email_id)
	except Exception:
		# CODE-002: don't swallow silently — a misconfigured sender is worth a log.
		# We still fall back to the site's default account so mail keeps sending.
		frappe.log_error(frappe.get_traceback(), "aa_email sender resolution")
	return None  # use the site's default outgoing account


def portal_url(path="/aa-portal"):
	return get_url(path)


def aa_email_html(heading, body_html, rows=None, cta_label=None, cta_url=None, sign_off=None, chip=None, chip_tone="slate"):
	"""Wrap content in the AA-branded shell. ``body_html`` is trusted HTML;
	``rows`` is an optional list of (label, value-html) summary pairs."""
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
	chip_html = ""
	if chip:
		fg, bg, bd = _CHIP_TONES.get(chip_tone, _CHIP_TONES["slate"])
		chip_html = (
			'<div style="margin:0 0 12px"><span style="display:inline-block;font-size:11px;'
			'font-weight:700;letter-spacing:0.06em;text-transform:uppercase;padding:4px 10px;'
			'border-radius:100px;color:' + fg + ';background:' + bg + ';border:1px solid ' + bd + '">'
			+ escape_html(chip) + '</span></div>'
		)
	sign = ('<p style="margin:18px 0 0">' + sign_off + '</p>') if sign_off else ""
	return (
		'<div style="background:#F3F4F6;padding:24px 0;font-family:\'Helvetica Neue\',Helvetica,Arial,sans-serif">'
		'<table cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;margin:0 auto;background:#ffffff;border-radius:10px;overflow:hidden">'
		'<tr><td style="padding:20px 28px;border-bottom:3px solid ' + AA_RED + '">'
		'<table cellpadding="0" cellspacing="0"><tr>'
		'<td style="vertical-align:middle;padding-right:14px"><img embed="/assets/anticipatory_action/aadashboard.png" alt="Kenya Anticipatory Action" style="height:46px;display:block" /></td>'
		'<td style="vertical-align:middle;font-size:16px;font-weight:700;color:#111827">Anticipatory Action</td>'
		'</tr></table></td></tr>'
		'<tr><td style="padding:26px 28px;color:#374151;font-size:14.5px;line-height:1.65">'
		+ chip_html +
		'<h2 style="margin:0 0 12px;font-size:19px;color:#111827">' + escape_html(heading) + '</h2>'
		+ body_html + rows_html + cta + sign +
		'</td></tr>'
		'<tr><td style="padding:16px 28px;background:#F9FAFB;border-top:1px solid #E5E7EB;color:#9CA3AF;font-size:12px;line-height:1.6">'
		'Kenya Anticipatory Action - National Technical Working Group.'
		'</td></tr>'
		'</table></div>'
	)


def aa_sendmail(recipients, subject, message, **kwargs):
	"""Send branded AA mail through the site's default outgoing account (or the
	Email Account chosen in the AA Settings switcher). Never raises (logs instead)
	so a mail hiccup can't break the action that triggered it. As long as the site
	has a working default outgoing Email Account, AA mail sends — nothing AA-specific
	needs configuring first."""
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


def send_set_password_email(user, heading=None, intro=None):
	"""Generate a set/reset-password link (cross-version) and email it inside the
	branded AA shell, with the CTA pointing at the portal. ``user`` is a User doc.
	Returns True if queued. Used by the welcome-on-approval and the admin
	password-reset so both look identical and land members on the portal."""
	try:
		reset = getattr(user, "reset_password", None) or getattr(user, "_reset_password", None)
		link = reset(send_email=False) if callable(reset) else None
	except Exception:
		frappe.log_error(frappe.get_traceback(), "aa set-password link")
		return False
	if not link:
		return False
	first = (user.get("first_name") if hasattr(user, "get") else None) or "there"
	heading = heading or "Set your password"
	intro = intro or ("We received a request to set a new password for your Kenya Anticipatory Action "
		"account. Use the button below to choose a password and sign in.")
	body = "<p>Dear " + escape_html(first) + ",</p><p>" + intro + "</p>"
	html = aa_email_html(
		heading, body, cta_label="Set your password", cta_url=link,
		chip="Password", chip_tone="slate",
		sign_off="If you didn't request this, you can safely ignore this email - your existing "
			"password won't change. For your security, this link is unique to your account and "
			"will expire after a short time.",
	)
	aa_sendmail([user.name], "Set your Anticipatory Action password", html)
	return True


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
			"<p>We're pleased to confirm that your Anticipatory Action submission has been reviewed "
			"and <strong>approved</strong> by the National TWG Secretariat. Thank you for helping "
			"strengthen Kenya's preparedness.</p>"
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
			chip="Approved", chip_tone="green",
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
			"Your submission has been approved - " + (doc.get("name") or ""),
			html,
			attachments=attachments,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "send_submission_approved")


def send_submission_replied(doc, message=None, method=None):
	"""Email the reporter the reviewer's request for more information.

	Mirrors send_submission_approved but for the "Replied" (information-requested)
	decision: the reviewer's message is shown to the reporter with a CTA to open the
	portal, revise the submission and answer - which returns it to the review queue.
	Fully wrapped so a mail hiccup can never roll back the review action."""
	try:
		if doc.get("is_test"):
			return
		to = (doc.get("reporter_email") or "").strip()
		if not to:
			return
		msg = (message or doc.get("info_request") or "").strip()
		name = escape_html(doc.get("reporting_person") or "there")
		body = (
			"<p>Dear " + name + ",</p>"
			"<p>Thank you for your Anticipatory Action submission. Before the National TWG "
			"Secretariat can complete its review, we'd be grateful if you could help us with the "
			"following:</p>"
			'<div style="margin:16px 0;padding:13px 16px;background:#FFFBEB;border-left:3px solid #B45309;'
			'color:#5c3a10;font-size:13.5px;line-height:1.55;border-radius:0 6px 6px 0">'
			'<span style="display:block;font-size:11px;font-weight:700;letter-spacing:0.06em;'
			'text-transform:uppercase;color:#6B7280;margin-bottom:5px">From the reviewer</span>'
			+ escape_html(msg).replace("\n", "<br/>") +
			'</div>'
			"<p>To respond, open your submission in the portal, add the requested detail and save it - "
			"this returns your submission to the review queue automatically.</p>"
		)
		rows = [
			("Reference", escape_html(doc.get("name") or "-")),
			("Organisation", escape_html(doc.get("implementing_organization") or "-")),
			("Hazard", escape_html(doc.get("anticipated_hazard") or "-")),
		]
		html = aa_email_html(
			"We need a little more information", body, rows=rows,
			cta_label="Update your submission", cta_url=portal_url("/aa-portal"),
			chip="Action needed", chip_tone="amber",
			sign_off='Questions? Contact <a href="mailto:' + AA_INBOX + '" style="color:#CC0000">' + AA_INBOX + '</a>.',
		)
		aa_sendmail(
			[to],
			"More information needed - " + (doc.get("name") or ""),
			html,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "send_submission_replied")


def send_submission_received(doc, method=None):
	"""Acknowledge a freshly-filed Anticipatory Action to the reporter.

	Always sends a branded receipt; if the reporter ticked "email me a copy" the
	submission PDF is attached. Fully wrapped so a mail hiccup can never fail the
	submission that triggered it."""
	try:
		if doc.get("is_test"):
			return
		to = (doc.get("reporter_email") or "").strip()
		if not to:
			return
		name = escape_html(doc.get("reporting_person") or "there")
		body = (
			"<p>Dear " + name + ",</p>"
			"<p>Thank you for contributing to Kenya's anticipatory action. Your submission has been "
			"received and is now with the National TWG Secretariat for review. We'll be in touch "
			"once it has been assessed.</p>"
			"<p>Here is a summary for your records:</p>"
		)
		rows = [
			("Reference", escape_html(doc.get("name") or "-")),
			("Organisation", escape_html(doc.get("implementing_organization") or "-")),
			("Hazard", escape_html(doc.get("anticipated_hazard") or "-")),
			("Activation date", escape_html(str(doc.get("activation_start_date") or "-"))),
		]
		attachments = None
		if doc.get("email_me_a_copy"):
			try:
				from anticipatory_action.anticipatory_action.doctype.anticipatory_action.pdf import build_submission_pdf
				pdf = build_submission_pdf(doc)
				if pdf:
					attachments = [{"fname": (doc.get("name") or "submission") + ".pdf", "fcontent": pdf}]
			except Exception:
				frappe.log_error(frappe.get_traceback(), "submission receipt pdf")
		html = aa_email_html(
			"Thank you - your submission has been received", body, rows=rows,
			cta_label="View in your portal", cta_url=portal_url("/aa-portal"),
			chip="Received", chip_tone="slate",
			sign_off='Questions? Contact <a href="mailto:' + AA_INBOX + '" style="color:#CC0000">' + AA_INBOX + '</a>.',
		)
		aa_sendmail(
			[to],
			"We've received your submission - " + (doc.get("name") or ""),
			html,
			attachments=attachments,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "send_submission_received")


def send_new_submission_alert(doc, recipients):
	"""Alert reviewers (an organisation's approvers + all admins) that a new
	submission needs review. Each recipient is emailed SEPARATELY - one address per
	message - so reviewers' addresses are never exposed to one another. Fully
	wrapped so a mail hiccup can never fail the submission."""
	try:
		if doc.get("is_test"):
			return
		to_list = [e for e in {(r or "").strip() for r in (recipients or [])} if e]
		if not to_list:
			return
		body = (
			"<p>A new Anticipatory Action submission has been filed and is ready for your review "
			"in the admin console.</p>"
		)
		rows = [
			("Reference", escape_html(doc.get("name") or "-")),
			("Organisation", escape_html(doc.get("implementing_organization") or "-")),
			("Reporter", escape_html(doc.get("reporting_person") or "-")),
			("Hazard", escape_html(doc.get("anticipated_hazard") or "-")),
			("Activation date", escape_html(str(doc.get("activation_start_date") or "-"))),
		]
		html = aa_email_html(
			"A new submission is awaiting review", body, rows=rows,
			cta_label="Review in the admin console", cta_url=portal_url("/aa-admin"),
			chip="For review", chip_tone="blue",
			sign_off="You're receiving this as a reviewer for the Kenya Anticipatory Action programme.",
		)
		subject = "New submission for review - " + (doc.get("name") or "")
		for to in to_list:
			aa_sendmail([to], subject, html)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "send_new_submission_alert")
