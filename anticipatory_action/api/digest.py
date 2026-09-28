"""Daily summary email for reviewers, replacing per-event staff alerts.

Every morning (08:00 site time, see hooks.py) each reviewer gets ONE email instead
of an email per submission / access request:

* AA Admins (and the central AA inbox) - the whole programme: what was filed
  yesterday, the review queue, guest submissions held for an account, and
  pending access requests. Guest submissions always need an admin: the account
  has to be approved and the organisation may not exist on the platform yet.
* Approvers - their own organisation's submissions and queue; plus pending
  access requests when they hold the account-approval capability.

A digest is only sent when something new arrived yesterday or something has been
waiting longer than OVERDUE_DAYS, so quiet days send nothing.

Run by hand (e.g. to preview on a staging site):
	bench --site <site> execute anticipatory_action.api.digest.send_daily_digests --kwargs "{'force': 1}"
"""

import frappe
from frappe.utils import add_days, date_diff, escape_html, formatdate, getdate, nowdate

from anticipatory_action.api.aa_email import AA_INBOX, aa_email_html, aa_sendmail, portal_url
from anticipatory_action.api.permissions import _org_logins

OVERDUE_DAYS = 3
_ROLE_ADMIN = "Anticipatory Action Admin"
_ROLE_APPROVER = "Anticipatory Action Approver"

# Real, reviewable submissions: not test data, not a superseded (cancelled)
# version, and not held against a pending sign-up.
_LIVE = {"is_test": ["!=", 1], "docstatus": ["<", 2], "awaiting_account": ["!=", 1]}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _window(today):
	"""Yesterday, as [start, end) datetimes in site time."""
	start = add_days(today, -1)
	return f"{start} 00:00:00", f"{today} 00:00:00", start


def _owner_filter(owners):
	return {"owner": ["in", sorted(owners)]} if owners is not None else {}


def _new_submissions(win_start, win_end, owners=None):
	return frappe.get_all(
		"Anticipatory Action",
		filters={**_LIVE, **_owner_filter(owners), "creation": ["between", [win_start, win_end]]},
		fields=["name", "implementing_organization", "anticipated_hazard", "is_update"],
		order_by="creation asc",
	)


def _pending(today, owners=None):
	rows = frappe.get_all(
		"Anticipatory Action",
		filters={**_LIVE, **_owner_filter(owners), "status": "Pending", "docstatus": 0},
		fields=["name", "implementing_organization", "anticipated_hazard", "modified"],
		order_by="modified asc",
	)
	for r in rows:
		r.waiting = date_diff(today, getdate(r.modified))
	return rows


def _org_names():
	return {
		(n or "").strip().lower()
		for n in frappe.get_all("Anticipatory Action Organization", pluck="name_of_organization")
	}


def _guest_submissions(today):
	"""Submissions filed through guest checkout, held until an admin approves the
	applicant's account (and creates their organisation if it isn't listed)."""
	rows = frappe.get_all(
		"Anticipatory Action",
		filters={"awaiting_account": 1, "is_test": ["!=", 1], "docstatus": 0},
		fields=["name", "implementing_organization", "reporter_email", "linked_request", "creation"],
		order_by="creation asc",
	)
	known = _org_names()
	for r in rows:
		req = frappe.db.get_value(
			"AA Membership Request", r.linked_request, ["first_name", "last_name", "organization"], as_dict=True
		) if r.linked_request else None
		r.applicant = " ".join(p for p in [(req or {}).get("first_name"), (req or {}).get("last_name")] if p) or r.reporter_email
		r.org = ((req or {}).get("organization") or r.implementing_organization or "").strip()
		r.org_missing = bool(r.org) and r.org.lower() not in known
		r.waiting = date_diff(today, getdate(r.creation))
	return rows


def _access_requests(today):
	rows = frappe.get_all(
		"AA Membership Request",
		filters={"status": "Pending"},
		fields=["name", "first_name", "last_name", "email", "organization", "creation"],
		order_by="creation asc",
	)
	known = _org_names()
	held = {
		r.linked_request for r in frappe.get_all(
			"Anticipatory Action", filters={"awaiting_account": 1, "docstatus": 0}, fields=["linked_request"]
		) if r.linked_request
	}
	for r in rows:
		r.applicant = " ".join(p for p in [r.first_name, r.last_name] if p) or r.email
		r.org = (r.organization or "").strip()
		r.org_missing = bool(r.org) and r.org.lower() not in known
		r.has_held = r.name in held
		r.waiting = date_diff(today, getdate(r.creation))
	return rows


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_TH = "text-align:left;padding:6px 8px;font-size:11px;color:#6B7280;border-bottom:1px solid #E5E7EB;font-weight:600"
_TD = "padding:7px 8px;font-size:13px;color:#111827;border-bottom:1px solid #F3F4F6;vertical-align:top"


def _h(text):
	return ('<h3 style="margin:24px 0 8px;font-size:15px;color:#111827">' + escape_html(text) + "</h3>")


def _p(html):
	return '<p style="margin:0 0 8px;font-size:13.5px;color:#374151">' + html + "</p>"


def _table(headers, rows):
	head = "".join(f'<th style="{_TH}">{escape_html(h)}</th>' for h in headers)
	body = "".join("<tr>" + "".join(f'<td style="{_TD}">{c}</td>' for c in r) + "</tr>" for r in rows)
	return f'<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;margin:4px 0 6px"><tr>{head}</tr>{body}</table>'


def _days(n):
	n = int(n or 0)
	label = "today" if n <= 0 else ("1 day" if n == 1 else f"{n} days")
	style = "color:#B91C1C;font-weight:600" if n > OVERDUE_DAYS else "color:#6B7280"
	return f'<span style="{style}">{label}</span>'


def _flag(text):
	return (' <span style="display:inline-block;margin-top:3px;font-size:11px;font-weight:600;color:#92400E;'
			'background:#FEF3C7;padding:1px 7px;border-radius:999px">' + escape_html(text) + "</span>")


def _plural(n, word, many=None):
	return f"{n} {word if n == 1 else (many or word + 's')}"


def _new_section(new, day_label):
	if not new:
		return _h(f"Filed on {day_label}") + _p("No new submissions.")
	by_org = {}
	for r in new:
		by_org[r.implementing_organization or "Unknown"] = by_org.get(r.implementing_organization or "Unknown", 0) + 1
	rows = [[escape_html(org), str(n)] for org, n in sorted(by_org.items(), key=lambda x: (-x[1], x[0]))]
	updates = sum(1 for r in new if r.is_update)
	note = f" ({_plural(updates, 'update')} to earlier submissions)" if updates else ""
	return (_h(f"Filed on {day_label}: {_plural(len(new), 'submission')}")
			+ _p(f"{len(new)} new{escape_html(note)}, by organisation:")
			+ _table(["Organisation", "Submissions"], rows))


def _pending_section(pending):
	if not pending:
		return _h("Review queue") + _p("Nothing is waiting for review.")
	overdue = [r for r in pending if r.waiting > OVERDUE_DAYS]
	lead = f"{_plural(len(pending), 'submission')} waiting for review"
	if overdue:
		lead += f", <b style=\"color:#B91C1C\">{len(overdue)} for more than {OVERDUE_DAYS} days</b>"
	shown = sorted(pending, key=lambda r: -r.waiting)[:10]
	rows = [[escape_html(r.name), escape_html(r.implementing_organization or "-"),
			 escape_html(r.anticipated_hazard or "-"), _days(r.waiting)] for r in shown]
	more = _p(f"…and {len(pending) - len(shown)} more in the console.") if len(pending) > len(shown) else ""
	return _h("Review queue") + _p(lead + ".") + _table(["Reference", "Organisation", "Hazard", "Waiting"], rows) + more


def _guest_section(guests):
	if not guests:
		return ""
	rows = []
	for r in guests:
		who = escape_html(r.applicant) + '<br><span style="color:#6B7280;font-size:12px">' + escape_html(r.reporter_email or "") + "</span>"
		org = escape_html(r.org or "-") + (_flag("Not on the platform - create it first") if r.org_missing else "")
		rows.append([escape_html(r.name), who, org, _days(r.waiting)])
	return (_h(f"Guest submissions waiting for an account: {len(guests)}")
			+ _p("These were filed by people without an account. They stay out of the review queue until you "
				 "approve the applicant's access request. If their organisation isn't on the platform yet, add it "
				 "under Organisations first so you can assign it when approving.")
			+ _table(["Reference", "Applicant", "Organisation", "Waiting"], rows))


def _requests_section(requests):
	if not requests:
		return ""
	rows = []
	for r in requests:
		who = escape_html(r.applicant) + '<br><span style="color:#6B7280;font-size:12px">' + escape_html(r.email or "") + "</span>"
		org = escape_html(r.org or "-") + (_flag("Not on the platform") if r.org_missing else "")
		extra = _flag("Has a held submission") if r.has_held else ""
		rows.append([who + extra, org, _days(r.waiting)])
	return (_h(f"Access requests waiting: {len(requests)}")
			+ _table(["Applicant", "Organisation", "Waiting"], rows))


def _needs_sending(new, pending, guests, requests, new_requests):
	if new or new_requests or any(date_diff(getdate(nowdate()), getdate(g.creation)) <= 1 for g in guests):
		return True
	return any(r.waiting > OVERDUE_DAYS for r in (pending + guests + requests))


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def _recipient(row):
	return (row.get("user") or row.get("email") or "").strip()


def _send(to, subject, heading, body):
	html = aa_email_html(
		heading, body,
		cta_label="Open the admin console", cta_url=portal_url("/aa-admin"),
		chip="Daily summary", chip_tone="blue",
		sign_off="You receive this summary as a reviewer for the Kenya Anticipatory Action programme. "
			"It is sent each morning only when something is new or waiting.",
	)
	aa_sendmail([to], subject, html)


def build_admin_digest(today=None):
	"""(subject, heading, body_html, should_send) for the programme-wide digest."""
	today = getdate(today or nowdate())
	win_start, win_end, day = _window(today)
	day_label = formatdate(day, "d MMM yyyy")
	new = _new_submissions(win_start, win_end)
	pending = _pending(today)
	guests = _guest_submissions(today)
	requests = _access_requests(today)
	new_guests = [g for g in guests if win_start <= str(g.creation) < win_end]
	new_requests = [r for r in requests if win_start <= str(r.creation) < win_end]

	summary = [_plural(len(new), "new submission")]
	if new_guests:
		summary.append(_plural(len(new_guests), "new guest submission"))
	if new_requests:
		summary.append(_plural(len(new_requests), "new access request"))
	actions = []
	if pending:
		actions.append(f"review {_plural(len(pending), 'submission')}")
	if guests:
		actions.append(f"set up accounts for {_plural(len(guests), 'guest submission')}")
	if requests:
		actions.append(f"decide {_plural(len(requests), 'access request')}")

	body = (_p(f"<b>{escape_html(day_label)}:</b> " + escape_html(", ".join(summary)) + ".")
			+ (_p("<b>Needs your action:</b> " + escape_html("; ".join(actions)) + ".") if actions
			   else _p("Nothing needs your action right now."))
			+ _guest_section(guests)
			+ _requests_section(requests)
			+ _pending_section(pending)
			+ _new_section(new, day_label))
	subject = f"AA daily summary {formatdate(day, 'd MMM')}: {len(new)} new, {len(pending) + len(guests) + len(requests)} to action"
	return subject, "Your daily summary", body, _needs_sending(new, pending, guests, requests, new_requests)


def build_approver_digest(approver, today=None):
	"""(subject, heading, body_html, should_send) for one approver's organisation."""
	today = getdate(today or nowdate())
	win_start, win_end, day = _window(today)
	day_label = formatdate(day, "d MMM yyyy")
	owners = _org_logins(approver.organization) | {_recipient(approver)}
	org_name = frappe.db.get_value("Anticipatory Action Organization", approver.organization, "name_of_organization") or ""
	new = _new_submissions(win_start, win_end, owners)
	pending = _pending(today, owners)
	requests = _access_requests(today) if approver.can_approve_accounts else []
	new_requests = [r for r in requests if win_start <= str(r.creation) < win_end]

	actions = []
	if pending:
		actions.append(f"review {_plural(len(pending), 'submission')}")
	if requests:
		actions.append(f"decide {_plural(len(requests), 'access request')}")
	body = (_p(f"<b>{escape_html(day_label)}:</b> {_plural(len(new), 'new submission')} from "
			   + escape_html(org_name or "your organisation") + ".")
			+ (_p("<b>Needs your action:</b> " + escape_html("; ".join(actions)) + ".") if actions
			   else _p("Nothing needs your action right now."))
			+ _requests_section(requests)
			+ _pending_section(pending)
			+ _new_section(new, day_label))
	subject = f"AA daily summary {formatdate(day, 'd MMM')} - {org_name}: {len(new)} new, {len(pending)} to review"
	return subject, "Your daily summary", body, _needs_sending(new, pending, [], requests, new_requests)


def send_daily_digests(force=0):
	"""Scheduler entry point (08:00 daily). Sends at most once per day per site
	unless ``force`` is set (manual preview/resend)."""
	today = getdate(nowdate())
	key = f"aa:daily_digest:{today}"
	if not int(force or 0) and frappe.cache.get_value(key):
		return
	sent = 0
	try:
		subject, heading, body, go = build_admin_digest(today)
		if go:
			admins = frappe.get_all(
				"Anticipatory Action User", filters={"role": _ROLE_ADMIN, "enabled": 1}, fields=["user", "email"]
			)
			for to in sorted({_recipient(a) for a in admins if _recipient(a)} | {AA_INBOX}):
				_send(to, subject, heading, body)
				sent += 1
	except Exception:
		frappe.log_error(frappe.get_traceback(), "aa daily digest (admin)")

	for ap in frappe.get_all(
		"Anticipatory Action User",
		filters={"role": _ROLE_APPROVER, "enabled": 1, "organization": ["is", "set"]},
		fields=["user", "email", "organization", "can_approve_accounts"],
	):
		to = _recipient(ap)
		if not to:
			continue
		try:
			subject, heading, body, go = build_approver_digest(ap, today)
			if go:
				_send(to, subject, heading, body)
				sent += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"aa daily digest (approver {to})")

	frappe.cache.set_value(key, 1, expires_in_sec=36 * 3600)
	return sent
