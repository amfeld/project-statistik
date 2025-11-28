# Project Financial Analytics for Odoo v18

## What does this module do?

This module provides comprehensive financial analytics for your projects by tracking all revenue, costs, and profitability in real-time. It's specifically designed for Odoo v18 German accounting and uses analytic accounts as the single source of truth.

## What information does it calculate?

For each project, it shows:

### Revenue (Customer Invoices)
- **Total Invoiced Amount**: Total amount invoiced to customers for this project (**WITH TAX** - gross amount)
- **Total Paid Amount**: Money actually received from customers (**WITH TAX** - gross amount)
- **Outstanding Amount**: Money still owed by customers (Invoiced - Paid) (**WITH TAX**)

### Costs
- **Vendor Bills Total**: Total amount of vendor bills for this project (**WITH TAX** - includes VAT)
- **Net Costs (without tax)**: Labor costs + other costs (excluding vendor bills) (**WITHOUT TAX** - net amount)
- **Total Costs (with tax)**: Net costs with VAT/taxes included (**WITH TAX**)

### Profitability
- **Profit/Loss Amount**: Revenue minus all costs (**calculated from invoiced amounts, accrual basis**)
- **Negative Differences**: Absolute value of losses (for easy reporting)

### Labor
- **Total Hours Booked**: Total hours logged in timesheets (in hours)
- **Labor Costs**: Cost of labor based on employee rates (**WITHOUT TAX** - net amount)

---

### Quick Reference: Net vs. Gross Amounts

| Field | Tax Status | Description |
|-------|-----------|-------------|
| Total Invoiced Amount | **WITH TAX** 🟢 | Gross amount from customer invoices |
| Total Paid Amount | **WITH TAX** 🟢 | Gross amount received from customers |
| Outstanding Amount | **WITH TAX** 🟢 | Gross amount still owed |
| Vendor Bills Total | **WITH TAX** 🟢 | Gross vendor bill amounts (includes VAT) |
| Labor Costs | **WITHOUT TAX** 🔵 | Net labor costs |
| Net Costs | **WITHOUT TAX** 🔵 | Labor + other costs (net) |
| Total Costs (with tax) | **WITH TAX** 🟢 | Net costs + calculated VAT |
| Profit/Loss Amount | **MIXED** ⚠️ | Invoiced (gross) - Vendor Bills (gross) - Net Costs (net) |

**Important Notes:**
- **Profit/Loss Formula:** `customer_invoiced_amount (gross) - vendor_bills_total (gross) - total_costs_net (net)`
- Revenue (invoiced/paid) uses **line.price_total** which includes taxes
- Vendor bills use **line.price_total** which includes taxes
- Internal costs (labor, other) are typically **net amounts** from analytic lines
- Tax is added separately to net costs in "Total Costs (with tax)"

---

## 💰 Skonto (Cash Discount) Tracking

This module properly tracks **Skonto** (cash discounts) in German accounting!

### What is Skonto?

**Skonto** is a cash discount offered/received for early payment, very common in German business:

**Example - Customer Invoice:**
```
Invoice Amount: €10,000 (payment terms: 2% discount within 10 days)
Customer pays early: €9,800
Skonto taken: €200 (booked to account 7300 "Gewährte Skonti")
```

**Example - Vendor Bill:**
```
Bill Amount: €5,000 (payment terms: 2% discount within 10 days)
We pay early: €4,900
Skonto received: €100 (booked to account 4730 "Erhaltene Skonti")
```

### How It Works

The module queries **analytic lines directly from Skonto accounts**:

1. **Finds all analytic lines** for the project's analytic account
2. **Filters by account code** to identify Skonto entries:
   - **Customer Skonto (Gewährte Skonti)**: Accounts 7300-7303
   - **Vendor Skonto (Erhaltene Skonti)**: Accounts 4730-4733
3. **Sums up amounts** - Only Skonto entries with analytic distribution are included

**Why This Approach:**
- ✅ Simple and reliable - queries account.analytic.line directly
- ✅ Uses Odoo's standard analytic distribution
- ✅ Only tracks Skonto properly allocated to projects
- ✅ Works with any payment method or reconciliation structure
- ✅ No complex reconciliation analysis needed

### Impact on Profit Calculation

```python
# Adjusted Revenue (what we actually receive)
adjusted_revenue = customer_invoiced_amount - customer_skonto_taken

# Adjusted Costs (what we actually pay)
adjusted_vendor_costs = vendor_bills_total - vendor_skonto_received

# Final Profit/Loss
profit_loss = adjusted_revenue - adjusted_vendor_costs - total_costs_net
```

### Fields in Views

- **Customer Cash Discounts (Skonto)**: Shows total Skonto taken by customers (reduces revenue)
- **Vendor Cash Discounts Received**: Shows total Skonto received from vendors (reduces costs)

Both fields are **hidden by default** in list view - enable them in optional columns if needed.

---

## How does it work?

The module uses Odoo v18's analytic distribution system to track all financial data:

### 1. Analytic Account (plan_id=1)
Every project has an analytic account that serves as the central tracking point for all financial transactions.

### 2. Customer Invoices
- Finds invoice lines with `analytic_distribution` pointing to the project
- Calculates invoiced amount per line (handles partial project allocation)
- Determines paid amount using `amount_residual` from invoices
- **Payment Calculation**: `(invoice.amount_total - invoice.amount_residual) / invoice.amount_total * line_amount`

### 3. Vendor Bills
- Finds bill lines with `analytic_distribution` pointing to the project
- Calculates bill amount per line (handles partial project allocation)

### 4. Labor Costs
- Gets all timesheet entries (`is_timesheet=True`) for the analytic account
- Sums hours and costs

### 5. Other Costs
- Gets analytic lines that are:
  - NOT timesheets
  - NOT from vendor bills
  - Have negative amounts (costs are negative in Odoo)

## Calculation Logic

### Total Paid Amount - Waterproof Implementation

The payment calculation is **line-based**, not invoice-based, to handle complex scenarios correctly:

**Example Scenario:**
```
Invoice #123 Total: €10,000 (80% paid = €8,000 received)

Line 1: Service A (€6,000) → 100% to Project X
Line 2: Service B (€4,000) → 100% to Project Y

Correct Calculation:
- Payment ratio = €8,000 / €10,000 = 0.8 (80%)
- Project X invoiced: €6,000
- Project X paid: €6,000 * 0.8 = €4,800 ✓
- Project Y invoiced: €4,000
- Project Y paid: €4,000 * 0.8 = €3,200 ✓
- Total paid: €8,000 ✓
```

**Why This Is Waterproof:**
1. Each invoice line is processed individually
2. Payment ratio is calculated from the full invoice
3. Line payment = Line amount × Payment ratio
4. Handles partial payments correctly
5. Handles multi-project invoices correctly
6. Excludes display lines (sections, notes)

## When does it calculate?

Calculations happen **in real-time** when you view:
- Project Analytics Dashboard (Accounting → Project Analytics → Dashboard)
- List view with financial columns
- Pivot view with financial measures

## Technical Details (Odoo v18 Compatibility)

### Core Features
- Uses `analytic_distribution` JSON field (new in Odoo v18)
- Handles percentage-based project allocation
- Uses `parent_state='posted'` for invoice/bill lines
- Filters out display lines (`display_type=False`)
- Compatible with German chart of accounts
- No `store=True` on computed fields (ensures real-time accuracy)
- **Only uses analytic plan_id=1** (project plan in German accounting)

### Handles All Document Types
- ✅ Customer Invoices (`out_invoice`)
- ✅ Customer Credit Notes (`out_refund`) - reduces revenue
- ✅ Vendor Bills (`in_invoice`)
- ✅ Vendor Refunds (`in_refund`) - reduces costs
- ✅ Timesheets with labor costs
- ✅ Other expense entries

### Additional Security Features

**1. Account Type Validation**
- Customer invoices: Only includes 'income' and 'income_other' account types
- Vendor bills: Only includes 'expense' account types
- Prevents wrong account types from affecting calculations

**2. Reversal Entry Handling (Storno)**
- Automatically skips reversal entries (`reversed_entry_id` or `reversal_move_id`)
- Prevents double-counting when entries are reversed
- Common in German accounting for corrections

**3. Skonto (Cash Discount) Tracking**
- Analyzes payment reconciliations to detect Skonto
- Customer Skonto (Gewährte Skonti): Accounts 7300-7303
- Vendor Skonto (Erhaltene Skonti): Accounts 4730-4733
- Proportionally allocated to projects
- See detailed Skonto section above

### Bug Fixes Applied

**1. No Double-Counting of Vendor Bills**
- Vendor bills are counted ONLY in `vendor_bills_total`
- Tax calculation explicitly excludes vendor bill taxes (already in bill total)
- Other costs exclude lines from vendor bills

**2. Correct Tax Calculation**
- Taxes added only for non-vendor-bill expense lines
- Vendor bill taxes already included in `line.price_total`
- No double-counting of taxes

**3. Credit Notes & Refunds Handled**
- Customer credit notes reduce invoiced/paid amounts
- Vendor refunds reduce vendor bill totals
- Correctly handles negative amounts

**4. Accrual-Based Profit Calculation**
- Profit = **Invoiced** - Costs (not just paid amount)
- Follows German accounting standards (accrual basis)
- Outstanding amounts tracked separately

**5. Line-Based Payment Calculation**
- Each invoice line calculated independently
- Payment ratio applied per line
- Handles multi-project invoices correctly

## Simple Example

**Project ABC:**
```
REVENUE (WITH TAX - GROSS):
- Invoiced to customer: €10,000 (gross, includes 19% VAT)
- Customer paid: €8,000 (gross, 80% of invoice paid)
- Outstanding: €2,000 (gross)

COSTS:
- Vendor bills: €3,000 (gross, includes 19% VAT)
- Labor costs: €2,000 (net, no VAT on internal labor)
- Other costs: €500 (net)
- Net costs total: €2,500 (net = labor + other)
- Total costs with tax: €2,975 (net + calculated VAT on applicable items)

PROFITABILITY (ACCRUAL BASIS):
- Profit/Loss: €10,000 (gross invoiced) - €3,000 (gross vendor bills) - €2,500 (net costs) = €4,500 profit

BREAKDOWN:
- We compare GROSS revenue (€10,000)
- Against GROSS vendor bills (€3,000)
- Against NET internal costs (€2,500)
- Result: €4,500 profit (before considering taxes on internal costs)
```

**Why This Makes Sense:**
- Customer invoices and vendor bills naturally include VAT (external transactions)
- Internal costs (labor, expenses) are tracked net, taxes calculated separately
- This matches how German accounting typically tracks project profitability
- Outstanding amount (€2,000) shows cash flow needs

This helps you instantly see which projects are profitable and which need attention!

---

## 🗑️ Module Uninstallation

This module follows **Odoo best practices for clean uninstallation**.

### What Happens on Uninstall

When you uninstall this module, the `uninstall_hook` automatically:

1. **Removes all computed stored fields** from the `project_project` table
2. **Cleans up database columns** to prevent orphaned data
3. **Ensures clean reinstallation** if you need to reinstall later

### Fields Cleaned Up

All computed fields with `store=True` are removed:
- `customer_invoiced_amount`, `customer_paid_amount`, `customer_outstanding_amount`
- `customer_skonto_taken`, `vendor_skonto_received`
- `vendor_bills_total`
- `total_costs_net`, `total_costs_with_tax`
- `profit_loss`, `negative_difference`
- `total_hours_booked`, `labor_costs`
- `project_id_display`, `client_name`, `head_of_project`

### How It Works

**__init__.py:**
```python
def uninstall_hook(env):
    # Drops all computed field columns from project_project table
    env.cr.execute("ALTER TABLE project_project DROP COLUMN IF EXISTS ...")
```

**__manifest__.py:**
```python
{
    'uninstall_hook': 'uninstall_hook',
}
```

### Why This Matters

❌ **Without uninstall_hook:**
- Database columns remain after uninstall
- Orphaned data clutters your database
- Reinstalling may cause conflicts
- Manual database cleanup needed

✅ **With uninstall_hook:**
- Complete cleanup on uninstall
- No orphaned data
- Clean slate for reinstallation
- Professional module management

**This module can be safely installed and uninstalled without leaving database artifacts!**