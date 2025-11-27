# Project Financial Analytics for Odoo v18

## What does this module do?

This module provides comprehensive financial analytics for your projects by tracking all revenue, costs, and profitability in real-time. It's specifically designed for Odoo v18 German accounting and uses analytic accounts as the single source of truth.

## What information does it calculate?

For each project, it shows:

### Revenue (Customer Invoices)
- **Total Invoiced Amount**: Total amount invoiced to customers for this project
- **Total Paid Amount**: Money actually received from customers
- **Outstanding Amount**: Money still owed by customers (Invoiced - Paid)

### Costs
- **Vendor Bills Total**: Total amount of vendor bills for this project
- **Net Costs (without tax)**: Labor costs + other costs (excluding vendor bills)
- **Total Costs (with tax)**: Net costs with VAT/taxes included

### Profitability
- **Profit/Loss Amount**: Revenue minus all costs
- **Negative Differences**: Absolute value of losses (for easy reporting)

### Labor
- **Total Hours Booked**: Total hours logged in timesheets
- **Labor Costs**: Cost of labor based on employee rates

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
Revenue:
- Invoiced to customer: €10,000
- Customer paid: €8,000
- Outstanding: €2,000

Costs:
- Vendor bills: €3,000
- Labor costs: €2,000
- Other costs: €500
- Net costs: €2,500
- Total costs with tax: €2,975

Result:
- Profit/Loss: €8,000 - €3,000 - €2,500 = €2,500 profit
```

This helps you instantly see which projects are profitable and which need attention!