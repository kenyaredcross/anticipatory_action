frappe.ready(function() {
    frappe.web_form.on('Anticipatory Action Details', {
        after_load: function(form, doctype, docname) {
            $('input[data-fieldname="name"]').closest('.form-group').hide();
        }
    });
    
    // Add "Edit Details" button to each row
    setTimeout(function() {
        let field = frappe.web_form.fields_dict['anticipatory_action_details'];
        
        if (field && field.grid) {
            let grid = field.grid;
            
            // Add edit button to each row
            grid.wrapper.find('.grid-row').each(function() {
                let $row = $(this);
                if ($row.find('.btn-open-row').length === 0) {
                    let idx = $row.attr('data-idx');
                    let $editBtn = $('<button class="btn btn-xs btn-default btn-open-row" style="margin-left: 10px;">Edit Full Details</button>');
                    
                    $editBtn.on('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        let doc = grid.get_row(idx).doc;
                        grid.open_grid_row(doc);
                    });
                    
                    $row.find('.data-row').append($editBtn);
                }
            });
            
            // Watch for new rows being added
            let original_render_row = grid.render_row.bind(grid);
            grid.render_row = function(row) {
                original_render_row(row);
                
                let $row = $(row.wrapper);
                if ($row.find('.btn-open-row').length === 0) {
                    let $editBtn = $('<button class="btn btn-xs btn-default btn-open-row" style="margin-left: 10px;">Edit Full Details</button>');
                    
                    $editBtn.on('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        grid.open_grid_row(row.doc);
                    });
                    
                    $row.find('.data-row').append($editBtn);
                }
            };
        }
    }, 1000);
});