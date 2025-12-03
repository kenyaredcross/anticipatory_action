// Copyright (c) 2025, Kelvin Njenga and contributors
// For license information, please see license.txt

frappe.ui.form.on("Anticipatory Action User", {
    refresh(frm) {
        frm.doc.full_name = `${frm.doc.first_name || ""} ${frm.doc.last_name || ""}`;
        frm.refresh_field("full_name");
    },
});