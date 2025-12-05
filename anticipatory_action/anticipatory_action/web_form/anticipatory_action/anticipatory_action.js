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
frappe.web_form.after_load = () => {
    setTimeout(() => {
        let child_table_fieldname = 'anticipatory_action_details';
        
        let grid_field = frappe.web_form.fields_dict[child_table_fieldname];
        
        if (grid_field && grid_field.grid) {
            // Override add_new_row to add closed, then open
            let original_add_new_row = grid_field.grid.add_new_row.bind(grid_field.grid);
            
            grid_field.grid.add_new_row = function(idx, callback, show_dialog) {
                // Call original with show_dialog = false to add row collapsed
                let row = original_add_new_row(idx, callback, false);
                
                // Now open it
                setTimeout(() => {
                    let $last_row = $(grid_field.grid.wrapper).find('.grid-body .grid-row').last();
                    let $edit_btn = $last_row.find('.btn-open-row');
                    
                    if ($edit_btn.length) {
                        $edit_btn[0].click();
                    }
                }, 100);
                
                return row;
            };
        }
    }, 1000);
};