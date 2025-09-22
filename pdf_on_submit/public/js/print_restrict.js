/**
 * ============================================================================
 * Custom Print Page Toolbar Override — Restrict Not Approved Quotation Downloads
 * ============================================================================
 * Purpose:
 *   One of our clients uses a workflow-enabled Quotation process where:
 *     - A Quotation in **Request For Approval** state must NOT be printed or downloaded.
 *     - Printing/downloading should only be allowed once the document has moved
 *       beyond the Draft or Pending stage (e.g., after approval or self approval).
 *
 *   This script enforces that restriction on the Print Page (`/app/print/...`).
 *
 * ⚙️ What This Script Does:
 *   - Overrides the `set_title()` method of Frappe's `PrintView` class.(path: frappe/printing/page/print/print.js)
 *   - When the document is a:
 *       → `Quotation` AND `workflow_state is not Approval and Self Approval`:
 *         → It hides:
 *             1. The "Print" primary action button.
 *             2. The "PDF" download button (identified via `#icon-small-file`).
 *             3. The "Full Page" button (identified via `#icon-full-page`).
 *   - For all other cases: these buttons are shown normally.

 * Technical Implementation:
 *   - Uses an IIFE (Immediately Invoked Function Expression) to:
 *       → Limit scope and prevent global leakage.
 *       → Execute the override logic immediately.
 *   - Calls the original `set_title()` method after injecting the custom logic.
 * 	 - Uses jQuery `.filter()` with `.text().trim()` to target buttons by their
 *     visible text (innertext) — this means we are matching **what the user sees on screen**,
 *     not `data-label` attributes or icon references.
 *   - Injected using the `page_js` hook for the Print Page.
 *
 * File:
 *   pdf_on_submit/public/js/print_restrict.js
 *
 * Hook (hooks.py):
 *   page_js = {
 *       "print": "public/js/print_restrict.js"
 *   }

 * Why This Approach:
 *   - Non-intrusive: Core files remain untouched.
 *   - Safe and scoped: Only runs on the `/print` page, and does not leak variables.
 *   - Frappe-aligned: Extends core functionality cleanly using prototypal inheritance.

 * Maintenance Notes:
 Even though we preserve original behavior using `fnOriginalSetTitle.call(this)`,
 *   changes in Frappe's internal implementation of `PrintView` may still impact this override.

 *   Here's what could break and why:

 *   | Change Type                                                           | Impact                                          | Example                                                            |
 *   | --------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------ |
 *   | ✅ *Internal logic changes*                                            | ❌ No issue                                      | You're still calling it — good.                                    |
 *   | ❌ *Renames or removes* `set_title()`                                  | 🚨 Breaks your override                         | Your override won't run because the method no longer exists.       |
 *   | ❌ *Adds new behavior before/after* `set_title()` is called internally | 🔄 You might be bypassing new internal features | If they rely on `set_title()` being executed at a different point. |
 *   

 * ============================================================================
 */

(function () {
	// Check if PrintView and set_title exist before proceeding
	if (frappe.ui.form.PrintView.prototype.set_title) {
		const fnOriginalSetTitle = frappe.ui.form.PrintView.prototype.set_title;

		frappe.ui.form.PrintView.prototype.set_title = function () {
			try {
				// (bug-fix note) : both form's Save and Print was primary action button, 
				// so for more robust checking we are reading the innertext as well
				// in the element
				// @params - iAction (str) - "hide" or "show"
				function fnToggleButtons( iAction) {
					 // Primary "Print" button
					 $('button.btn.btn-primary.btn-sm.primary-action')
					 .filter(function () {
						 return $(this).text().trim() === __('Print');
					 })[iAction]();

				 // Secondary buttons: Full Page & PDF (with translation support)
				 $('button.btn.btn-default.btn-sm.ellipsis').filter(function () {
					 return [__('Full Page'), __('PDF')].includes($(this).text().trim());
				 })[iAction]();
				}

				// Use `workflow state` instead of `status` for reliability
				if (this.frm.doctype === "Quotation" && 
					this.frm.doc.workflow_state && 
					(!["Approved", "Self Approved"].includes(this.frm.doc.workflow_state))) {

					// Hide Print Button
					// $(".btn.btn-primary.btn-sm.primary-action").hide();

					// // Hide Full Page Button
					// $('button:has(use[href="#icon-full-page"])').hide();

					// // Hide PDF Button
					// $('button:has(use[href="#icon-small-file"])').hide();
					fnToggleButtons("hide");
					
				} else {
					// $(".btn.btn-primary.btn-sm.primary-action").show();
					// $('button:has(use[href="#icon-full-page"])').show();
					// $('button:has(use[href="#icon-small-file"])').show();
					fnToggleButtons("show");
				}
				// Call the original method safely
				fnOriginalSetTitle.call(this);
			} catch (error) {
				console.log("Custom print button override failed:", error);
			}
		};
	} else {
		console.log("frappe.ui.form.PrintView.set_title not found to execute custtom print button override. Override skipped.");
	}
})();



