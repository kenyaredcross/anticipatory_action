# Anticipatory Action (Kenya)

A Frappe app for the Kenya **Anticipatory Action** coalition (NDOC / NDRMA and TWG
partners): a public information site plus a member/approver/admin self-service
portal for submitting, reviewing and approving anticipatory-action activations,
and feeding approved data to reporting/PowerBI.

The app collects personal data (names, emails, phone numbers) of Kenyan
participants and reporters, so it operates under the **Kenya Data Protection Act
2019**. Treat the portal API (`api/portal.py`) as the trust boundary: every
privileged endpoint carries an explicit server-side role/ownership guard and runs
under `ignore_permissions` only *after* that guard.

## Architecture (where things live)

- `api/portal.py` — the member/approver/admin portal + admin API (the trust boundary).
- `api/anticipatory_action.py` — public submission endpoints, public metrics, and the
  PowerBI/reporting feeds (reviewer-gated).
- `api/permissions.py` — multi-tenant row-level scoping (an Approver sees only their own
  organisation) via `permission_query_conditions` / `has_permission` hooks, plus the
  `require_aa_access` / `require_reporting_access` endpoint guards.
- `api/aa_email.py`, `doctype/anticipatory_action/pdf.py` — branded email + the approval PDF.
- `api/scheduling.py` — daily job that flips activity/event status from their dates.
- `www/` — the public pages and the portal/admin single-page consoles. Whitelisted web
  controllers must be **underscore-named** (`aa_admin.py`), never hyphenated
  (`aa-contact.py`), because `/api/method` cannot import a hyphenated dotted path.
- `page/aa_operations/` — the desk operations console (Admin/Approver only).

Roles: **Anticipatory Action User** (member) < **Anticipatory Action Approver**
(reviews & curates, confined to their own organisation) < **Anticipatory Action
Admin** (manages the AA roster, orgs and sign-ups). None can ever be escalated to
System Manager.

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app anticipatory_action
bench --site <site> migrate
```

## Deployment prerequisites (do these before go-live)

1. **Outgoing Email Account.** Configure an official NDRMA / Kenya Red Cross outgoing
   Email Account in the site (with SPF/DKIM), not a personal Gmail — welcome,
   set-password and approval emails all depend on it. Optionally point
   *Anticipatory Action Settings → AA email sender* at it for branded From.
2. **Timezone = `Africa/Nairobi`.** Set the site `time_zone` to `Africa/Nairobi`.
   Daily status flips and all "today" comparisons use the site date; on a UTC site
   they fire hours off local time (see `api/scheduling.py`).
3. **wkhtmltopdf with patched Qt.** The approval PDF is rendered server-side; install
   a patched-Qt wkhtmltopdf build or PDF-attachment emails fail.
4. **Turn the test environment OFF.** *Anticipatory Action Settings → testing enabled*
   must be off in production; the test form/dashboard are otherwise reachable while
   it is on.
5. **PowerBI / reporting feed auth.** `get_anticipatory_action_data` / `get_test_data`
   require an AA reviewer role — provision a dedicated service user with an AA role and
   authenticate the PowerBI connection with its API key. `allow_guest=False` alone is not
   an authorisation control.
6. **Subdomain routing** is hardcoded in the portal email links — confirm the public
   base URL is correct for the deployment.

## Contributing

This app uses `pre-commit` for formatting and linting (ruff, eslint, prettier, pyupgrade):

```bash
cd apps/anticipatory_action
pre-commit install
```

## CI & tests

- **Linters** run [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and
  [pip-audit](https://pypi.org/project/pip-audit/) on pull requests.
- The doctype `test_*.py` files are currently empty scaffolds — there is **no**
  meaningful automated test coverage yet. The highest-value suites to add first are
  multi-tenant isolation (`reviewer_owner_scope` / `aa_query_conditions`), the portal
  authorization boundary (`require_aa_access` / `_require_admin` / `_require_approver`),
  guest-submission validation, and the submission approval state machine.

## License

MIT
