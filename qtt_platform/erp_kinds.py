"""
ERP document kinds (PROJ-0019) — every ERPNext / HRMS document Orbitra ERP and Office Pulse open through the shared
document engine (erp_docs.py), as plain data the app draws its list, form, detail and report screens from.

A kind:
  key, label, group, doctype, icon, product (QTT_ORBITRA / QTT_OFFICE_PULSE)
  area     the product's permission area (Orbitra: sales, purchases, inventory_edit, accounts, reports; Office Pulse: hr)
  plan     the plan feature flag that must be on (None: every plan)
  scope    "company" (the doctype has a company field) or "tenant" (a company-less master: the qtt_tenant field)
  title    the field shown as the row's title; sub: fields under it; date / amount / status fields
  fields   header fields: (name, label, type, extra) — types: data, text, date, datetime, int, float, currency, check,
           select (extra = options), link (extra = a LINKS key)
  table    (child field, label, [fields]) — the lines (items, accounts, criteria…) or None
  submit   True when the document is submitted (draft → submitted → cancelled)
  create   False when new ones are made elsewhere (from another document) — the list and detail still work
  next     [(label, target kind, "python.path.to.mapper")] — "Make delivery note" etc.; the mapper takes the source name
Only the fields listed here are ever read from or written by the app (a whitelist), and every link is checked to belong
to this business before it's saved (erp_docs.check_link).
"""

D, T, DT, I, F, C, B, S, L = "date", "text", "datetime", "int", "float", "currency", "check", "select", "link"

# link → (doctype, scope, label field). scope: company / tenant / global / item (via the item's business) / employee
LINKS = {
	"customer": ("Customer", "tenant", "customer_name"), "supplier": ("Supplier", "tenant", "supplier_name"),
	"item": ("Item", "tenant", "item_name"), "warehouse": ("Warehouse", "company", "warehouse_name"),
	"price_list": ("Price List", "tenant", "price_list_name"), "territory": ("Territory", "tenant", "territory_name"),
	"sales_partner": ("Sales Partner", "tenant", "partner_name"), "uom": ("UOM", "global", "uom_name"),
	"currency": ("Currency", "global", "currency_name"), "cost_center": ("Cost Center", "company", "cost_center_name"),
	"account": ("Account", "company", "account_name"), "bank_account": ("Account", "company_bank", "account_name"),
	"fiscal_year": ("Fiscal Year", "global", "name"), "sales_order": ("Sales Order", "company", "name"),
	"delivery_note": ("Delivery Note", "company", "name"), "purchase_receipt": ("Purchase Receipt", "company", "name"),
	"purchase_order": ("Purchase Order", "company", "name"), "work_order": ("Work Order", "company", "name"),
	"bom": ("BOM", "company", "name"), "workstation": ("Workstation", "tenant", "workstation_name"),
	"operation": ("Operation", "tenant", "name"), "batch": ("Batch", "tenant", "batch_id"),
	"asset": ("Asset", "company", "asset_name"), "asset_category": ("Asset Category", "global", "asset_category_name"),
	"location": ("Location", "tenant", "location_name"), "lead": ("Lead", "company", "lead_name"),
	"qi_template": ("Quality Inspection Template", "tenant", "quality_inspection_template_name"),
	"quality_procedure": ("Quality Procedure", "tenant", "quality_procedure_name"),
	"maintenance_team": ("Asset Maintenance Team", "company", "maintenance_team_name"),
	"employee": ("Employee", "company", "employee_name"), "designation": ("Designation", "global", "designation_name"),
	"appraisal_cycle": ("Appraisal Cycle", "company", "cycle_name"), "kra": ("KRA", "tenant", "title"),
	"job_opening": ("Job Opening", "company", "job_title"), "job_applicant": ("Job Applicant", "tenant", "applicant_name"),
	"interview_round": ("Interview Round", "tenant", "round_name"), "user": ("User", "employee_user", "full_name"),
	"training_program": ("Training Program", "company", "training_program"), "training_event": ("Training Event", "company", "event_name"),
	"skill": ("Skill", "tenant", "skill_name"), "loyalty_program": ("Loyalty Program", "company", "loyalty_program_name"),
}

_ITEM_LINES = ("items", "Items", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("rate", "Rate", C, None)])
_ITEM_LINES_WH = ("items", "Items", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("rate", "Rate", C, None),
									 ("warehouse", "Store", L, "warehouse")])
_SELL_HEAD = [("customer", "Customer", L, "customer"), ("currency", "Currency", L, "currency"), ("selling_price_list", "Price list", L, "price_list")]
_BUY_HEAD = [("supplier", "Supplier", L, "supplier"), ("currency", "Currency", L, "currency"), ("buying_price_list", "Price list", L, "price_list")]


def K(key, label, group, doctype, icon, area, plan, scope, title, fields, table=None, *, sub=(), date=None, amount=None, status="status",
	  submit=False, create=True, next=(), product="QTT_ORBITRA"):
	return {"key": key, "label": label, "group": group, "doctype": doctype, "icon": icon, "area": area, "plan": plan, "scope": scope,
			"title": title, "sub": list(sub), "date": date, "amount": amount, "status": status, "submit": submit, "create": create,
			"fields": [{"name": f[0], "label": f[1], "type": f[2], "extra": f[3] if len(f) > 3 else None} for f in fields],
			"table": ({"field": table[0], "label": table[1],
					   "fields": [{"name": f[0], "label": f[1], "type": f[2], "extra": f[3]} for f in table[2]]} if table else None),
			"next": [{"label": n[0], "kind": n[1], "mapper": n[2]} for n in next], "product": product}


_SO = "erpnext.selling.doctype.sales_order.sales_order."
_DN = "erpnext.stock.doctype.delivery_note.delivery_note."
_PO = "erpnext.buying.doctype.purchase_order.purchase_order."
_PR = "erpnext.stock.doctype.purchase_receipt.purchase_receipt."
_WO = "erpnext.manufacturing.doctype.work_order.work_order."

KINDS = [
	# ---- sales and purchase flow --------------------------------------------------------------------------------
	K("sales_order", "Sales orders", "Sales", "Sales Order", "receipt_long", "sales", "sales_flow", "company", "customer_name",
	  _SELL_HEAD + [("transaction_date", "Order date", D), ("delivery_date", "Deliver by", D)], _ITEM_LINES_WH,
	  date="transaction_date", amount="grand_total", submit=True,
	  next=[("Make delivery note", "delivery_note", _SO + "make_delivery_note"), ("Make invoice", "sales_invoice", _SO + "make_sales_invoice"),
			("Make pick list", "pick_list", _SO + "create_pick_list")]),
	K("delivery_note", "Delivery notes", "Sales", "Delivery Note", "local_shipping", "sales", "sales_flow", "company", "customer_name",
	  _SELL_HEAD + [("posting_date", "Date", D), ("lr_no", "Vehicle / docket no.", "data")], _ITEM_LINES_WH,
	  date="posting_date", amount="grand_total", submit=True,
	  next=[("Make invoice", "sales_invoice", _DN + "make_sales_invoice"), ("Make packing slip", "packing_slip", _DN + "make_packing_slip"),
			("Make return", "delivery_note", _DN + "make_sales_return")]),
	K("price_list", "Price lists", "Sales", "Price List", "sell", "sales", "sales_flow", "tenant", "price_list_name",
	  [("price_list_name", "Name", "data"), ("currency", "Currency", L, "currency"), ("selling", "For selling", B), ("buying", "For buying", B),
	   ("enabled", "In use", B)], status=None),
	K("item_price", "Item prices", "Sales", "Item Price", "price_change", "sales", "sales_flow", "item", "item_name",
	  [("item_code", "Item", L, "item"), ("price_list", "Price list", L, "price_list"), ("price_list_rate", "Rate", C),
	   ("valid_from", "Valid from", D), ("valid_upto", "Valid until", D)], sub=("price_list",), amount="price_list_rate", status=None),
	K("pricing_rule", "Pricing rules", "Sales", "Pricing Rule", "percent", "sales", "sales_flow", "company", "title",
	  [("title", "Name", "data"), ("apply_on", "Apply on", S, "Item Code\nItem Group\nTransaction"), ("selling", "Selling", B), ("buying", "Buying", B),
	   ("rate_or_discount", "Give", S, "Discount Percentage\nDiscount Amount\nRate"), ("discount_percentage", "Discount %", F),
	   ("discount_amount", "Discount amount", C), ("rate", "Rate", C), ("min_qty", "From qty", F), ("valid_from", "Valid from", D),
	   ("valid_upto", "Valid until", D), ("customer", "Only for customer", L, "customer")],
	  ("items", "Items", [("item_code", "Item", L, "item")]), status=None),
	K("purchase_order", "Purchase orders", "Buying", "Purchase Order", "shopping_cart", "purchases", "sales_flow", "company", "supplier_name",
	  _BUY_HEAD + [("transaction_date", "Order date", D), ("schedule_date", "Needed by", D), ("is_subcontracted", "Subcontracted", B)], _ITEM_LINES_WH,
	  date="transaction_date", amount="grand_total", submit=True,
	  next=[("Make goods receipt", "purchase_receipt", _PO + "make_purchase_receipt"), ("Make supplier bill", "purchase_invoice", _PO + "make_purchase_invoice"),
			("Make subcontracting order", "subcontracting_order", _PO + "make_subcontracting_order")]),
	K("purchase_receipt", "Goods receipts", "Buying", "Purchase Receipt", "inventory", "purchases", "sales_flow", "company", "supplier_name",
	  _BUY_HEAD + [("posting_date", "Date", D), ("supplier_delivery_note", "Supplier's delivery no.", "data")], _ITEM_LINES_WH,
	  date="posting_date", amount="grand_total", submit=True,
	  next=[("Make supplier bill", "purchase_invoice", _PR + "make_purchase_invoice"), ("Return to supplier", "purchase_receipt", _PR + "make_purchase_return"),
			("Add landed cost", "landed_cost", "prefill:__receipt")]),
	K("purchase_invoice", "Supplier bills (full)", "Buying", "Purchase Invoice", "request_quote", "purchases", "sales_flow", "company", "supplier_name",
	  _BUY_HEAD + [("posting_date", "Date", D), ("bill_no", "Supplier bill no.", "data"), ("due_date", "Due", D)], _ITEM_LINES_WH,
	  date="posting_date", amount="grand_total", submit=True,
	  next=[("Make return", "purchase_invoice", "erpnext.accounts.doctype.purchase_invoice.purchase_invoice.make_debit_note")]),
	K("sales_invoice", "Invoices (full)", "Sales", "Sales Invoice", "receipt", "sales", "sales_flow", "company", "customer_name",
	  _SELL_HEAD + [("posting_date", "Date", D), ("due_date", "Due", D)], _ITEM_LINES_WH, date="posting_date", amount="grand_total", submit=True),
	K("reorder", "Reorder levels", "Stock", "Item", "low_priority", "inventory_edit", "sales_flow", "tenant", "item_name",
	  [], ("reorder_levels", "When stock falls to", [("warehouse", "Store", L, "warehouse"), ("warehouse_reorder_level", "Reorder at", F, None),
												   ("warehouse_reorder_qty", "Order qty", F, None), ("material_request_type", "As", S, "Purchase\nTransfer\nManufacture")]),
	  status=None, create=False),
	# ---- stock depth ----------------------------------------------------------------------------------------------
	K("batch", "Batches", "Stock", "Batch", "qr_code_2", "inventory_edit", "stock_depth", "tenant", "batch_id",
	  [("batch_id", "Batch no.", "data"), ("item", "Item", L, "item"), ("manufacturing_date", "Made on", D), ("expiry_date", "Expires", D)],
	  sub=("item",), date="expiry_date", status=None),
	K("serial_no", "Serial numbers", "Stock", "Serial No", "pin", "inventory_edit", "stock_depth", "company", "serial_no",
	  [("serial_no", "Serial no.", "data"), ("item_code", "Item", L, "item"), ("warranty_expiry_date", "Warranty until", D)], sub=("item_code",)),
	K("pick_list", "Pick lists", "Stock", "Pick List", "checklist", "inventory_edit", "stock_depth", "company", "name",
	  [("purpose", "For", S, "Delivery\nMaterial Transfer\nMaterial Transfer for Manufacture"), ("customer", "Customer", L, "customer")],
	  ("locations", "Pick", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("warehouse", "From store", L, "warehouse")]), submit=True,
	  next=[("Make delivery note", "delivery_note", "erpnext.stock.doctype.pick_list.pick_list.create_delivery_note")]),
	K("packing_slip", "Packing slips", "Stock", "Packing Slip", "inventory_2", "inventory_edit", "stock_depth", "delivery_note", "delivery_note",
	  [("delivery_note", "Delivery note", L, "delivery_note"), ("from_case_no", "From box no.", I), ("to_case_no", "To box no.", I)],
	  ("items", "In the boxes", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("net_weight", "Weight", F, None)]),
	  submit=True, create=False),
	K("landed_cost", "Landed costs", "Stock", "Landed Cost Voucher", "add_shopping_cart", "purchases", "stock_depth", "company", "name",
	  [("__receipt", "Goods receipt", L, "purchase_receipt"), ("distribute_charges_based_on", "Share by", S, "Qty\nAmount\nDistribute Manually")],
	  ("taxes", "Costs (freight, duty…)", [("description", "What", "data", None), ("expense_account", "Account", L, "account"), ("amount", "Amount", C, None)]),
	  submit=True),
	# ---- accounts depth -------------------------------------------------------------------------------------------
	K("cost_center", "Cost centres", "Accounts", "Cost Center", "account_tree", "accounts", "accounts_depth", "company", "cost_center_name",
	  [("cost_center_name", "Name", "data"), ("parent_cost_center", "Under", L, "cost_center"), ("is_group", "Is a group", B)], status=None),
	K("budget", "Budgets", "Accounts", "Budget", "savings", "accounts", "accounts_depth", "company", "cost_center",
	  [("budget_against", "Budget for", S, "Cost Center"), ("cost_center", "Cost centre", L, "cost_center"), ("fiscal_year", "Year", L, "fiscal_year"),
	   ("action_if_annual_budget_exceeded", "If the year's budget runs out", S, "Warn\nStop\nIgnore")],
	  ("accounts", "Budget per account", [("account", "Account", L, "account"), ("budget_amount", "Amount", C, None)]), submit=True),
	K("asset", "Assets and equipment", "Accounts", "Asset", "precision_manufacturing", "accounts", "accounts_depth", "company", "asset_name",
	  [("asset_name", "Name", "data"), ("item_code", "Asset item", L, "item"), ("asset_category", "Category", L, "asset_category"),
	   ("location", "Location", L, "location"), ("purchase_date", "Bought on", D), ("available_for_use_date", "In use from", D),
	   ("gross_purchase_amount", "Cost", C), ("is_existing_asset", "Already owned", B)], date="purchase_date", amount="gross_purchase_amount", submit=True),
	# ---- CRM and buying extras ------------------------------------------------------------------------------------
	K("lead", "Leads", "CRM", "Lead", "person_search", "sales", "crm", "company", "lead_name",
	  [("lead_name", "Name", "data"), ("company_name", "Business", "data"), ("email_id", "Email", "data"), ("mobile_no", "Mobile", "data"),
	   ("source", "Source", S, "\nWalk In\nReference\nAdvertisement\nCampaign\nWebsite\nExisting Customer"), ("territory", "Territory", L, "territory")],
	  sub=("company_name",), next=[("Make opportunity", "opportunity", "erpnext.crm.doctype.lead.lead.make_opportunity")]),
	K("opportunity", "Opportunities", "CRM", "Opportunity", "trending_up", "sales", "crm", "company", "party_name",
	  [("opportunity_from", "From", S, "Customer\nLead"), ("party_name", "Customer or lead", "data"), ("sales_stage", "Stage", S,
	   "Prospecting\nQualification\nNeeds Analysis\nValue Proposition\nIdentifying Decision Makers\nPerception Analysis\nProposal/Price Quote\nNegotiation/Review"),
	   ("opportunity_amount", "Value", C), ("probability", "Chance %", F), ("expected_closing", "Closing by", D)],
	  _ITEM_LINES, amount="opportunity_amount", date="expected_closing",
	  next=[("Make quotation", "quotation", "erpnext.crm.doctype.opportunity.opportunity.make_quotation")]),
	K("quotation", "Quotations (full)", "Sales", "Quotation", "request_quote", "sales", "crm", "company", "customer_name",
	  [("quotation_to", "To", S, "Customer\nLead"), ("party_name", "Customer or lead", "data"), ("transaction_date", "Date", D),
	   ("valid_till", "Valid until", D)], _ITEM_LINES, date="transaction_date", amount="grand_total", submit=True,
	  next=[("Make sales order", "sales_order", "erpnext.selling.doctype.quotation.quotation.make_sales_order")]),
	K("territory", "Territories", "CRM", "Territory", "map", "sales", "crm", "tenant", "territory_name",
	  [("territory_name", "Name", "data"), ("parent_territory", "Under", L, "territory"), ("is_group", "Is a group", B)], status=None),
	K("sales_partner", "Sales partners", "CRM", "Sales Partner", "handshake", "sales", "crm", "tenant", "partner_name",
	  [("partner_name", "Name", "data"), ("commission_rate", "Commission %", F), ("territory", "Territory", L, "territory")], status=None),
	K("loyalty_program", "Loyalty programmes", "CRM", "Loyalty Program", "loyalty", "sales", "crm", "company", "loyalty_program_name",
	  [("loyalty_program_name", "Name", "data"), ("from_date", "From", D), ("to_date", "Until", D), ("conversion_factor", "1 point is worth", C),
	   ("expiry_duration", "Points last (days)", I), ("auto_opt_in", "Every customer joins", B), ("expense_account", "Expense account", L, "account"),
	   ("cost_center", "Cost centre", L, "cost_center")],
	  ("collection_rules", "Earn", [("tier_name", "Tier", "data", None), ("min_spent", "From spend", C, None), ("collection_factor", "Spend per point", C, None)]),
	  status=None),
	K("rfq", "Requests for quotation", "Buying", "Request for Quotation", "forward_to_inbox", "purchases", "crm", "company", "name",
	  [("transaction_date", "Date", D), ("message_for_supplier", "Message", T)],
	  ("items", "Items", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("warehouse", "For store", L, "warehouse")]),
	  date="transaction_date", submit=True,
	  next=[("Make supplier quotation", "supplier_quotation", "erpnext.buying.doctype.request_for_quotation.request_for_quotation.make_supplier_quotation_from_rfq")]),
	K("supplier_quotation", "Supplier quotations", "Buying", "Supplier Quotation", "request_page", "purchases", "crm", "company", "supplier_name",
	  _BUY_HEAD + [("transaction_date", "Date", D), ("valid_till", "Valid until", D)], _ITEM_LINES, date="transaction_date", amount="grand_total", submit=True,
	  next=[("Make purchase order", "purchase_order", "erpnext.buying.doctype.supplier_quotation.supplier_quotation.make_purchase_order")]),
	K("supplier_scorecard", "Supplier scorecards", "Buying", "Supplier Scorecard", "scoreboard", "purchases", "crm", "supplier", "supplier",
	  [("supplier", "Supplier", L, "supplier"), ("period", "Every", S, "Per Week\nPer Month\nPer Year")], status="status"),
	# ---- manufacturing ------------------------------------------------------------------------------------------
	K("bom", "Bills of materials", "Manufacturing", "BOM", "account_tree", "inventory_edit", "manufacturing", "company", "item_name",
	  [("item", "Makes", L, "item"), ("quantity", "Qty made", F), ("is_default", "Default", B), ("with_operations", "With operations", B)],
	  ("items", "Materials", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("rate", "Rate", C, None)]),
	  amount="total_cost", submit=True,
	  next=[("Make work order", "work_order", "erpnext.manufacturing.doctype.bom.bom.make_work_order")]),
	K("work_order", "Work orders", "Manufacturing", "Work Order", "factory", "inventory_edit", "manufacturing", "company", "production_item",
	  [("production_item", "Item to make", L, "item"), ("bom_no", "Bill of materials", L, "bom"), ("qty", "Qty", F),
	   ("wip_warehouse", "Work-in-progress store", L, "warehouse"), ("fg_warehouse", "Finished goods store", L, "warehouse"),
	   ("planned_start_date", "Start", DT)], date="planned_start_date", submit=True,
	  next=[("Send materials", "stock_entry", "qtt_platform.erp_docs.wo_transfer"), ("Finish (make the goods)", "stock_entry", "qtt_platform.erp_docs.wo_finish")]),
	K("job_card", "Job cards", "Manufacturing", "Job Card", "assignment", "inventory_edit", "manufacturing", "company", "operation",
	  [("work_order", "Work order", L, "work_order"), ("operation", "Operation", L, "operation"), ("workstation", "Workstation", L, "workstation"),
	   ("for_quantity", "Qty", F)], submit=True, create=False),
	K("workstation", "Workstations", "Manufacturing", "Workstation", "precision_manufacturing", "inventory_edit", "manufacturing", "tenant", "workstation_name",
	  [("workstation_name", "Name", "data"), ("production_capacity", "Jobs at once", I), ("hour_rate_electricity", "Power cost / hour", C),
	   ("hour_rate_labour", "Labour cost / hour", C)], status=None),
	K("operation", "Operations", "Manufacturing", "Operation", "build", "inventory_edit", "manufacturing", "tenant", "name",
	  [("__newname", "Name", "data"), ("workstation", "Default workstation", L, "workstation"), ("description", "Description", T)], status=None),
	K("production_plan", "Production plans", "Manufacturing", "Production Plan", "event_note", "inventory_edit", "manufacturing", "company", "name",
	  [("posting_date", "Date", D)], ("po_items", "Make", [("item_code", "Item", L, "item"), ("bom_no", "Bill of materials", L, "bom"),
														   ("planned_qty", "Qty", F, None), ("warehouse", "Into store", L, "warehouse")]),
	  date="posting_date", submit=True),
	K("subcontracting_order", "Subcontracting orders", "Manufacturing", "Subcontracting Order", "handyman", "purchases", "manufacturing", "company",
	  "supplier_name", [("supplier", "Subcontractor", L, "supplier"), ("transaction_date", "Date", D), ("supplier_warehouse", "Their store", L, "warehouse")],
	  ("items", "Goods to make", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("bom", "Bill of materials", L, "bom")]),
	  date="transaction_date", submit=True, create=False),
	K("stock_entry", "Stock entries", "Manufacturing", "Stock Entry", "swap_horiz", "inventory_edit", "manufacturing", "company", "stock_entry_type",
	  [("stock_entry_type", "Type", S, "Material Transfer for Manufacture\nManufacture\nMaterial Issue\nMaterial Receipt\nMaterial Transfer"),
	   ("posting_date", "Date", D)],
	  ("items", "Items", [("item_code", "Item", L, "item"), ("qty", "Qty", F, None), ("s_warehouse", "From store", L, "warehouse"),
						  ("t_warehouse", "To store", L, "warehouse")]), date="posting_date", submit=True),
	# ---- quality --------------------------------------------------------------------------------------------------
	K("quality_inspection", "Quality inspections", "Quality", "Quality Inspection", "fact_check", "inventory_edit", "manufacturing", "company", "item_name",
	  [("inspection_type", "When", S, "Incoming\nOutgoing\nIn Process"), ("reference_type", "For", S, "Purchase Receipt\nDelivery Note\nStock Entry\nJob Card"),
	   ("reference_name", "Document no.", "data"), ("item_code", "Item", L, "item"), ("sample_size", "Sample size", F),
	   ("quality_inspection_template", "Checklist", L, "qi_template"), ("status", "Result", S, "Accepted\nRejected"), ("remarks", "Notes", T)],
	  ("readings", "Readings", [("specification", "Check", "data", None), ("reading_1", "Reading", "data", None), ("status", "Result", S, "Accepted\nRejected")]),
	  submit=True),
	K("qi_template", "Inspection checklists", "Quality", "Quality Inspection Template", "rule", "inventory_edit", "manufacturing", "tenant",
	  "quality_inspection_template_name", [("quality_inspection_template_name", "Name", "data")],
	  ("item_quality_inspection_parameter", "Checks", [("specification", "Check", "data", None), ("min_value", "Min", F, None),
												   ("max_value", "Max", F, None), ("value", "Expected", "data", None)]), status=None),
	K("quality_goal", "Quality goals", "Quality", "Quality Goal", "flag", "inventory_edit", "manufacturing", "tenant", "goal",
	  [("goal", "Goal", "data"), ("frequency", "Review", S, "None\nDaily\nWeekly\nMonthly\nQuarterly")],
	  ("objectives", "Objectives", [("objective", "Objective", "data", None), ("target", "Target", "data", None), ("uom", "Unit", L, "uom")]), status=None),
	K("non_conformance", "Non-conformances", "Quality", "Non Conformance", "report", "inventory_edit", "manufacturing", "tenant", "subject",
	  [("subject", "What went wrong", "data"), ("procedure", "Procedure", L, "quality_procedure"), ("status", "Status", S, "Open\nResolved\nCancelled"),
	   ("details", "Details", T), ("corrective_action", "Corrective action", T), ("preventive_action", "Preventive action", T)]),
	K("quality_procedure", "Quality procedures", "Quality", "Quality Procedure", "menu_book", "inventory_edit", "manufacturing", "tenant",
	  "quality_procedure_name", [("quality_procedure_name", "Name", "data")],
	  ("processes", "Steps", [("process_description", "Step", T, None)]), status=None),
	# ---- maintenance ----------------------------------------------------------------------------------------------
	K("maintenance_team", "Maintenance teams", "Maintenance", "Asset Maintenance Team", "groups", "accounts", "manufacturing", "company",
	  "maintenance_team_name", [("maintenance_team_name", "Name", "data"), ("maintenance_manager", "Manager", L, "user")],
	  ("maintenance_team_members", "Members", [("team_member", "Member", L, "user"), ("maintenance_role", "Role", "data", None)]), status=None),
	K("asset_maintenance", "Preventive maintenance", "Maintenance", "Asset Maintenance", "build_circle", "accounts", "manufacturing", "company",
	  "asset_name", [("asset_name", "Equipment", L, "asset"), ("maintenance_team", "Team", L, "maintenance_team")],
	  ("asset_maintenance_tasks", "Tasks", [("maintenance_task", "Task", "data", None), ("maintenance_type", "Type", S, "Preventive Maintenance\nCalibration"),
										  ("periodicity", "Every", S, "Daily\nWeekly\nMonthly\nQuarterly\nHalf-yearly\nYearly\n2 Yearly\n3 Yearly"),
										  ("start_date", "From", D, None), ("assign_to", "Done by", L, "user")]), status=None),
	K("maintenance_log", "Maintenance visits", "Maintenance", "Asset Maintenance Log", "event_available", "accounts", "manufacturing", "maintenance_plan",
	  "asset_name", [("asset_maintenance", "Maintenance plan", "data"), ("task", "Task", "data"), ("maintenance_status", "Status", S,
	   "Planned\nCompleted\nCancelled\nOverdue"), ("completion_date", "Done on", D), ("actions_performed", "Work done", T)],
	  date="completion_date", status="maintenance_status", submit=True),
	K("asset_repair", "Breakdowns and repairs", "Maintenance", "Asset Repair", "car_repair", "accounts", "manufacturing", "company", "asset_name",
	  [("asset", "Equipment", L, "asset"), ("failure_date", "Broke down", DT), ("description", "What happened", T), ("repair_status", "Status", S,
	   "Pending\nCompleted\nCancelled"), ("completion_date", "Fixed on", DT), ("repair_cost", "Repair cost", C)],
	  date="failure_date", amount="repair_cost", status="repair_status", submit=True),
	# ---- HR (Office Pulse) -------------------------------------------------------------------------------------------
	K("appraisal_cycle", "Appraisal cycles", "Performance", "Appraisal Cycle", "event_repeat", "hr", "appraisal", "company", "cycle_name",
	  [("cycle_name", "Name", "data"), ("start_date", "From", D), ("end_date", "Until", D),
	   ("kra_evaluation_method", "Goals scored by", S, "Automated Based on Goal Progress\nManual Rating")], date="start_date",
	  product="QTT_OFFICE_PULSE"),
	K("kra", "Key result areas", "Performance", "KRA", "flag", "hr", "appraisal", "tenant", "title", [("title", "Name", "data")], status=None,
	  product="QTT_OFFICE_PULSE"),
	K("appraisal", "Appraisals", "Performance", "Appraisal", "star_rate", "hr", "appraisal", "company", "employee_name",
	  [("employee", "Employee", L, "employee"), ("appraisal_cycle", "Cycle", L, "appraisal_cycle"), ("remarks", "Remarks", T)],
	  ("appraisal_kra", "Key result areas", [("kra", "Area", L, "kra"), ("per_weightage", "Weight %", F, None)]),
	  sub=("appraisal_cycle",), amount="final_score", submit=True, product="QTT_OFFICE_PULSE"),
	K("job_opening", "Job openings", "Recruitment", "Job Opening", "work", "hr", "recruitment", "company", "job_title",
	  [("job_title", "Title", "data"), ("designation", "Designation", L, "designation"), ("status", "Status", S, "Open\nClosed"),
	   ("vacancies", "Vacancies", I), ("lower_range", "Salary from", C), ("upper_range", "Salary to", C), ("description", "Description", T)],
	  product="QTT_OFFICE_PULSE"),
	K("job_applicant", "Applicants", "Recruitment", "Job Applicant", "person_add", "hr", "recruitment", "tenant", "applicant_name",
	  [("applicant_name", "Name", "data"), ("email_id", "Email", "data"), ("phone_number", "Phone", "data"), ("job_title", "For opening", L, "job_opening"),
	   ("status", "Status", S, "Open\nReplied\nRejected\nHold\nAccepted"), ("cover_letter", "Notes", T)], sub=("job_title",),
	  product="QTT_OFFICE_PULSE"),
	K("interview_round", "Interview rounds", "Recruitment", "Interview Round", "list_alt", "hr", "recruitment", "tenant", "round_name",
	  [("round_name", "Name", "data"), ("designation", "For designation", L, "designation")],
	  ("expected_skill_set", "Skills to check", [("skill", "Skill", L, "skill")]), status=None, product="QTT_OFFICE_PULSE"),
	K("interview", "Interviews", "Recruitment", "Interview", "event", "hr", "recruitment", "tenant", "job_applicant",
	  [("interview_round", "Round", L, "interview_round"), ("job_applicant", "Applicant", L, "job_applicant"), ("scheduled_on", "Date", D),
	   ("from_time", "From", "data"), ("to_time", "To", "data"), ("status", "Status", S, "Pending\nUnder Review\nCleared\nRejected")],
	  ("interview_details", "Interviewers", [("interviewer", "Interviewer", L, "user")]), date="scheduled_on", product="QTT_OFFICE_PULSE"),
	K("training_program", "Training programmes", "Training", "Training Program", "school", "hr", "training", "company", "training_program",
	  [("training_program", "Name", "data"), ("trainer_name", "Trainer", "data"), ("description", "What it covers", T)], status=None,
	  product="QTT_OFFICE_PULSE"),
	K("training_event", "Training events", "Training", "Training Event", "event_seat", "hr", "training", "company", "event_name",
	  [("event_name", "Name", "data"), ("training_program", "Programme", L, "training_program"), ("type", "Type", S,
	   "Seminar\nTheory\nWorkshop\nConference\nExam\nInternet\nSelf-Study"), ("start_time", "Starts", DT), ("end_time", "Ends", DT),
	   ("location", "Where", "data"), ("trainer_name", "Trainer", "data")],
	  ("employees", "Who attends", [("employee", "Employee", L, "employee")]), date="start_time", status="event_status", submit=True,
	  product="QTT_OFFICE_PULSE"),
	K("skill", "Skills", "Training", "Skill", "psychology", "hr", "training", "tenant", "skill_name",
	  [("skill_name", "Name", "data"), ("description", "Description", T)], status=None, product="QTT_OFFICE_PULSE"),
	K("skill_map", "Employee skills", "Training", "Employee Skill Map", "hub", "hr", "training", "employee", "employee_name",
	  [("employee", "Employee", L, "employee")],
	  ("employee_skills", "Skills", [("skill", "Skill", L, "skill"), ("proficiency", "Level (1–5)", I, None)]), status=None,
	  product="QTT_OFFICE_PULSE"),
]

# Reports: key → (label, group, area, plan, ERPNext / HRMS report module with execute(filters), default filters, product)
REPORTS = {
	"trial_balance": ("Trial balance", "Accounts", "accounts", "accounts_depth", "erpnext.accounts.report.trial_balance.trial_balance", "fy", "QTT_ORBITRA"),
	"balance_sheet": ("Balance sheet", "Accounts", "accounts", "accounts_depth", "erpnext.accounts.report.balance_sheet.balance_sheet", "fy_period", "QTT_ORBITRA"),
	"profit_loss": ("Profit and loss", "Accounts", "accounts", "accounts_depth",
					"erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement", "fy_period", "QTT_ORBITRA"),
	"cash_flow": ("Cash flow", "Accounts", "accounts", "accounts_depth", "erpnext.accounts.report.cash_flow.cash_flow", "fy_period", "QTT_ORBITRA"),
	"budget_variance": ("Budget against actual", "Accounts", "accounts", "accounts_depth",
						"erpnext.accounts.report.budget_variance_report.budget_variance_report", "budget", "QTT_ORBITRA"),
	"stock_ledger_value": ("Stock valuation", "Stock", "inventory_edit", "stock_depth", "erpnext.stock.report.stock_balance.stock_balance", "dates", "QTT_ORBITRA"),
	"batch_expiry": ("Batches and expiry", "Stock", "inventory_edit", "stock_depth",
					 "erpnext.stock.report.batch_wise_balance_history.batch_wise_balance_history", "dates", "QTT_ORBITRA"),
	"sales_funnel": ("Sales funnel", "CRM", "sales", "crm", "erpnext.selling.page.sales_funnel.sales_funnel", "funnel", "QTT_ORBITRA"),
	"supplier_quotation_comparison": ("Supplier quotes compared", "Buying", "purchases", "crm",
									  "erpnext.buying.report.supplier_quotation_comparison.supplier_quotation_comparison", "dates", "QTT_ORBITRA"),
	"work_order_summary": ("Work orders", "Manufacturing", "inventory_edit", "manufacturing",
						   "erpnext.manufacturing.report.work_order_summary.work_order_summary", "fy_dates", "QTT_ORBITRA"),
	"quality_inspection_summary": ("Inspections", "Quality", "inventory_edit", "manufacturing",
								   "erpnext.manufacturing.report.quality_inspection_summary.quality_inspection_summary", "dates", "QTT_ORBITRA"),
	"appraisal_overview": ("Appraisal overview", "Performance", "hr", "appraisal",
						   "hrms.hr.report.appraisal_overview.appraisal_overview", "none", "QTT_OFFICE_PULSE"),
	"recruitment_analytics": ("Recruitment", "Recruitment", "hr", "recruitment",
							  "hrms.hr.report.recruitment_analytics.recruitment_analytics", "none", "QTT_OFFICE_PULSE"),
}

# Special screens (not a plain document list): key → (label, group, area, plan, product)
TOOLS = {"bank_clearance": ("Bank reconciliation", "Accounts", "accounts", "accounts_depth", "QTT_ORBITRA"),
		 "customer_portal": ("Customer portal", "CRM", "sales", "crm", "QTT_ORBITRA")}

BY_KEY = {k["key"]: k for k in KINDS}
GROUP_ORDER = ("Sales", "Buying", "Stock", "Accounts", "CRM", "Manufacturing", "Quality", "Maintenance", "Performance", "Recruitment", "Training")


def kinds_for(product: str) -> list[dict]:
	return [k for k in KINDS if k["product"] == product]


def allowed(entry_area: str, plan: str | None, areas: list[str], features: dict) -> bool:
	"""May this person open this kind / report / tool: their area, and its plan flag switched on."""
	if entry_area not in areas:
		return False
	return not plan or str(features.get(plan, 0)) in ("1", "True", "true")


def write_fields(kind: dict) -> set[str]:
	"""The header fields the app may write (the whitelist)."""
	return {f["name"] for f in kind["fields"]}
