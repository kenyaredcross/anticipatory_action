frappe.ready(function() {
	// bind events here

	frappe.web_form.on('Anticipatory Action Details', {
    after_load: function(form, doctype, docname) {
        // Hide the name field
        $('input[data-fieldname="name"]').closest('.form-group').hide();
    }
});

})