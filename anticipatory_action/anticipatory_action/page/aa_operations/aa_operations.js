// AA Operations Console.
// A clean, light SaaS-style operations dashboard for Kenya's national
// Anticipatory Action programme (National Disaster Operations Centre · TWG).
// Layout: a full-height grouped left sidebar with a brand badge, a white top
// bar (back link, refresh, alerts bell, role chip, dark primary action,
// avatar), divider-style KPI metrics, search/filter toolbars and card grids.
//
// Sections behind the sidebar: Overview / Activations / Events / Reports /
// Members, plus admin-only Messages and Users. Every panel reads live data
// from whitelisted endpoints; rows route into the standard Frappe forms so the
// console stays a cockpit, not a re-implementation.

frappe.pages["aa-operations"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AA Operations Console"),
		single_column: true,
	});
	frappe.aa_operations = new AAOperations(page, wrapper);
};

const API = "anticipatory_action.anticipatory_action.page.aa_operations.aa_operations";

const AA_ICONS = {
	overview: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
	activations: '<path d="M13 2L3 14h7l-1 8 10-12h-7z"/>',
	events: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/>',
	reports: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>',
	members: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
	messages: '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><polyline points="22 6 12 13 2 6"/>',
	users: '<path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z"/>',
	plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
	arrow: '<line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/>',
	ext: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
	refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
	people: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>',
	pin: '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
	clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/>',
	back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
	bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
	search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
	mail: '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><polyline points="22 6 12 13 2 6"/>',
	globe: '<circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z"/>',
};
function aaIcon(name, sw) {
	return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw || 1.9}" stroke-linecap="round" stroke-linejoin="round">${AA_ICONS[name] || ""}</svg>`;
}
function aaNum(n) {
	return (Number(n) || 0).toLocaleString("en-US");
}
function aaMoney(n) {
	const v = Number(n) || 0;
	if (v >= 1e9) return (v / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
	if (v >= 1e6) return (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
	if (v >= 1e3) return (v / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
	return String(v);
}
function aaEsc(s) {
	return frappe.utils.escape_html(s == null ? "" : String(s));
}
function aaDate(d) {
	if (!d) return "—";
	const dt = frappe.datetime.str_to_obj(d);
	if (!dt || isNaN(dt)) return aaEsc(d);
	return dt
		.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
		.toUpperCase();
}
function aaInitials(name) {
	const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
	const a = (parts[0] || "?")[0];
	const b = parts.length > 1 ? parts[parts.length - 1][0] : "";
	return (a + b).toUpperCase();
}
const AA_AVATARS = [
	["#E7EEFB", "#2C6BD6"],
	["#E5F6EE", "#2E9E5B"],
	["#FBEFE2", "#C77B27"],
	["#F0EAFB", "#7A53C4"],
	["#FCE9EC", "#D6455A"],
	["#E2F3F5", "#1C8FA3"],
];
function aaAvatar(seed) {
	let h = 0;
	for (let i = 0; i < String(seed).length; i++) h = (h * 31 + String(seed).charCodeAt(i)) >>> 0;
	return AA_AVATARS[h % AA_AVATARS.length];
}
// Maps a free-text status to one of the console's semantic tones.
function aaTone(status) {
	const s = (status || "").toLowerCase();
	if (/(not appro|reject|declin|cancel|fail)/.test(s)) return "alert";
	if (/(approv|complete|done|deliver|closed)/.test(s)) return "ok";
	if (/(pending|review|await|progress|ongoing|new|planned)/.test(s)) return "warn";
	return "muted";
}

class AAOperations {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.filters = { status: "", hazard: "", county: "" };
		this.section = localStorage.getItem("aa_ops_section") || "overview";
		this.ensure_fonts();
		$(wrapper).find(".page-head").hide();
		this.page.main.css({ padding: "0", background: "#F4F6F9" });
		this.fill_page();
		this.is_admin =
			frappe.user.has_role("Anticipatory Action Admin") ||
			frappe.user.has_role("System Manager");
		this._shown = false;
		this.render_shell();
		this.go(this.section);

		$(wrapper).on("show", () => {
			if (!this._shown) {
				this._shown = true;
				return;
			}
			this.refresh();
		});
	}

	ensure_fonts() {
		if (document.getElementById("aa-ops-fonts")) return;
		const l = document.createElement("link");
		l.id = "aa-ops-fonts";
		l.rel = "stylesheet";
		l.href =
			"https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700;800;900&family=Barlow:wght@300;400;500;600;700&display=swap";
		document.head.appendChild(l);
	}

	fill_page() {
		// Break out of the desk's centred, max-width page container so the
		// console fills the full content area edge-to-edge.
		const $w = $(this.wrapper);
		$w.closest(".page-body, .main-section, .layout-main-section-wrapper").css({ padding: "0" });
		$w.parents(".container").css({ "max-width": "100%", "padding-left": "0", "padding-right": "0" });
		$w.find(".layout-main-section, .page-content").css({ padding: "0", margin: "0" });
		$w.find(".layout-main-section-wrapper").css({ "margin-bottom": "0" });
	}

	role_label() {
		if (frappe.user.has_role("Anticipatory Action Admin")) return "AA Admin";
		if (frappe.user.has_role("System Manager")) return "System Manager";
		if (frappe.user.has_role("Anticipatory Action User")) return "AA User";
		return "Operations";
	}

	nav_groups() {
		const groups = [
			{
				label: "Operations",
				items: [
					{ key: "overview", label: "Overview", icon: "overview" },
					{ key: "activations", label: "Activations", icon: "activations" },
					{ key: "events", label: "Events", icon: "events" },
					{ key: "reports", label: "Reports", icon: "reports" },
					{ key: "members", label: "Members", icon: "members" },
				],
			},
		];
		if (this.is_admin) {
			groups.push({
				label: "Administration",
				items: [
					{ key: "messages", label: "Messages", icon: "messages" },
					{ key: "users", label: "Users", icon: "users" },
				],
			});
		}
		return groups;
	}

	render_shell() {
		const info = frappe.user_info(frappe.session.user) || {};
		const fullname = info.fullname || frappe.session.user_fullname || frappe.session.user || "";
		const initials = aaInitials(fullname);

		const nav = this.nav_groups()
			.map(
				(g) =>
					`<div class="aa-nav-group">${aaEsc(g.label)}</div>` +
					g.items
						.map(
							(n) => `
				<button class="aa-nav-item" data-nav="${n.key}">
				  <span class="aa-nav-ico">${aaIcon(n.icon)}</span>
				  <span class="aa-nav-lbl">${aaEsc(n.label)}</span>
				  <span class="aa-nav-flag" data-flag="${n.key}"></span>
				</button>`
						)
						.join("")
			)
			.join("");

		const html = `
		<div class="aa-ops"><div class="aa-app">
		  <aside class="aa-side">
		    <div class="aa-brand">
		      <span class="aa-brand-badge">NDOC</span>
		      <span class="aa-brand-name">AA Ops<small>Operations Console</small></span>
		    </div>
		    <nav class="aa-nav">${nav}</nav>
		    <div class="aa-side-foot">
		      <button class="aa-nav-item" data-act="site">
		        <span class="aa-nav-ico">${aaIcon("globe")}</span>
		        <span class="aa-nav-lbl">Public Website</span>
		      </button>
		      <div class="aa-side-user">
		        <span class="aa-avatar">${aaEsc(initials)}</span>
		        <div class="aa-side-user-txt"><b>${aaEsc(fullname)}</b><small>${this.role_label()}</small></div>
		      </div>
		    </div>
		  </aside>

		  <div class="aa-content">
		    <header class="aa-topbar">
		      <button class="aa-back" data-act="home">${aaIcon("back")} Anticipatory Action</button>
		      <div class="aa-topbar-r">
		        <button class="aa-icon-btn" data-act="refresh" title="Refresh">${aaIcon("refresh")}</button>
		        <button class="aa-icon-btn aa-bell" data-act="alerts" title="Alerts">${aaIcon("bell")}<span class="aa-bell-dot" data-flag="bell"></span></button>
		        <span class="aa-role-chip">${this.role_label()}</span>
		        <button class="aa-btn aa-btn-primary" data-act="new">${aaIcon("plus", 2.2)} New Activation</button>
		        <span class="aa-avatar aa-avatar-sm">${aaEsc(initials)}</span>
		      </div>
		    </header>
		    <main class="aa-page" id="aaMain"></main>
		  </div>
		</div></div>`;

		this.page.main.html(html);
		this.$main = this.page.main.find("#aaMain");

		this.page.main.find('[data-act="new"]').on("click", () => frappe.new_doc("Anticipatory Action"));
		this.page.main.find('[data-act="site"]').on("click", () => window.open("/aa", "_blank"));
		this.page.main.find('[data-act="home"]').on("click", () => frappe.set_route("apps"));
		this.page.main.find('[data-act="refresh"]').on("click", () => this.refresh());
		this.page.main.find('[data-act="alerts"]').on("click", () => this.go(this.is_admin ? "messages" : "activations"));
		this.page.main.find("[data-nav]").on("click", (e) => this.go($(e.currentTarget).data("nav")));
	}

	set_active_nav() {
		this.page.main.find(".aa-nav-item").removeClass("is-active");
		this.page.main.find(`[data-nav="${this.section}"]`).addClass("is-active");
	}

	go(section) {
		this.section = section;
		localStorage.setItem("aa_ops_section", section);
		this.set_active_nav();
		this.$main.html(this.skeleton());
		const render = {
			overview: this.render_overview,
			activations: this.render_activations,
			events: this.render_events,
			reports: this.render_reports,
			members: this.render_members,
			messages: this.render_messages,
			users: this.render_users,
		}[section];
		(render || this.render_overview).call(this);
		this.load_summary();
	}

	refresh() {
		this.go(this.section);
	}

	// ---- data + chrome helpers ---------------------------------------
	call(method, args) {
		return new Promise((resolve) => {
			frappe
				.call({ method: `${API}.${method}`, args: args || {} })
				.then((r) => resolve((r && r.message) || null));
		});
	}

	load_summary() {
		this.call("get_summary").then((d) => {
			if (!d) return;
			this.summary = d;
			this.paint_flags();
		});
	}

	paint_flags() {
		const d = this.summary || {};
		const flags = { activations: Number(d.activations_pending || 0), messages: Number(d.messages_new || 0) };
		Object.keys(flags).forEach((k) => {
			const $f = this.page.main.find(`[data-flag="${k}"]`);
			if (flags[k] > 0) $f.text(aaNum(flags[k])).addClass("on");
			else $f.text("").removeClass("on");
		});
		const total = flags.activations + flags.messages;
		const $bell = this.page.main.find('[data-flag="bell"]');
		if (total > 0) $bell.addClass("on"); else $bell.removeClass("on");
	}

	skeleton() {
		const cards = new Array(4)
			.fill('<div class="aa-kpi"><div class="aa-kpi-num aa-skel">000</div><div class="aa-kpi-lbl">&nbsp;</div></div>')
			.join("");
		return `<div class="aa-pagehead aa-skel" style="height:46px"></div><div class="aa-kpis">${cards}</div><div class="aa-panel aa-skel" style="height:280px;margin-top:24px"></div>`;
	}

	// Page header: title, subtitle and optional status pills (right aligned).
	pagehead(title, sub, pills) {
		return `<div class="aa-pagehead">
			<div class="aa-pagehead-l">
				<h1 class="aa-page-title">${aaEsc(title)}</h1>
				${sub ? `<div class="aa-page-sub">${sub}</div>` : ""}
			</div>
			${pills ? `<div class="aa-pagehead-r">${pills}</div>` : ""}
		</div>`;
	}

	head(title, note) {
		return `<div class="aa-sec-head"><h2 class="aa-sec-title">${aaEsc(title)}</h2>${
			note ? `<span class="aa-sec-note">${aaEsc(note)}</span>` : ""
		}</div>`;
	}

	empty(msg) {
		return `<div class="aa-empty">${aaEsc(msg)}</div>`;
	}

	pill(label, tone) {
		return `<span class="aa-pill is-${tone || "muted"}"><i></i>${aaEsc(label)}</span>`;
	}

	// A search box that filters an in-memory list and repaints a container.
	searchbox(ph) {
		return `<div class="aa-search">${aaIcon("search")}<input type="text" placeholder="${aaEsc(ph || "Search")}" data-search></div>`;
	}

	// ============ OVERVIEW ============================================
	render_overview() {
		Promise.all([this.call("get_summary"), this.call("get_situation")]).then(([d, sit]) => {
			this.summary = d || {};
			this.paint_flags();
			d = this.summary;
			sit = sit || [];

			const now = new Date();
			const date = now.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
			const time = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
			const info = frappe.user_info(frappe.session.user) || {};
			const first = ((info.fullname || "there").split(" ")[0] || "there").trim();
			const sub = `Karibu, <b>${aaEsc(first)}</b> &nbsp;·&nbsp; ${date} &nbsp;·&nbsp; AS OF <b>${time}</b> EAT`;
			const pills =
				this.pill(`${aaNum(d.activations_approved)} active`, "ok") +
				(d.activations_pending > 0 ? this.pill(`${aaNum(d.activations_pending)} pending`, "warn") : "");

			const kpis = [
				{ v: aaNum(d.activations_total), l: "Activations" },
				{ v: aaNum(d.activations_pending), l: "Pending Review", alert: d.activations_pending > 0 },
				{ v: aaNum(d.counties_active), l: "Counties Active" },
				{ v: aaNum(d.people_reached), l: "People Targeted" },
				{ v: aaMoney(d.funds_kes), l: "Funds (KES)", pre: "KSh " },
				{ v: aaNum(d.organizations), l: "Member Orgs" },
			]
				.map(
					(k) => `<div class="aa-kpi ${k.alert ? "is-alert" : ""}">
					<div class="aa-kpi-num">${k.pre ? `<span class="pre">${k.pre}</span>` : ""}${k.v}</div>
					<div class="aa-kpi-lbl">${k.l}</div></div>`
				)
				.join("");

			let callouts = "";
			if (d.is_admin && (d.activations_pending > 0 || d.messages_new > 0)) {
				const c = [];
				if (d.activations_pending > 0)
					c.push(
						`<button class="aa-callout" data-co="approvals">${aaIcon("activations")}<div><b>${aaNum(
							d.activations_pending
						)}</b> activation${d.activations_pending > 1 ? "s" : ""} awaiting review</div>${aaIcon("arrow")}</button>`
					);
				if (d.messages_new > 0)
					c.push(
						`<button class="aa-callout" data-co="messages">${aaIcon("messages")}<div><b>${aaNum(
							d.messages_new
						)}</b> new contact message${d.messages_new > 1 ? "s" : ""}</div>${aaIcon("arrow")}</button>`
					);
				callouts = `<div class="aa-callouts">${c.join("")}</div>`;
			}

			const hz = (d.hazards || []).filter((h) => h.activations > 0);
			const hzMax = Math.max(1, ...hz.map((h) => h.activations));
			const hazardRows = hz.length
				? hz
						.map(
							(h) => `<div class="aa-bar-row">
						<div class="aa-bar-lbl">${aaEsc(h.hazard)}</div>
						<div class="aa-bar-track"><div class="aa-bar-fill" style="width:${Math.round((h.activations / hzMax) * 100)}%"></div></div>
						<div class="aa-bar-val">${aaNum(h.activations)} <span>· ${aaNum(h.people)} ppl</span></div>
					</div>`
						)
						.join("")
				: this.empty("No approved activations yet");

			const sitRows = sit.length
				? sit
						.slice(0, 14)
						.map((c) => {
							const tags = c.hazards.map((h) => `<span class="aa-tag">${aaEsc(h)}</span>`).join("");
							const tone = c.level === "Complete" ? "ok" : c.level === "Ongoing" ? "warn" : "muted";
							return `<div class="aa-sit-row">
							<div class="aa-sit-geo">${aaIcon("pin")}<span>${aaEsc(c.county)}</span></div>
							<div class="aa-sit-tags">${tags}</div>
							<div class="aa-sit-num">${aaNum(c.people)}<span>people</span></div>
							<div class="aa-sit-num">${aaNum(c.activations)}<span>activations</span></div>
							<div class="aa-sit-stat">${this.pill(c.level, tone)}</div>
						</div>`;
						})
						.join("")
				: this.empty("No county-level activity recorded yet");

			const recent = (d.recent || []).length
				? d.recent
						.map(
							(r) => `<div class="aa-line" data-name="${aaEsc(r.name)}" tabindex="0" role="button">
						<div><div class="aa-line-t">${aaEsc(r.implementing_organization || r.name)}</div>
						<div class="aa-line-s"><span class="id">${aaEsc(r.name)}</span> · ${aaEsc(r.anticipated_hazard || "Unspecified hazard")}</div></div>
						${this.pill(r.status || "Pending", aaTone(r.status))}</div>`
						)
						.join("")
				: this.empty("No activation reports yet");

			const html = `
			${this.pagehead("Overview", sub, pills)}
			<div class="aa-kpis">${kpis}</div>
			${callouts}
			<div class="aa-grid-2">
			  <section class="aa-panel">
			    ${this.head("County Situation", "Derived from approved activations")}
			    <div class="aa-sit">${sitRows}</div>
			  </section>
			  <section class="aa-panel">
			    ${this.head("Hazard Outlook", "Approved activations by hazard")}
			    <div class="aa-bars">${hazardRows}</div>
			    <div class="aa-sub-head">${this.head("Recent Activations", "Latest submissions")}</div>
			    <div class="aa-lines">${recent}</div>
			  </section>
			</div>`;

			this.$main.html(html);
			this.$main.find("[data-co='approvals']").on("click", () => {
				this.filters = { status: "Pending", hazard: "", county: "" };
				this.go("activations");
			});
			this.$main.find("[data-co='messages']").on("click", () => this.go("messages"));
			this.$main.find(".aa-line").on("click", (e) =>
				frappe.set_route("Form", "Anticipatory Action", $(e.currentTarget).data("name"))
			);
		});
	}

	// ============ ACTIVATIONS =========================================
	render_activations() {
		const f = this.filters;
		this.call("get_activations", f).then((rows) => {
			rows = rows || [];
			const hazards = ["", "Drought", "Floods", "Conflict", "Pest / Parasite Infection", "Disease Outbreak", "Civil disorders", "Landslides / Earth movements", "Other"];
			const statuses = ["", "Pending", "Approved", "Not Approved"];
			const opt = (arr, sel) =>
				arr.map((v) => `<option value="${aaEsc(v)}" ${v === sel ? "selected" : ""}>${aaEsc(v || "All")}</option>`).join("");

			const row = (r) => `<tr data-name="${aaEsc(r.name)}" tabindex="0" role="button">
				<td class="mono">${aaEsc(r.name)}</td>
				<td class="strong">${aaEsc(r.organization || "—")}${r.counties ? `<div class="sub">${aaEsc(r.counties)}</div>` : ""}</td>
				<td>${aaEsc(r.hazard || "—")}</td>
				<td class="r">${aaNum(r.people)}</td>
				<td class="r">${r.funds ? "KSh " + aaMoney(r.funds) : "—"}</td>
				<td>${aaDate(r.start_date)}</td>
				<td>${this.pill(r.status || "Pending", aaTone(r.status))}</td>
			</tr>`;

			const toolbar = `<div class="aa-toolbar">
				${this.searchbox("Search implementer, county, ref…")}
				<div class="aa-toolbar-controls">
					<label class="aa-field">Status<select data-f="status">${opt(statuses, f.status)}</select></label>
					<label class="aa-field">Hazard<select data-f="hazard">${opt(hazards, f.hazard)}</select></label>
					${f.status || f.hazard || f.county ? '<button class="aa-clear" data-clear="1">Clear</button>' : ""}
				</div>
			</div>`;

			const tableShell = `<div class="aa-table-wrap"><table class="aa-table">
				<thead><tr><th>Ref</th><th>Implementer / Counties</th><th>Hazard</th>
				<th class="r">People</th><th class="r">Funds</th><th>Activated</th><th>Status</th></tr></thead>
				<tbody data-list></tbody></table></div>`;

			this.$main.html(
				this.pagehead("Activations", "Activation register · click a row to open the report") +
					toolbar +
					(rows.length ? tableShell : this.empty("No activations match the current filters"))
			);

			const $body = this.$main.find("[data-list]");
			const paint = (q) => {
				q = (q || "").toLowerCase();
				const list = q
					? rows.filter((r) =>
							[r.name, r.organization, r.counties, r.hazard, r.status].some((v) => String(v || "").toLowerCase().includes(q))
					  )
					: rows;
				$body.html(list.length ? list.map(row).join("") : `<tr><td colspan="7" class="aa-td-empty">No matches</td></tr>`);
				$body.find("tr[data-name]").on("click", (e) =>
					frappe.set_route("Form", "Anticipatory Action", $(e.currentTarget).data("name"))
				);
			};
			if (rows.length) paint("");

			this.$main.find("select[data-f]").on("change", (e) => {
				const $s = $(e.currentTarget);
				this.filters[$s.data("f")] = $s.val();
				this.render_activations();
			});
			this.$main.find("[data-clear]").on("click", () => {
				this.filters = { status: "", hazard: "", county: "" };
				this.render_activations();
			});
			this.$main.find("[data-search]").on("input", (e) => paint($(e.currentTarget).val()));
		});
	}

	// ============ EVENTS ==============================================
	render_events() {
		this.call("get_events").then((d) => {
			d = d || { upcoming: [], past: [] };
			const card = (r, upcoming) => {
				const dt = r.date ? frappe.datetime.str_to_obj(r.date) : null;
				const day = dt ? dt.toLocaleDateString("en-GB", { day: "2-digit" }) : "--";
				const mon = dt ? dt.toLocaleDateString("en-GB", { month: "short" }).toUpperCase() : "—";
				const yr = dt ? dt.getFullYear() : "";
				return `<div class="aa-event ${upcoming ? "is-up" : ""}">
					<div class="aa-event-date"><span class="d">${day}</span><span class="m">${mon}</span><span class="y">${yr}</span></div>
					<div class="aa-event-body">
					  <div class="aa-event-top">
					    ${r.pillar ? `<span class="aa-tag">${aaEsc(r.pillar)}</span>` : ""}
					    ${r.status ? this.pill(r.status, aaTone(r.status)) : ""}
					  </div>
					  <div class="aa-event-act">${aaEsc(r.activity || "Untitled activity")}</div>
					  ${r.milestone ? `<div class="aa-event-ms">${aaIcon("clock")} ${aaEsc(r.milestone)}</div>` : ""}
					  ${r.activity_reference ? `<div class="aa-event-ref">Ref: ${aaEsc(r.activity_reference)}</div>` : ""}
					</div>
				</div>`;
			};

			const up = d.upcoming.length ? d.upcoming.map((r) => card(r, true)).join("") : this.empty("No upcoming events scheduled");
			const past = d.past.length ? d.past.map((r) => card(r, false)).join("") : this.empty("No past events on record");

			this.$main.html(`
				${this.pagehead("Events", "TWG activity calendar")}
				<button class="aa-mini-act" data-manage="Anticipatory Activities">Manage events ${aaIcon("ext")}</button>
				<div class="aa-sub-head">${this.head("Upcoming", `${d.upcoming.length} scheduled`)}</div>
				<div class="aa-events">${up}</div>
				<div class="aa-sub-head">${this.head("Past", `${d.past.length} on record`)}</div>
				<div class="aa-events aa-events-past">${past}</div>
			`);
			this.$main.find("[data-manage]").on("click", (e) => frappe.set_route("List", $(e.currentTarget).data("manage")));
		});
	}

	// ============ REPORTS =============================================
	render_reports() {
		this.call("get_reports").then((rows) => {
			rows = rows || [];
			const cats = ["", ...Array.from(new Set(rows.map((r) => r.category).filter(Boolean)))];
			const years = ["", ...Array.from(new Set(rows.map((r) => r.year).filter(Boolean))).sort((a, b) => b - a)];
			this._rfilter = this._rfilter || { category: "", year: "" };
			const f = this._rfilter;
			const opt = (arr, sel) =>
				arr.map((v) => `<option value="${aaEsc(v)}" ${String(v) === String(sel) ? "selected" : ""}>${aaEsc(v || "All")}</option>`).join("");

			const card = (r) => {
				const [bg, fg] = aaAvatar(r.category || r.title);
				const meta = [r.source, r.year ? (r.month ? `${r.month} ${r.year}` : r.year) : null].filter(Boolean).map(aaEsc).join(" · ");
				const open = r.url
					? `<a class="aa-btn-soft" href="${aaEsc(r.url)}" target="_blank" rel="noopener">Open ${aaIcon("ext")}</a>`
					: `<span class="aa-btn-soft is-off">No link</span>`;
				return `<div class="aa-card">
					<div class="aa-card-head">
						<span class="aa-doc" style="background:${bg};color:${fg}">${aaIcon("reports")}</span>
						<span class="aa-chip">${aaEsc(r.category)}</span>
					</div>
					<div class="aa-card-title">${aaEsc(r.title)}</div>
					${r.description ? `<div class="aa-card-desc">${aaEsc(r.description)}</div>` : ""}
					<div class="aa-card-foot">${meta ? `<span class="aa-card-meta">${meta}</span>` : "<span></span>"}${open}</div>
				</div>`;
			};

			this.$main.html(`
				${this.pagehead("Reports", "Reports & publications library")}
				<div class="aa-toolbar">
					${this.searchbox("Search title, source, keyword…")}
					<div class="aa-toolbar-controls">
						<label class="aa-field">Category<select data-rf="category">${opt(cats, f.category)}</select></label>
						<label class="aa-field">Year<select data-rf="year">${opt(years, f.year)}</select></label>
						${f.category || f.year ? '<button class="aa-clear" data-rclear="1">Clear</button>' : ""}
					</div>
				</div>
				<div class="aa-cards" data-list></div>
			`);

			const $list = this.$main.find("[data-list]");
			const paint = (q) => {
				q = (q || "").toLowerCase();
				const list = rows.filter(
					(r) =>
						(!f.category || r.category === f.category) &&
						(!f.year || String(r.year) === String(f.year)) &&
						(!q || [r.title, r.source, r.keywords, r.description].some((v) => String(v || "").toLowerCase().includes(q)))
				);
				$list.html(list.length ? list.map(card).join("") : this.empty("No reports or publications match"));
			};
			paint("");

			this.$main.find("select[data-rf]").on("change", (e) => {
				const $s = $(e.currentTarget);
				this._rfilter[$s.data("rf")] = $s.val();
				this.render_reports();
			});
			this.$main.find("[data-rclear]").on("click", () => {
				this._rfilter = { category: "", year: "" };
				this.render_reports();
			});
			this.$main.find("[data-search]").on("input", (e) => paint($(e.currentTarget).val()));
		});
	}

	// ============ MEMBERS =============================================
	render_members() {
		frappe.db
			.get_list("Anticipatory Action Organization", {
				fields: [
					"name",
					"name_of_organization",
					"type_of_organization",
					"primary_contact_person_name",
					"primary_email_contact",
					"organization_website",
				],
				order_by: "name_of_organization asc",
				limit: 0,
			})
			.then((rows) => {
				rows = rows || [];
				const card = (r) => {
					const nm = r.name_of_organization || r.name;
					const [bg, fg] = aaAvatar(nm);
					return `<div class="aa-card" data-name="${aaEsc(r.name)}" tabindex="0" role="button">
						<div class="aa-card-head">
							<span class="aa-avatar aa-avatar-lg" style="background:${bg};color:${fg}">${aaEsc(aaInitials(nm))}</span>
							${r.type_of_organization ? `<span class="aa-chip">${aaEsc(r.type_of_organization)}</span>` : ""}
						</div>
						<div class="aa-card-title">${aaEsc(nm)}</div>
						${r.primary_contact_person_name ? `<div class="aa-card-desc">${aaIcon("people")} ${aaEsc(r.primary_contact_person_name)}</div>` : ""}
						${r.primary_email_contact ? `<div class="aa-card-desc">${aaIcon("mail")} ${aaEsc(r.primary_email_contact)}</div>` : ""}
						<div class="aa-card-foot">
							<span></span>
							${r.organization_website ? `<a class="aa-btn-soft" href="${aaEsc(r.organization_website)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Visit ${aaIcon("ext")}</a>` : "<span></span>"}
						</div>
					</div>`;
				};

				this.$main.html(`
					${this.pagehead("Members", "TWG partner organisations")}
					<div class="aa-toolbar">
						${this.searchbox("Search organisation, type, contact…")}
						<button class="aa-mini-act" data-manage="Anticipatory Action Organization" style="margin:0">Manage ${aaIcon("ext")}</button>
					</div>
					<div class="aa-cards" data-list></div>
				`);

				const $list = this.$main.find("[data-list]");
				const paint = (q) => {
					q = (q || "").toLowerCase();
					const list = q
						? rows.filter((r) =>
								[r.name_of_organization, r.type_of_organization, r.primary_contact_person_name, r.primary_email_contact].some((v) =>
									String(v || "").toLowerCase().includes(q)
								)
						  )
						: rows;
					$list.html(list.length ? list.map(card).join("") : this.empty("No member organisations match"));
					$list.find(".aa-card[data-name]").on("click", (e) =>
						frappe.set_route("Form", "Anticipatory Action Organization", $(e.currentTarget).data("name"))
					);
				};
				paint("");

				this.$main.find("[data-manage]").on("click", (e) => frappe.set_route("List", $(e.currentTarget).data("manage")));
				this.$main.find("[data-search]").on("input", (e) => paint($(e.currentTarget).val()));
			});
	}

	// ============ MESSAGES (admin) ====================================
	render_messages() {
		if (!this.is_admin) return this.go("overview");
		frappe.db
			.get_list("AA Contact Message", {
				fields: ["name", "full_name", "organization", "subject", "status", "submitted_on", "email"],
				order_by: "submitted_on desc",
				limit: 100,
			})
			.then((rows) => {
				rows = rows || [];
				const body = rows
					.map(
						(r) => `<tr data-name="${aaEsc(r.name)}" tabindex="0" role="button">
					<td class="strong">${aaEsc(r.full_name || "—")}${r.organization ? `<div class="sub">${aaEsc(r.organization)}</div>` : ""}</td>
					<td>${aaEsc(r.subject || "—")}</td>
					<td>${aaEsc(r.email || "")}</td>
					<td>${aaDate(r.submitted_on)}</td>
					<td>${this.pill(r.status || "New", r.status === "New" ? "alert" : aaTone(r.status))}</td>
				</tr>`
					)
					.join("");
				const table = rows.length
					? `<div class="aa-table-wrap"><table class="aa-table">
						<thead><tr><th>From</th><th>Subject</th><th>Email</th><th>Received</th><th>Status</th></tr></thead>
						<tbody>${body}</tbody></table></div>`
					: this.empty("No contact messages received");
				this.$main.html(this.pagehead("Messages", "Enquiries from the public website") + table);
				this.$main.find("tr[data-name]").on("click", (e) =>
					frappe.set_route("Form", "AA Contact Message", $(e.currentTarget).data("name"))
				);
			});
	}

	// ============ USERS (admin) =======================================
	render_users() {
		if (!this.is_admin) return this.go("overview");
		frappe.db
			.get_list("Anticipatory Action User", {
				fields: ["name", "full_name", "first_name", "last_name", "email", "phone", "organization", "role"],
				order_by: "full_name asc",
				limit: 0,
			})
			.then((rows) => {
				rows = rows || [];
				const nameOf = (r) => r.full_name || [r.first_name, r.last_name].filter(Boolean).join(" ") || r.name;
				const body = rows
					.map((r) => {
						const [bg, fg] = aaAvatar(nameOf(r));
						return `<tr data-name="${aaEsc(r.name)}" tabindex="0" role="button">
					<td class="strong"><span class="aa-avatar aa-avatar-row" style="background:${bg};color:${fg}">${aaEsc(aaInitials(nameOf(r)))}</span>${aaEsc(nameOf(r))}</td>
					<td>${aaEsc(r.email || "—")}</td>
					<td>${aaEsc(r.phone || "—")}</td>
					<td>${aaEsc(r.organization || "—")}</td>
					<td>${this.pill(r.role === "Anticipatory Action Admin" ? "Admin" : "User", r.role === "Anticipatory Action Admin" ? "ok" : "muted")}</td>
				</tr>`;
					})
					.join("");
				const table = rows.length
					? `<div class="aa-table-wrap"><table class="aa-table">
						<thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Organisation</th><th>Role</th></tr></thead>
						<tbody>${body}</tbody></table></div>`
					: this.empty("No AA users registered");
				this.$main.html(
					this.pagehead("Users", "Console accounts") +
						`<button class="aa-mini-act" data-manage="Anticipatory Action User">Manage users ${aaIcon("ext")}</button>` +
						table
				);
				this.$main.find("[data-manage]").on("click", (e) => frappe.set_route("List", $(e.currentTarget).data("manage")));
				this.$main.find("tr[data-name]").on("click", (e) =>
					frappe.set_route("Form", "Anticipatory Action User", $(e.currentTarget).data("name"))
				);
			});
	}
}
