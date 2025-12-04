frappe.web_form.on('load', () => {
    frappe.web_form.fields.forEach(df => {
        if (df.fieldtype === "Table") {
            const table = frappe.web_form.fields_dict[df.fieldname];
            
            table.grid.fields_map && Object.keys(table.grid.fields_map).forEach(childfield => {
                const child_df = table.grid.fields_map[childfield];

                if (["county", "sub_county"].includes(child_df.fieldname)) {
                    child_df.get_query = () => {
                        return {
                            query: "anticipatory_action.api.search_link.search_link_fields"
                        };
                    };
                }
            });
        }
    });
});
