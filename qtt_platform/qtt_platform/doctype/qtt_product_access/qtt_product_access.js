// Desk UI fix — product_role is a Select field with no static options
// (see qtt_product_access.json's own comment on this field): this script
// loads the real role catalog for whichever Product is selected
// (api/product.py::get_product_role_options, backed by QTT Product.roles
// — never a hardcoded list) and sets it as this control's options.
// Server-side validate() is the actual authority on what's a valid role;
// this only keeps the admin from having to guess/type it correctly.
frappe.ui.form.on("QTT Product Access", {
	refresh(frm) {
		load_product_role_options(frm);
	},
	product(frm) {
		// A role valid for the previous Product is not assumed valid for
		// the new one — cleared here rather than left stale, matching
		// the "clear an existing role if it is not valid for the newly
		// selected product" requirement.
		frm.set_value("product_role", "");
		load_product_role_options(frm);
	},
});

function load_product_role_options(frm) {
	if (!frm.doc.product) {
		frm.set_df_property("product_role", "options", []);
		return;
	}
	frappe.call({
		method: "qtt_platform.api.product.get_product_role_options",
		args: { product: frm.doc.product },
		callback(r) {
			const options = r.message || [];
			frm.set_df_property("product_role", "options", options);

			const valid_keys = options.map((option) => option.value);
			if (frm.doc.product_role && !valid_keys.includes(frm.doc.product_role)) {
				frm.set_value("product_role", "");
			}
			frm.refresh_field("product_role");
		},
	});
}
