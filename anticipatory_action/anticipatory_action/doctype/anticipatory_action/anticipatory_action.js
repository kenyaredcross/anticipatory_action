// Copyright (c) 2025, Kelvin Njenga and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Anticipatory Action", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on('AnticipatoryAction', {
    county(frm) {
        frm.set_query("sub_county", function() {
            return {
                filters: {
                    county: frm.doc.county
                }
            };
        });

        // Clear previous subcounty if county changes
        frm.set_value("sub_county", "");
    }
});
