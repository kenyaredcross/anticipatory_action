// ── Web Form Client Script — Anticipatory Action ─────────────────────────────
// Replaces Frappe's default child-table grid UI with custom modal dialogs
// and rich row summary cards.

frappe.web_form.after_load = () => {
	// Set up link-field queries for county / sub_county inside child tables
	frappe.web_form.fields.forEach(df => {
		if (df.fieldtype !== 'Table') return;
		const table = frappe.web_form.fields_dict[df.fieldname];
		if (!table || !table.grid || !table.grid.fields_map) return;
		Object.keys(table.grid.fields_map).forEach(fn => {
			const cdf = table.grid.fields_map[fn];
			if (['county', 'sub_county'].includes(cdf.fieldname)) {
				cdf.get_query = () => ({
					query: 'anticipatory_action.api.search_link.search_link_fields'
				});
			}
		});
	});

	renderFormHeader();
	setTimeout(initializeAllChildTables, 400);
};

// ── FORM HEADER (logos + title) ───────────────────────────────────────────────

function renderFormHeader() {
	if ($('.aa-form-header').length) return;

	const header = $(`
		<div class="aa-form-header">
			<img src="/NDOC.png" alt="NDOC" class="aa-form-logo" />
			<div class="aa-form-header-center">
				<div class="aa-form-header-title">Kenya Anticipatory Action</div>
				<div class="aa-form-header-sub">Data Collection &amp; Monitoring Platform &middot; 2024&ndash;2029</div>
			</div>
			<img src="/assets/anticipatory_action/KRCS%2060.png" alt="Kenya Red Cross Society" class="aa-form-logo" />
		</div>
	`);

	// Prepend inside the web-form container (before the title / intro text)
	const $target = $('.web-form-container').first();
	if ($target.length) {
		$target.prepend(header);
	} else {
		// Fallback for different Frappe versions
		$('.page-content > .container, main > .container').first().prepend(header);
	}
}

// ── HELPERS ──────────────────────────────────────────────────────────────────

function evaluateExpression(expr, doc) {
	if (!expr) return false;
	try {
		let e = expr.trim();
		if (e.startsWith('eval:')) e = e.slice(5).trim();
		return new Function('doc', `with(doc){try{return ${e}}catch(e){return false}}`)(doc);
	} catch (_) { return false; }
}

function isFieldHidden(field, doc) {
	if (field.hidden) return true;
	if (field.depends_on) return !evaluateExpression(field.depends_on, doc);
	return false;
}

function isFieldRequired(field, doc) {
	if (field.reqd) return true;
	if (field.mandatory_depends_on) return evaluateExpression(field.mandatory_depends_on, doc);
	return false;
}

function fmtCurrency(val) {
	if (val == null || val === '') return '—';
	return 'KES\u00a0' + new Intl.NumberFormat('en-KE').format(val);
}

function fmtNumber(val) {
	if (!val && val !== 0) return null;
	return new Intl.NumberFormat('en-KE').format(val);
}

// ── INIT ALL TABLES ───────────────────────────────────────────────────────────

function initializeAllChildTables() {
	Object.keys(frappe.web_form.fields_dict).forEach(fn => {
		const f = frappe.web_form.fields_dict[fn];
		if (f && f.grid && f.grid.wrapper) {
			initializeChildTable(f);
		}
	});
}

// ── INIT ONE TABLE ────────────────────────────────────────────────────────────

function initializeChildTable(grid_field) {
	if (!grid_field || !grid_field.grid) return;

	// Collapse & render cards for any pre-existing rows
	if (grid_field.grid.grid_rows) {
		grid_field.grid.grid_rows.forEach(r => {
			if (r.doc && r.wrapper) {
				r.toggle_view(false);
				renderRowCard(r);
			}
		});
	}
	renderEmptyState(grid_field);

	// Override add_new_row to open custom modal instead of inline editor
	const orig = grid_field.grid.add_new_row.bind(grid_field.grid);
	grid_field.grid.add_new_row = function(idx, callback) {
		if (this.grid_rows) this.grid_rows.forEach(r => r.toggle_view(false));
		const new_row = orig(idx, callback, false);
		setTimeout(() => {
			const nr = this.grid_rows[this.grid_rows.length - 1];
			if (nr) openCustomDialog(nr, this.grid_rows.length, true, grid_field);
		}, 50);
		return new_row;
	};

	// Click an existing row to edit it
	$(grid_field.grid.wrapper).off('click.aa-grid').on('click.aa-grid', '.grid-row', function(e) {
		if ($(e.target).is('input[type="checkbox"]') ||
			$(e.target).closest('.grid-row-check, .aa-row-delete').length) return;
		const idx = $(this).index();
		const row = grid_field.grid.grid_rows[idx];
		if (row) openCustomDialog(row, idx + 1, false, grid_field);
	});

	// Delete row via trash button on card
	$(grid_field.grid.wrapper).on('click.aa-delete', '.aa-row-delete', function(e) {
		e.stopPropagation();
		const idx = $(this).closest('.grid-row').index();
		const row = grid_field.grid.grid_rows[idx];
		if (!row) return;
		frappe.confirm('Remove this entry?', () => {
			row.remove();
			setTimeout(() => renderEmptyState(grid_field), 80);
		});
	});

	// MutationObserver: keep cards rendered as Frappe re-renders rows
	const el = grid_field.grid.wrapper instanceof jQuery
		? grid_field.grid.wrapper[0]
		: grid_field.grid.wrapper;
	if (el && el instanceof Node) {
		new MutationObserver(() => {
			if (!grid_field.grid.grid_rows) return;
			grid_field.grid.grid_rows.forEach(r => {
				if (r.doc && r.wrapper && !$(r.wrapper).find('.aa-row-card').length) {
					r.toggle_view(false);
					renderRowCard(r);
				}
			});
			renderEmptyState(grid_field);
		}).observe(el, { childList: true, subtree: false });
	}
}

// ── EMPTY STATE ───────────────────────────────────────────────────────────────

function renderEmptyState(grid_field) {
	const $body = $(grid_field.grid.wrapper).find('.grid-body');
	$body.find('.aa-empty-state').remove();
	const hasRows = grid_field.grid.grid_rows && grid_field.grid.grid_rows.length > 0;
	if (!hasRows) {
		$body.append(`
			<div class="aa-empty-state">
				<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="3" y="3" width="18" height="18" rx="3"/>
					<line x1="12" y1="8" x2="12" y2="16"/>
					<line x1="8" y1="12" x2="16" y2="12"/>
				</svg>
				<h4>No entries yet</h4>
				<p>Click "Add Row" below to add an intervention detail.</p>
			</div>
		`);
	}
}

// ── ROW CARD ──────────────────────────────────────────────────────────────────

function renderRowCard(grid_row) {
	const doc = grid_row.doc || {};
	const county = doc.county || '—';
	const subcounty = doc.subcounty ? ` · ${doc.subcounty}` : '';
	const sector = doc.sector || '—';
	const amount = doc.amount_for_anticipatory_action_kes;
	const people = doc.number_of_people_targeted;
	const status = doc.status_of_the_early_action || 'Planned';
	const intervention = doc.describe_the_anticipatory_action_intervention || '';
	const truncated = intervention.length > 90
		? intervention.slice(0, 90) + '\u2026'
		: intervention;

	const statusClass = status === 'Complete' ? 'aa-status-complete'
		: status === 'Ongoing' ? 'aa-status-ongoing'
		: 'aa-status-planned';

	const metaHtml = [
		(amount != null && amount !== '')
			? `<div class="aa-meta-item">
					<span class="aa-meta-label">Budget</span>
					<span class="aa-meta-value">${fmtCurrency(amount)}</span>
				</div>` : '',
		people
			? `<div class="aa-meta-item">
					<span class="aa-meta-label">People</span>
					<span class="aa-meta-value">${fmtNumber(people)}</span>
				</div>` : ''
	].join('');

	$(grid_row.wrapper).find('.data-row').html(`
		<div class="aa-row-card">
			<div class="aa-row-main">
				<div class="aa-row-location">
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
						<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
						<circle cx="12" cy="10" r="3"/>
					</svg>
					<strong>${county}</strong>${subcounty}
				</div>
				<div class="aa-row-sector">${sector}</div>
				${truncated ? `<div class="aa-row-desc">${truncated}</div>` : ''}
			</div>
			<div class="aa-row-meta">
				${metaHtml}
				<span class="aa-status-badge ${statusClass}">${status}</span>
				<button class="aa-row-delete" title="Remove entry">
					<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<polyline points="3 6 5 6 21 6"/>
						<path d="M19 6l-1 14H6L5 6"/>
						<path d="M10 11v6M14 11v6"/>
						<path d="M9 6V4h6v2"/>
					</svg>
				</button>
			</div>
		</div>
	`);
}

// ── MODAL DIALOG ──────────────────────────────────────────────────────────────

function openCustomDialog(grid_row, row_number, is_new, grid_field) {
	const doc = grid_row.doc || {};
	const county = doc.county;
	const title = is_new
		? 'Add Intervention Detail'
		: (county ? `Edit: ${county}` : `Edit Entry #${row_number}`);

	const overlay = $('<div class="aa-modal-overlay"></div>');
	const modal = $(`
		<div class="aa-modal" role="dialog" aria-modal="true">
			<div class="aa-modal-header">
				<div class="aa-modal-title-wrap">
					<svg class="aa-modal-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
						<path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
					</svg>
					<h3 class="aa-modal-title">${title}</h3>
				</div>
				<button class="aa-modal-close" aria-label="Close">&times;</button>
			</div>
			<div class="aa-modal-body"></div>
			<div class="aa-modal-footer">
				<button class="aa-btn aa-btn-cancel">Cancel</button>
				<button class="aa-btn aa-btn-save">
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
						<polyline points="20 6 9 17 4 12"/>
					</svg>
					Save Entry
				</button>
			</div>
		</div>
	`);

	overlay.append(modal);
	$('body').append(overlay);
	// Trigger entrance animation
	setTimeout(() => overlay.addClass('aa-modal-visible'), 10);

	const fields = grid_row.grid.docfields || grid_row.grid.fields || [];
	const modalBody = modal.find('.aa-modal-body');
	// Working copy of the row's data for conditional logic
	const currentDoc = { ...doc };

	// ── Build form structure, respecting Section Break / Column Break ─────────

	let currentSectionEl = null;
	let currentColGroup = null;
	let inCol = false;

	fields.forEach(field => {
		if (field.fieldname === 'name') return;

		if (field.fieldtype === 'Section Break') {
			inCol = false;
			currentColGroup = null;
			const sec = $(`
				<div class="aa-section">
					${field.label ? `<div class="aa-section-title">${field.label}</div>` : '<div class="aa-section-divider"></div>'}
					<div class="aa-section-fields"></div>
				</div>
			`);
			modalBody.append(sec);
			currentSectionEl = sec.find('.aa-section-fields');
			return;
		}

		if (field.fieldtype === 'Column Break') {
			if (!inCol && currentSectionEl) {
				const cg = $('<div class="aa-col-group"></div>');
				const col1 = $('<div class="aa-col"></div>');
				const col2 = $('<div class="aa-col"></div>');
				// Move everything already in this section into column 1
				currentSectionEl.children().appendTo(col1);
				cg.append(col1).append(col2);
				currentSectionEl.append(cg);
				currentColGroup = col2;
				inCol = true;
			}
			return;
		}

		if (field.hidden) return;

		const container = (inCol && currentColGroup) ? currentColGroup
			: (currentSectionEl || modalBody);

		buildFieldWidget(field, container);
	});

	// ── Field state: visibility + required markers ────────────────────────────

	function updateFieldStates() {
		fields.forEach(field => {
			if (!field.fieldname || field.fieldname === 'name') return;
			const fw = modalBody.find(`[data-fieldname="${field.fieldname}"]`);
			if (!fw.length) return;

			const hidden = isFieldHidden(field, currentDoc);
			fw.toggle(!hidden);

			if (!hidden) {
				const inp = fw.find('input, textarea, select').first();
				const lbl = fw.find('.aa-field-label');
				const required = isFieldRequired(field, currentDoc);
				if (required) {
					inp.attr('required', true);
					if (!lbl.find('.aa-req').length) lbl.append('<span class="aa-req">*</span>');
				} else {
					inp.removeAttr('required');
					lbl.find('.aa-req').remove();
				}
			}
		});
	}

	// ── Widget builder ────────────────────────────────────────────────────────

	function buildFieldWidget(field, container) {
		const isCheck = field.fieldtype === 'Check';
		const fw = $(`<div class="aa-field${isCheck ? ' aa-field-check' : ''}" data-fieldname="${field.fieldname}"></div>`);
		const fieldValue = currentDoc[field.fieldname];

		if (isCheck) {
			const checked = fieldValue === 1 || fieldValue === true || fieldValue === '1';
			const inp = $(`<input type="checkbox" class="aa-checkbox">`).prop('checked', checked);
			const lbl = $(`<label class="aa-field-label aa-check-label">${field.label || ''}</label>`);
			inp.data('field', field).data('fieldname', field.fieldname);
			inp.on('change', function() {
				currentDoc[field.fieldname] = $(this).prop('checked') ? 1 : 0;
				updateFieldStates();
			});
			fw.append(inp).append(lbl);
		} else {
			if (field.description) {
				fw.append(`<p class="aa-field-desc">${field.description}</p>`);
			}
			fw.append(`<label class="aa-field-label">${field.label || ''}${field.reqd ? '<span class="aa-req">*</span>' : ''}</label>`);
			const inp = buildInput(field, fieldValue);
			inp.on('change input', function() {
				const f = $(this).data('field');
				const fn = $(this).data('fieldname');
				if (['Int', 'Float', 'Currency'].includes(f.fieldtype)) {
					const v = $(this).val();
					currentDoc[fn] = v !== '' ? parseFloat(v) || 0 : 0;
				} else {
					currentDoc[fn] = $(this).val();
				}
				updateFieldStates();
			});
			fw.append(inp);
			fw.append('<div class="aa-field-error"></div>');
		}

		container.append(fw);
	}

	function buildInput(field, fieldValue) {
		let inp;
		switch (field.fieldtype) {
			case 'Data':
			case 'Text':
				inp = $(`<input type="text" class="aa-input" placeholder="${field.label || ''}">`).val(fieldValue || '');
				break;
			case 'Small Text':
				inp = $(`<textarea class="aa-input aa-textarea" rows="3" placeholder="${field.label || ''}"></textarea>`).val(fieldValue || '');
				break;
			case 'Long Text':
				inp = $(`<textarea class="aa-input aa-textarea" rows="5" placeholder="${field.label || ''}"></textarea>`).val(fieldValue || '');
				break;
			case 'Int':
				inp = $(`<input type="number" step="1" class="aa-input">`);
				inp.val(fieldValue != null && fieldValue !== '' ? fieldValue : '');
				break;
			case 'Float':
			case 'Currency':
				inp = $(`<input type="number" step="any" class="aa-input">`);
				inp.val(fieldValue != null && fieldValue !== '' ? fieldValue : '');
				break;
			case 'Date':
				inp = $(`<input type="date" class="aa-input">`).val(fieldValue || '');
				break;
			case 'Select': {
				inp = $(`<select class="aa-input aa-select"></select>`);
				inp.append('<option value=""></option>');
				(field.options || '').split('\n').forEach(o => {
					o = o.trim();
					if (o) inp.append(`<option value="${o}">${o}</option>`);
				});
				inp.val(fieldValue || field.default || '');
				break;
			}
			default:
				inp = $(`<input type="text" class="aa-input">`).val(fieldValue || '');
		}
		inp.data('field', field).data('fieldname', field.fieldname);
		if (field.reqd) inp.attr('required', true);
		return inp;
	}

	updateFieldStates();

	// ── Validation ────────────────────────────────────────────────────────────

	function validate() {
		let valid = true;
		modal.find('.aa-field:visible').each(function() {
			const fw = $(this);
			const inp = fw.find('input, textarea, select').first();
			const field = inp.data('field');
			const err = fw.find('.aa-field-error');
			err.text('').hide();
			inp.removeClass('aa-input-error');
			if (field && isFieldRequired(field, currentDoc)) {
				const val = field.fieldtype === 'Check'
					? (inp.prop('checked') ? 1 : 0)
					: inp.val();
				if (!val && val !== 0) {
					valid = false;
					inp.addClass('aa-input-error');
					err.text(`${field.label} is required`).show();
				}
			}
		});
		return valid;
	}

	// ── Save ─────────────────────────────────────────────────────────────────

	modal.find('.aa-btn-save').on('click', function() {
		if (!validate()) {
			frappe.show_alert({ message: 'Please fill all required fields', indicator: 'red' }, 3);
			return;
		}
		modal.find('.aa-field:visible').each(function() {
			const inp = $(this).find('input, textarea, select').first();
			const fieldname = inp.data('fieldname');
			const field = inp.data('field');
			if (!fieldname || !field) return;
			if (field.fieldtype === 'Check') {
				grid_row.doc[fieldname] = inp.prop('checked') ? 1 : 0;
			} else if (['Int', 'Float', 'Currency'].includes(field.fieldtype)) {
				const v = inp.val();
				grid_row.doc[fieldname] = v !== '' ? parseFloat(v) || 0 : 0;
			} else {
				grid_row.doc[fieldname] = inp.val();
			}
		});
		grid_row.refresh();
		renderRowCard(grid_row);
		closeModal(false);
		frappe.show_alert({ message: 'Entry saved', indicator: 'green' }, 2);
	});

	// ── Cancel / Close ────────────────────────────────────────────────────────

	function closeModal(check_empty) {
		if (check_empty) {
			const isEmpty = !fields.some(
				f => f.fieldname && f.fieldname !== 'name' && grid_row.doc[f.fieldname]
			);
			if (isEmpty) {
				grid_row.remove();
				setTimeout(() => renderEmptyState(grid_field), 80);
			}
		}
		overlay.removeClass('aa-modal-visible');
		setTimeout(() => overlay.remove(), 250);
	}

	modal.find('.aa-btn-cancel, .aa-modal-close').on('click', () => closeModal(true));
	overlay.on('click', e => {
		if ($(e.target).hasClass('aa-modal-overlay')) closeModal(true);
	});

	// Focus first visible input
	setTimeout(() => {
		modal.find('.aa-field:visible').first().find('input, textarea, select').first().focus();
	}, 120);
}
