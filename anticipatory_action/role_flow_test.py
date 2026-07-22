"""End-to-end role + flow test for the Anticipatory Action app.

Exercises every role (Guest / Member / Approver / Admin / System Manager), the
email notifications each flow fires, and the test/dissemination mode — then cleans
up everything it created.

Run it:

    bench --site <your-site> execute anticipatory_action.role_flow_test.run

By default it CAPTURES outgoing mail (asserts the right notification fired, with
the right recipient/subject/PDF) without delivering anything and without needing
Redis or an SMTP account — so it is safe and repeatable on any site. To also send
the mail for real (to eyeball the actual inboxes on a running stack with an
outgoing Email Account configured):

    bench --site <your-site> execute anticipatory_action.role_flow_test.run --kwargs "{'send_real': 1}"

Prefer a staging/test site. It creates a handful of @example.com users/orgs and
deletes them at the end.
"""

import frappe

from anticipatory_action.api import anticipatory_action as aa
from anticipatory_action.api import portal
from anticipatory_action.anticipatory_action.page.aa_operations import aa_operations as ops

# --------------------------------------------------------------------------- #
# Tiny test harness
# --------------------------------------------------------------------------- #
_RESULTS = []       # (section, name, status, detail)  status: PASS/FAIL/SKIP
_CREATED = []       # (doctype, name) for cleanup, deleted in reverse
_MAILS = []         # captured outgoing emails


def _log(section, name, status, detail=""):
    _RESULTS.append((section, name, status, str(detail)[:120]))


def _check(section, name, cond, detail=""):
    _log(section, name, "PASS" if cond else "FAIL", detail)
    return bool(cond)


def _throws_perm(fn):
    try:
        fn()
        return False
    except frappe.PermissionError:
        return True
    except Exception as e:
        return "OTHER:%s" % type(e).__name__


def _track(doctype, name):
    if name:
        _CREATED.append((doctype, name))
    return name


def _mark():
    """Marker into the (never-cleared) email log, so a flow can assert only the
    mail IT fired without discarding earlier notifications from the summary."""
    return len(_MAILS)


def _mail_to(addr, since=0):
    """Captured emails since `since` whose recipient list includes addr."""
    out = []
    for m in _MAILS[since:]:
        rcpts = m["recipients"]
        rcpts = rcpts if isinstance(rcpts, (list, tuple)) else [rcpts]
        if any(addr in (r or "") for r in rcpts):
            out.append(m)
    return out


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def _first_option(doctype, fieldname, fallback=""):
    opts = (frappe.get_meta(doctype).get_field(fieldname).options or "").split("\n")
    return next((o for o in opts if o.strip()), fallback)


def _make_org(tag, label):
    otype = _first_option("Anticipatory Action Organization", "type_of_organization", "NGO")
    doc = frappe.get_doc({
        "doctype": "Anticipatory Action Organization",
        "name_of_organization": "RFT %s %s" % (tag, label),
        "type_of_organization": otype,
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    return _track("Anticipatory Action Organization", doc.name)


def _make_user(email, first, org, role, can_approve_accounts=0):
    doc = frappe.get_doc({
        "doctype": "Anticipatory Action User",
        "first_name": first, "last_name": "RFT", "email": email,
        "phone": "0712345678", "organization": org, "role": role,
        "enabled": 1, "can_approve_accounts": can_approve_accounts,
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    _track("Anticipatory Action User", doc.name)
    if frappe.db.exists("User", email):
        _track("User", email)
    return doc.name


def _sub_payload(tag, reporter_email):
    et = _first_option("Anticipatory Action", "entity_or_organization_type", "Other")
    sector = _first_option("Anticipatory Action Details", "sector", "Health and Nutrition")
    return {
        "implementing_organization": "RFT %s Activation" % tag,
        "entity_or_organization_type": et, "funding_source": "RFT Fund",
        "reporting_person": "RFT Reporter", "reporter_email": reporter_email,
        "reporter_phone_number": "0712345678", "anticipated_hazard": "Drought",
        "activation_start_date": "2026-08-01", "activation_end_date": "2026-08-31",
        "email_me_a_copy": 1,
        "anticipatory_action_details": [{
            "county": "Garissa", "sector": sector, "status_of_the_early_action": "Planned",
            "amount_for_anticipatory_action_kes": 1000,
            "describe_the_anticipatory_action_intervention": "RFT intervention",
            "number_of_people_targeted": 10, "number_of_hh_targeted": 3,
        }],
    }


def _new_submission(tag, owner_email, reporter_email, is_test=0):
    """Insert a submission as `owner_email` (via the real guest/member endpoint)."""
    frappe.set_user(owner_email)
    try:
        res = aa.submit_anticipatory_action(frappe.as_json(_sub_payload(tag, reporter_email)))
    finally:
        frappe.set_user("Administrator")
    name = res.get("name")
    _track("Anticipatory Action", name)
    return name


# --------------------------------------------------------------------------- #
# The test
# --------------------------------------------------------------------------- #
def run(send_real=0):
    send_real = int(send_real)
    orig_user = frappe.session.user
    orig_sendmail = frappe.sendmail
    orig_enqueue = getattr(frappe, "enqueue", None)
    orig_testing = frappe.db.get_single_value("Anticipatory Action Settings", "testing_enabled")

    def _capture(*a, **k):
        _MAILS.append({
            "recipients": k.get("recipients") or (a[0] if a else None),
            "subject": k.get("subject"),
            "has_pdf": bool(k.get("attachments")),
        })
        if send_real:
            try:
                orig_sendmail(*a, **k)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "role_flow_test send_real")

    frappe.sendmail = _capture
    if not send_real:
        frappe.enqueue = lambda *a, **k: None

    tag = frappe.generate_hash(length=5)
    try:
        frappe.set_user("Administrator")

        # ---- fixtures --------------------------------------------------------
        org_a = _make_org(tag, "OrgA")
        org_b = _make_org(tag, "OrgB")
        admin_email = "rft.admin.%s@example.com" % tag
        appr_email = "rft.approver.%s@example.com" % tag
        mem_a_email = "rft.member.a.%s@example.com" % tag
        mem_b_email = "rft.member.b.%s@example.com" % tag
        _make_user(admin_email, "Admin", org_a, "Anticipatory Action Admin")
        _make_user(appr_email, "Approver", org_a, "Anticipatory Action Approver", can_approve_accounts=1)
        _make_user(mem_a_email, "MemberA", org_a, "Anticipatory Action User")
        _make_user(mem_b_email, "MemberB", org_b, "Anticipatory Action User")
        frappe.db.commit()
        _check("Setup", "fixtures created (2 orgs, admin, approver, 2 members)", True)
        # (the fixture welcome emails stay in the email log and show in the summary)

        # ================================================================== #
        # GUEST
        # ================================================================== #
        frappe.set_user("Guest")
        _check("Guest", "get_public_metrics works", aa.get_public_metrics().get("success") is True)
        _check("Guest", "get_faqs works", aa.get_faqs().get("success") is True)
        _check("Guest", "get_activities_events works", aa.get_activities_events().get("success") is True)

        # guest submission -> Pending draft owned by Guest
        gsub = _new_submission(tag, "Guest", "rft.guest.%s@example.com" % tag)
        frappe.set_user("Guest")
        gs = frappe.db.get_value("Anticipatory Action", gsub, ["docstatus", "status", "owner"], as_dict=True)
        _check("Guest", "guest submission is a Pending draft", gs.docstatus == 0 and gs.status == "Pending" and gs.owner == "Guest", gs)

        # membership request + email + enumeration safety
        req_email = "rft.signup.%s@example.com" % tag
        mk = _mark()
        r1 = portal.submit_membership_request(first_name="Sign", last_name="Up", email=req_email,
            phone="0712345678", organization="RFT Org", position="Officer", message="please")
        req_name = frappe.db.get_value("AA Membership Request", {"email": req_email, "status": "Pending"}, "name")
        _track("AA Membership Request", req_name)
        _check("Guest", "membership request created", bool(req_name) and r1.get("success") is True)
        _check("Guest", "membership 'request received' email fired", len(_MAILS) - mk >= 1)
        # enumeration-safe: existing member email -> same neutral shape, no new request
        r2 = portal.submit_membership_request(first_name="X", last_name="Y", email=mem_a_email,
            phone="0712345678", organization="RFT", position="Officer")
        _check("Guest", "SEC-005 known-email neutral (no 'name'/'error')",
               r2 == {"success": True}, r2)

        # guest checkout -> request + held submission
        acc = {"first_name": "Guest", "last_name": "Checkout", "email": "rft.checkout.%s@example.com" % tag,
               "phone": "0712345678", "organization": "RFT Org", "position": "Officer"}
        gc = portal.submit_guest_application(frappe.as_json(_sub_payload(tag, acc["email"])), frappe.as_json(acc))
        gc_sub = gc.get("name")
        _track("Anticipatory Action", gc_sub)
        gc_req = frappe.db.get_value("AA Membership Request", {"email": acc["email"], "status": "Pending"}, "name")
        _track("AA Membership Request", gc_req)
        held = frappe.db.get_value("Anticipatory Action", gc_sub, ["awaiting_account", "linked_request"], as_dict=True) if gc_sub else {}
        _check("Guest", "guest checkout holds submission + links request",
               gc.get("success") and held.get("awaiting_account") == 1 and held.get("linked_request") == gc_req, held)

        # contact + pillar routing email
        mk = _mark()
        pillar = frappe.db.get_value("AA Pillar Lead", {}, "name")
        c1 = portal.submit_contact(full_name="Con Tact", email="rft.contact.%s@example.com" % tag,
            organization="RFT", phone="0712345678", subject="Hi", message="Hello",
            request_type="Get involved" if pillar else "General enquiry", pillar=pillar)
        cm = frappe.db.get_value("AA Contact Message", {"email": "rft.contact.%s@example.com" % tag}, "name")
        _track("AA Contact Message", cm)
        _check("Guest", "contact message stored", c1.get("success") and bool(cm))
        if pillar:
            _check("Guest", "pillar routing email fired", len(_MAILS) - mk >= 1, "pillar=%s" % pillar)
        else:
            _log("Guest", "pillar routing email fired", "SKIP", "no AA Pillar Lead configured")

        # UAT feedback
        u1 = aa.submit_uat_feedback({"tester_name": "RFT Tester", "tester_email": "rft.uat.%s@example.com" % tag,
                                     "overall_rating": 5})
        uf = frappe.db.get_value("AA UAT Feedback", {"tester_name": "RFT Tester"}, "name")
        _track("AA UAT Feedback", uf)
        _check("Guest", "UAT feedback stored", u1.get("success") and bool(uf))

        # guest DENIED privileged endpoints
        _check("Guest", "SEC-001 reporting feed denies Guest", _throws_perm(lambda: aa.get_anticipatory_action_data(1)) is True)
        _check("Guest", "portal admin denies Guest", _throws_perm(lambda: portal.list_aa_users()) is True)
        _check("Guest", "SEC-002 aa_operations denies Guest", _throws_perm(lambda: ops.get_reports()) is True)

        # ================================================================== #
        # MEMBER
        # ================================================================== #
        frappe.set_user(mem_a_email)
        land = portal.get_landing()
        _check("Member", "login lands on /aa-portal", "portal" in str(land).lower(), land)

        m_sub = _new_submission(tag, mem_a_email, mem_a_email)
        frappe.set_user(mem_a_email)
        mine = portal.get_my_submissions().get("data", [])
        names = {r["name"] for r in mine}
        _check("Member", "sees own submission", m_sub in names)
        # member should NOT see another member's submission
        b_sub = _new_submission(tag, mem_b_email, mem_b_email)
        frappe.set_user(mem_a_email)
        names2 = {r["name"] for r in portal.get_my_submissions().get("data", [])}
        _check("Member", "does NOT see another member's submission", b_sub not in names2)

        # SEC-101: javascript: report link rejected
        _check("Member", "SEC-101 javascript: report link rejected",
               _rejects(lambda: portal.submit_my_report(title="x", link="javascript:alert(1)")))
        rep = portal.submit_my_report(title="RFT Report %s" % tag, link="https://example.com/r.pdf", visibility="Private")
        _track("Anticipatory Report", rep.get("name"))
        _check("Member", "valid report stored", rep.get("success") is True)
        _check("Member", "member sees reports library (Public+Private)", isinstance(ops.get_reports(), list))

        # member DENIED admin/approver actions
        _check("Member", "cannot create users", _throws_perm(lambda: portal.create_aa_user("a", "b", "z@x.com", "0712345678", org_a)) is True)
        _check("Member", "cannot review (set_submission_status)", _throws_perm(lambda: portal.set_submission_status(m_sub, "Approved")) is True)
        _check("Member", "profile update works", portal.update_my_profile(first_name="MemberA2").get("success") is True)
        sr = portal.submit_support_request(subject="RFT Help %s" % tag, message="Issue")
        _track("AA Support Request", frappe.db.get_value("AA Support Request", {"raised_by": mem_a_email}, "name"))
        _check("Member", "support request works", sr.get("success") is True)

        # ================================================================== #
        # APPROVER  (org-scoped)
        # ================================================================== #
        frappe.set_user(appr_email)
        _check("Approver", "login lands on /aa-admin", "admin" in str(portal.get_landing()).lower())
        acts = ops.get_activations()
        act_names = {a["name"] for a in acts}
        _check("Approver", "sees own-org submission in queue", m_sub in act_names)
        _check("Approver", "does NOT see other-org submission", b_sub not in act_names)

        # approve own-org submission -> approval email with PDF to reporter
        mk = _mark()
        portal.set_submission_status(m_sub, "Approved")
        _check("Approver", "approval submits doc", frappe.db.get_value("Anticipatory Action", m_sub, "docstatus") == 1)
        appr_mail = _mail_to(mem_a_email, mk)
        _check("Approver", "approval email fired to reporter", len(appr_mail) >= 1, [m["subject"] for m in appr_mail])
        _check("Approver", "approval email carries the PDF", any(m["has_pdf"] for m in appr_mail))

        # WKF-001: approved -> Not Approved reopens an editable draft + emails reporter
        mk = _mark()
        rr = portal.set_submission_status(m_sub, "Not Approved", reason="needs budget")
        reopened = rr.get("name")
        _track("Anticipatory Action", reopened)
        rd = frappe.db.get_value("Anticipatory Action", reopened, ["docstatus", "status", "amended_from"], as_dict=True) if reopened else {}
        _check("Approver", "WKF-001 reopen -> editable Draft",
               reopened and rd.get("docstatus") == 0 and rd.get("status") == "Not Approved" and rd.get("amended_from") == m_sub, rd)
        rej_mail = _mail_to(mem_a_email, mk)
        _check("Approver", "rejection email fired to reporter", len(rej_mail) >= 1, [m["subject"] for m in rej_mail])

        # SEC-003: cross-org change-log denied, own-org allowed
        mem_b_roster = frappe.db.get_value("Anticipatory Action User", {"email": mem_b_email}, "name")
        mem_a_roster = frappe.db.get_value("Anticipatory Action User", {"email": mem_a_email}, "name")
        frappe.set_user(appr_email)
        _check("Approver", "SEC-003 cross-org change-log denied",
               _throws_perm(lambda: portal.get_change_log("Anticipatory Action Organization", org_b)) is True)
        _check("Approver", "SEC-003 own-org change-log allowed",
               _throws_perm(lambda: portal.get_change_log("Anticipatory Action Organization", org_a)) is False)

        # content curation
        f1 = portal.add_faq(question="RFT?", answer="<b>Yes</b><script>bad()</script>")
        _track("AA FAQ", f1.get("name"))
        stored_faq = frappe.db.get_value("AA FAQ", f1.get("name"), "answer") or ""
        _check("Approver", "SEC-102 FAQ sanitised on store", "<script>" not in stored_faq and "<b>Yes</b>" in stored_faq)
        _check("Approver", "approver cannot manage users", _throws_perm(lambda: portal.create_aa_user("a", "b", "z2@x.com", "0712345678", org_a)) is True)

        # ================================================================== #
        # ADMIN
        # ================================================================== #
        frappe.set_user(admin_email)
        mk = _mark()
        new_email = "rft.created.%s@example.com" % tag
        cu = portal.create_aa_user(first_name="Created", last_name="ByAdmin", email=new_email,
                                   phone="0712345678", organization=org_a, role="Anticipatory Action User")
        _track("Anticipatory Action User", frappe.db.get_value("Anticipatory Action User", {"email": new_email}, "name"))
        if frappe.db.exists("User", new_email):
            _track("User", new_email)
        _check("Admin", "create_aa_user provisions account", cu.get("success") and frappe.db.exists("User", new_email))
        _check("Admin", "welcome/set-password email fired", len(_mail_to(new_email, mk)) >= 1, [m["subject"] for m in _mail_to(new_email, mk)])

        # admin can set roles (WKF-003)
        up = portal.update_aa_user(frappe.db.get_value("Anticipatory Action User", {"email": new_email}, "name"),
                                   role="Anticipatory Action Approver")
        _check("Admin", "admin can change role", up.get("success") and "Anticipatory Action Approver" in set(frappe.get_roles(new_email)))

        # approve a membership request -> account + welcome + release held submissions
        mk = _mark()
        frappe.set_user(admin_email)
        ap = portal.approve_request(gc_req, organization=org_a, role="Anticipatory Action User")
        checkout_user = acc["email"]
        if frappe.db.exists("Anticipatory Action User", {"email": checkout_user}):
            _track("Anticipatory Action User", frappe.db.get_value("Anticipatory Action User", {"email": checkout_user}, "name"))
        if frappe.db.exists("User", checkout_user):
            _track("User", checkout_user)
        released = frappe.db.get_value("Anticipatory Action", gc_sub, ["awaiting_account", "owner"], as_dict=True) if gc_sub else {}
        _check("Admin", "approve_request provisions + welcomes", ap.get("success") and len(_mail_to(checkout_user, mk)) >= 1)
        _check("Admin", "held submission released to new owner",
               released.get("awaiting_account") in (0, None) and (released.get("owner") or "") != "Guest", released)

        # reject the plain sign-up request
        rj = portal.reject_request(req_name, notes="dup")
        _check("Admin", "reject_request works", rj.get("success") is True and frappe.db.get_value("AA Membership Request", req_name, "status") == "Rejected")

        # admin password reset -> set-password email
        mk = _mark()
        pr = portal.send_password_reset(mem_a_roster)
        _check("Admin", "password reset email fired", (pr.get("success") if isinstance(pr, dict) else True) and len(_mail_to(mem_a_email, mk)) >= 1)

        # ================================================================== #
        # SYSTEM MANAGER / ADMINISTRATOR — reporting feeds
        # ================================================================== #
        frappe.set_user("Administrator")
        feed = aa.get_anticipatory_action_data(100)
        _check("SysMgr", "reporting feed returns data to reviewer", feed.get("success") is True and isinstance(feed.get("data"), list))

        # ================================================================== #
        # TEST / DISSEMINATION MODE
        # ================================================================== #
        frappe.db.set_single_value("Anticipatory Action Settings", "testing_enabled", 0)
        frappe.db.commit()
        off = aa.submit_test_application(frappe.as_json(_sub_payload(tag, "rft.test.%s@example.com" % tag)))
        _check("TestMode", "test submit rejected when testing OFF", off.get("success") is False)

        frappe.db.set_single_value("Anticipatory Action Settings", "testing_enabled", 1)
        frappe.db.set_single_value("Anticipatory Action Settings", "test_batch_name", "RFT Batch %s" % tag)
        frappe.db.commit()
        metrics_before = aa.get_public_metrics().get("approved_submissions")
        ton = aa.submit_test_application(frappe.as_json(_sub_payload(tag, "rft.test.%s@example.com" % tag)))
        tsub = ton.get("name")
        _track("Anticipatory Action", tsub)
        tflags = frappe.db.get_value("Anticipatory Action", tsub, ["is_test", "test_batch"], as_dict=True) if tsub else {}
        _check("TestMode", "test submit creates is_test row when ON", ton.get("success") and tflags.get("is_test") == 1)
        _check("TestMode", "test row tagged with batch", (tflags.get("test_batch") or "").startswith("RFT Batch"))

        # test excluded from public metrics + real feed, included in test feed
        _check("TestMode", "test excluded from public metrics",
               aa.get_public_metrics().get("approved_submissions") == metrics_before)
        realfeed_names = {d["name"] for d in aa.get_anticipatory_action_data(500).get("data", [])}
        testfeed_names = {d["name"] for d in aa.get_test_data(500).get("data", [])}
        _check("TestMode", "test row excluded from real feed", tsub not in realfeed_names)
        _check("TestMode", "test row present in test feed", tsub in testfeed_names)

        # approving a test submission sends NO email (WKF-002)
        # a test row from member A's org so the approver can act on it
        t_owned = _new_submission(tag, mem_a_email, mem_a_email)
        frappe.db.set_value("Anticipatory Action", t_owned, "is_test", 1)
        frappe.db.commit()
        mk = _mark()
        frappe.set_user(appr_email)
        portal.set_submission_status(t_owned, "Approved")
        _check("TestMode", "approving a TEST submission sends NO email", len(_MAILS) - mk == 0, "mails=%d" % (len(_MAILS) - mk))

        # rejecting a TEST submission is likewise silent (is_test guard on the
        # rejection email); reopens as an editable Draft carrying is_test
        mk = _mark()
        tr = portal.set_submission_status(t_owned, "Not Approved", reason="test reject")
        _track("Anticipatory Action", tr.get("name"))
        _check("TestMode", "rejecting a TEST submission sends NO email", len(_MAILS) - mk == 0, "mails=%d" % (len(_MAILS) - mk))

    except Exception as e:
        import traceback
        _log("FATAL", type(e).__name__, "FAIL", traceback.format_exc().splitlines()[-1])
        traceback.print_exc()
    finally:
        # ---- restore + cleanup ----------------------------------------------
        frappe.set_user("Administrator")
        frappe.sendmail = orig_sendmail
        if orig_enqueue is not None:
            frappe.enqueue = orig_enqueue
        try:
            frappe.db.set_single_value("Anticipatory Action Settings", "testing_enabled", orig_testing or 0)
        except Exception:
            pass
        _cleanup(tag)
        try:
            frappe.set_user(orig_user)
        except Exception:
            pass

    _report()
    return {"passed": sum(1 for r in _RESULTS if r[2] == "PASS"),
            "failed": sum(1 for r in _RESULTS if r[2] == "FAIL"),
            "total": len(_RESULTS)}


def _rejects(fn):
    try:
        return fn().get("success") is False
    except Exception:
        return True


def _cleanup(tag):
    # Deleting a User (and some docs) enqueues background work; stub enqueue for the
    # duration of teardown so cleanup never needs a running Redis and always removes
    # everything this run created (otherwise User rows leak on a Redis-less bench).
    _orig_enqueue = getattr(frappe, "enqueue", None)
    frappe.enqueue = lambda *a, **k: None
    try:
        _cleanup_sweep(tag)
    finally:
        if _orig_enqueue is not None:
            frappe.enqueue = _orig_enqueue


def _cleanup_sweep(tag):
    # Safety-net sweep: catch any tag-scoped records this run created but didn't
    # explicitly track (amendments, releases, an interrupted run), so nothing leaks.
    email_like = "rft.%" + tag + "@example.com"
    tag_like = "RFT " + tag + "%"
    sweeps = [
        ("Anticipatory Action", {"implementing_organization": ["like", tag_like]}),
        ("AA Support Request", {"raised_by": ["like", email_like]}),
        ("Anticipatory Report", {"title": ["like", tag_like]}),
        ("AA Contact Message", {"email": ["like", email_like]}),
        ("AA Membership Request", {"email": ["like", email_like]}),
        ("Anticipatory Action User", {"email": ["like", email_like]}),
        ("User", {"email": ["like", email_like]}),
        ("Anticipatory Action Organization", {"name_of_organization": ["like", tag_like]}),
    ]
    for dt, filt in sweeps:
        try:
            for nm in frappe.get_all(dt, filters=filt, pluck="name"):
                _CREATED.append((dt, nm))
        except Exception:
            pass
    seen = set()
    for doctype, name in reversed(_CREATED):
        if not name or (doctype, name) in seen:
            continue
        seen.add((doctype, name))
        try:
            if not frappe.db.exists(doctype, name):
                continue
            if doctype == "Anticipatory Action":
                d = frappe.get_doc(doctype, name)
                if d.docstatus == 1:
                    d.flags.ignore_permissions = True
                    d.cancel()
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)
        except Exception as e:
            _log("Cleanup", "%s %s" % (doctype, name), "FAIL", type(e).__name__)
    frappe.db.commit()


def _report():
    print("\n" + "=" * 66)
    print("  ANTICIPATORY ACTION — ROLE + FLOW TEST")
    print("=" * 66)
    section = None
    for sec, name, status, detail in _RESULTS:
        if sec != section:
            print("\n[%s]" % sec)
            section = sec
        line = "  %-5s %s" % (status, name)
        if status != "PASS" and detail:
            line += "   -> %s" % detail
        print(line)
    p = sum(1 for r in _RESULTS if r[2] == "PASS")
    f = sum(1 for r in _RESULTS if r[2] == "FAIL")
    s = sum(1 for r in _RESULTS if r[2] == "SKIP")
    print("\n" + "-" * 66)
    print("  EMAILS CAPTURED (%d):" % len(_MAILS))
    for m in _MAILS:
        print("    -> %s | %s%s" % (m["recipients"], m["subject"], "  [+PDF]" if m["has_pdf"] else ""))
    print("-" * 66)
    print("  RESULT:  PASS %d   FAIL %d   SKIP %d   / %d" % (p, f, s, len(_RESULTS)))
    print("=" * 66)
