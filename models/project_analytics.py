from odoo import models, fields, api, _
import logging
import json

_logger = logging.getLogger(__name__)


class ProjectAnalytics(models.Model):
    _inherit = 'project.project'

    project_id_display = fields.Char(string='Project ID', compute='_compute_project_id_display', store=True)
    client_name = fields.Char(string='Name of Client', related='partner_id.name', store=True)
    head_of_project = fields.Char(string='Head of Project', related='user_id.name', store=True)
    project_id = fields.Many2one("project.project", string="Project", readonly=True)

    # Customer Invoice fields
    customer_invoiced_amount = fields.Float(
        string='Total Invoiced Amount',
        compute='_compute_financial_data',
        help="Total amount invoiced to customers for this project"
    )
    customer_paid_amount = fields.Float(
        string='Total Paid Amount',
        compute='_compute_financial_data',
        help="Total amount actually paid by customers"
    )
    customer_outstanding_amount = fields.Float(
        string='Outstanding Amount',
        compute='_compute_financial_data',
        help="Amount still owed by customers (Invoiced - Paid)"
    )

    # Vendor Bill fields
    vendor_bills_total = fields.Float(
        string='Vendor Bills Total',
        compute='_compute_financial_data',
        help="Total amount of vendor bills for this project"
    )

    # Skonto (Cash Discount) fields
    customer_skonto_taken = fields.Float(
        string='Customer Cash Discounts (Skonto)',
        compute='_compute_financial_data',
        help="Cash discounts taken by customers on early payment (Gewährte Skonti)"
    )
    vendor_skonto_received = fields.Float(
        string='Vendor Cash Discounts Received',
        compute='_compute_financial_data',
        help="Cash discounts received from vendors on early payment (Erhaltene Skonti)"
    )

    # Cost fields
    total_costs_net = fields.Float(
        string='Net Costs (without tax)',
        compute='_compute_financial_data',
        help="Labor costs + other costs (without vendor bills)"
    )
    total_costs_with_tax = fields.Float(
        string='Total Costs (with tax)',
        compute='_compute_financial_data',
        help="Net costs with tax included"
    )

    # Summary fields
    profit_loss = fields.Float(
        string='Profit/Loss Amount',
        compute='_compute_financial_data',
        help="Revenue minus all costs"
    )
    negative_difference = fields.Float(
        string='Negative Differences (losses)',
        compute='_compute_financial_data',
        help="Absolute value of losses"
    )

    # Labor/Timesheet fields
    total_hours_booked = fields.Float(
        string='Total Hours Booked',
        compute='_compute_financial_data',
        help="Total hours logged in timesheets for this project"
    )
    labor_costs = fields.Float(
        string='Labor Costs',
        compute='_compute_financial_data',
        help="Total cost of labor based on timesheets"
    )

    @api.depends('project_id')
    def _compute_project_id_display(self):
        for record in self:
            record.project_id_display = str(record.id)

    def _compute_financial_data(self):
        """
        Compute all financial data for the project based on analytic account lines (plan_id=1).
        This is the single source of truth for Odoo v18 German accounting.
        """
        for project in self:
            # Initialize all fields
            customer_invoiced_amount = 0.0
            customer_paid_amount = 0.0
            customer_outstanding_amount = 0.0
            vendor_bills_total = 0.0
            customer_skonto_taken = 0.0
            vendor_skonto_received = 0.0
            total_costs_net = 0.0
            total_costs_with_tax = 0.0
            profit_loss = 0.0
            negative_difference = 0.0
            total_hours_booked = 0.0
            labor_costs = 0.0

            # Get the analytic account associated with the project (plan_id=1 ONLY)
            analytic_account = None
            if hasattr(project, 'analytic_account_id') and project.analytic_account_id:
                # Verify this is plan_id=1 (project plan in German accounting)
                if hasattr(project.analytic_account_id, 'plan_id') and project.analytic_account_id.plan_id.id == 1:
                    analytic_account = project.analytic_account_id

            # Fallback to account_id if analytic_account_id not found
            if not analytic_account and hasattr(project, 'account_id') and project.account_id:
                if hasattr(project.account_id, 'plan_id') and project.account_id.plan_id.id == 1:
                    analytic_account = project.account_id

            if not analytic_account:
                _logger.warning(f"Project {project.id} has no analytic account - skipping financial computation")
                project.customer_invoiced_amount = 0.0
                project.customer_paid_amount = 0.0
                project.customer_outstanding_amount = 0.0
                project.vendor_bills_total = 0.0
                project.customer_skonto_taken = 0.0
                project.vendor_skonto_received = 0.0
                project.total_costs_net = 0.0
                project.total_costs_with_tax = 0.0
                project.profit_loss = 0.0
                project.negative_difference = 0.0
                project.total_hours_booked = 0.0
                project.labor_costs = 0.0
                continue

            # 1. Calculate Customer Invoices (Revenue)
            customer_data = self._get_customer_invoices_from_analytic(analytic_account)
            customer_invoiced_amount = customer_data['invoiced']
            customer_paid_amount = customer_data['paid']
            customer_skonto_taken = customer_data.get('skonto', 0.0)

            # 2. Calculate Vendor Bills (Direct Costs)
            vendor_data = self._get_vendor_bills_from_analytic(analytic_account)
            vendor_bills_total = vendor_data['total']
            vendor_skonto_received = vendor_data.get('skonto', 0.0)

            # 3. Calculate Labor Costs (Timesheets)
            timesheet_data = self._get_timesheet_costs(analytic_account)
            total_hours_booked = timesheet_data['hours']
            labor_costs = timesheet_data['costs']

            # 4. Calculate Other Costs (non-timesheet, non-bill analytic lines)
            other_costs = self._get_other_costs_from_analytic(analytic_account)

            # 5. Calculate totals
            total_costs_net = labor_costs + other_costs
            total_costs_with_tax = self._calculate_costs_with_tax(analytic_account, labor_costs, other_costs)

            customer_outstanding_amount = customer_invoiced_amount - customer_paid_amount

            # 6. Calculate Profit/Loss (Accrual basis with Skonto adjustments)
            # Revenue: Invoiced amount - Skonto taken by customers
            # Costs: Vendor bills - Skonto received + internal costs
            adjusted_revenue = customer_invoiced_amount - customer_skonto_taken
            adjusted_vendor_costs = vendor_bills_total - vendor_skonto_received
            profit_loss = adjusted_revenue - (adjusted_vendor_costs + total_costs_net)
            negative_difference = abs(min(0, profit_loss))

            # Update all computed fields
            project.customer_invoiced_amount = customer_invoiced_amount
            project.customer_paid_amount = customer_paid_amount
            project.customer_outstanding_amount = customer_outstanding_amount
            project.vendor_bills_total = vendor_bills_total
            project.customer_skonto_taken = customer_skonto_taken
            project.vendor_skonto_received = vendor_skonto_received
            project.total_costs_net = total_costs_net
            project.total_costs_with_tax = total_costs_with_tax
            project.profit_loss = profit_loss
            project.negative_difference = negative_difference
            project.total_hours_booked = total_hours_booked
            project.labor_costs = labor_costs

    def _get_customer_invoices_from_analytic(self, analytic_account):
        """
        Get customer invoices and credit notes via analytic_distribution in account.move.line.
        This is the Odoo v18 way to link invoices to projects.

        IMPORTANT: We must calculate the project portion based on invoice LINE amounts,
        not full invoice amounts, because different lines may go to different projects.

        Handles both:
        - out_invoice: Customer invoices (positive revenue)
        - out_refund: Customer credit notes (negative revenue)

        Also tracks Skonto (cash discounts) taken by customers by analyzing
        reconciled payment entries with discount accounts (7300 range).
        """
        result = {'invoiced': 0.0, 'paid': 0.0, 'skonto': 0.0}

        # Find all posted customer invoice/credit note lines with this analytic account
        # Filter by account_type to ensure we only get revenue/receivable lines
        invoice_lines = self.env['account.move.line'].search([
            ('analytic_distribution', '!=', False),
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', 'in', ['out_invoice', 'out_refund']),
            ('display_type', '=', False),  # Exclude section/note lines
            '|',
            ('account_id.account_type', '=', 'income'),
            ('account_id.account_type', '=', 'income_other')
        ])

        for line in invoice_lines:
            if not line.analytic_distribution:
                continue

            # Skip reversal entries (Storno) - they cancel out the original entry
            if line.move_id.reversed_entry_id or line.move_id.reversal_move_id:
                continue

            # Parse the analytic_distribution JSON
            try:
                distribution = line.analytic_distribution
                if isinstance(distribution, str):
                    distribution = json.loads(distribution)

                # Check if this project's analytic account is in the distribution
                if str(analytic_account.id) in distribution:
                    # Get the percentage allocated to this project for THIS LINE
                    percentage = distribution.get(str(analytic_account.id), 0.0) / 100.0

                    # Get the invoice to calculate payment proportion
                    invoice = line.move_id

                    # Calculate this line's contribution to the project
                    # Use price_total (includes taxes) to match invoice.amount_total
                    line_amount = line.price_total * percentage

                    # Credit notes (out_refund) reduce revenue, so subtract them
                    if invoice.move_type == 'out_refund':
                        line_amount = -abs(line_amount)  # Ensure negative

                    result['invoiced'] += line_amount

                    # Calculate actual payments and Skonto for this line
                    # by analyzing the reconciled entries
                    if abs(invoice.amount_total) > 0:
                        payment_data = self._calculate_line_payment_and_skonto(
                            line, invoice, line_amount, percentage, is_customer=True
                        )
                        result['paid'] += payment_data['paid']
                        result['skonto'] += payment_data['skonto']

            except Exception as e:
                _logger.warning(f"Error parsing analytic_distribution for line {line.id}: {e}")
                continue

        return result

    def _get_vendor_bills_from_analytic(self, analytic_account):
        """
        Get vendor bills and refunds via analytic_distribution in account.move.line.
        This is the Odoo v18 way to link bills to projects.

        IMPORTANT: We must calculate the project portion based on bill LINE amounts,
        not full bill amounts, because different lines may go to different projects.

        Handles both:
        - in_invoice: Vendor bills (positive cost)
        - in_refund: Vendor refunds (negative cost)

        Also tracks Skonto (cash discounts) received from vendors by analyzing
        reconciled payment entries with discount accounts (4730 range).
        """
        result = {'total': 0.0, 'skonto': 0.0}

        # Find all posted vendor bill/refund lines with this analytic account
        # Filter by account_type to ensure we only get expense/payable lines
        bill_lines = self.env['account.move.line'].search([
            ('analytic_distribution', '!=', False),
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', 'in', ['in_invoice', 'in_refund']),
            ('display_type', '=', False),  # Exclude section/note lines
            ('account_id.account_type', '=', 'expense')
        ])

        for line in bill_lines:
            if not line.analytic_distribution:
                continue

            # Skip reversal entries (Storno) - they cancel out the original entry
            if line.move_id.reversed_entry_id or line.move_id.reversal_move_id:
                continue

            # Parse the analytic_distribution JSON
            try:
                distribution = line.analytic_distribution
                if isinstance(distribution, str):
                    distribution = json.loads(distribution)

                # Check if this project's analytic account is in the distribution
                if str(analytic_account.id) in distribution:
                    # Get the percentage allocated to this project for THIS LINE
                    percentage = distribution.get(str(analytic_account.id), 0.0) / 100.0

                    # Get the bill to check type
                    bill = line.move_id

                    # Calculate this line's contribution to the project
                    # Use price_total (includes taxes) to match bill.amount_total
                    line_amount = line.price_total * percentage

                    # Vendor refunds (in_refund) reduce costs, so subtract them
                    if bill.move_type == 'in_refund':
                        line_amount = -abs(line_amount)  # Ensure negative

                    result['total'] += line_amount

                    # Calculate Skonto received from vendor for this line
                    if abs(bill.amount_total) > 0:
                        payment_data = self._calculate_line_payment_and_skonto(
                            line, bill, line_amount, percentage, is_customer=False
                        )
                        result['skonto'] += payment_data['skonto']

            except Exception as e:
                _logger.warning(f"Error parsing analytic_distribution for bill line {line.id}: {e}")
                continue

        return result

    def _calculate_line_payment_and_skonto(self, line, move, line_amount, percentage, is_customer=True):
        """
        Calculate actual payment and Skonto for a specific invoice/bill line.

        This method analyzes the reconciled entries on the invoice/bill to:
        1. Track actual payments received/made
        2. Identify cash discount (Skonto) entries

        Args:
            line: The invoice/bill line (account.move.line)
            move: The invoice/bill (account.move)
            line_amount: The calculated line amount for this project
            percentage: The project percentage for this line
            is_customer: True for customer invoices, False for vendor bills

        Returns:
            dict: {'paid': amount_paid, 'skonto': skonto_amount}
        """
        result = {'paid': 0.0, 'skonto': 0.0}

        # Get the receivable/payable line from the invoice/bill
        if is_customer:
            account_type = 'asset_receivable'
            skonto_accounts = ['7300', '7301', '7302', '7303']  # Gewährte Skonti (expense)
        else:
            account_type = 'liability_payable'
            skonto_accounts = ['4730', '4731', '4732', '4733']  # Erhaltene Skonti (income)

        # Find the receivable/payable line for this invoice/bill
        receivable_lines = move.line_ids.filtered(
            lambda l: l.account_id.account_type == account_type and not l.reconciled == False
        )

        if not receivable_lines:
            # No payment info available, use residual calculation
            if abs(move.amount_total) > 0:
                payment_ratio = (move.amount_total - move.amount_residual) / move.amount_total
                result['paid'] = line_amount * payment_ratio
            return result

        # Analyze reconciliation to find payments and Skonto
        for rec_line in receivable_lines:
            if not rec_line.matched_debit_ids and not rec_line.matched_credit_ids:
                continue

            # Get all reconciled entries (payments and discounts)
            reconciled_items = rec_line.matched_debit_ids + rec_line.matched_credit_ids

            for item in reconciled_items:
                # Get the counterpart line (payment or discount)
                counterpart_line = item.debit_move_id if item.credit_move_id == rec_line else item.credit_move_id

                if not counterpart_line:
                    continue

                # Calculate the proportion of this reconciliation item
                if abs(move.amount_total) > 0:
                    item_ratio = abs(item.amount) / abs(move.amount_total)
                else:
                    continue

                # Check if this is a Skonto entry (discount account)
                is_skonto = any(
                    counterpart_line.account_id.code and counterpart_line.account_id.code.startswith(acc_code)
                    for acc_code in skonto_accounts
                )

                if is_skonto:
                    # This is a cash discount entry
                    skonto_for_line = line_amount * item_ratio
                    result['skonto'] += abs(skonto_for_line)
                else:
                    # This is a regular payment
                    payment_for_line = line_amount * item_ratio
                    result['paid'] += abs(payment_for_line)

        return result

    def _get_timesheet_costs(self, analytic_account):
        """
        Get timesheet hours and costs from account.analytic.line.
        Timesheets have is_timesheet=True.
        """
        result = {'hours': 0.0, 'costs': 0.0}

        # Find all timesheet lines for this analytic account
        timesheet_lines = self.env['account.analytic.line'].search([
            ('account_id', '=', analytic_account.id),
            ('is_timesheet', '=', True)
        ])

        for line in timesheet_lines:
            result['hours'] += line.unit_amount or 0.0
            result['costs'] += abs(line.amount or 0.0)

        return result

    def _get_other_costs_from_analytic(self, analytic_account):
        """
        Get other costs from analytic lines that are:
        - NOT timesheets (is_timesheet=False)
        - NOT from vendor bills (no move_line_id with in_invoice)
        - Negative amounts (costs are negative in Odoo)
        """
        other_costs = 0.0

        # Find all cost lines (negative amounts, not timesheets)
        cost_lines = self.env['account.analytic.line'].search([
            ('account_id', '=', analytic_account.id),
            ('amount', '<', 0),
            ('is_timesheet', '=', False)
        ])

        for line in cost_lines:
            # Check if this line is NOT from a vendor bill
            is_from_vendor_bill = False
            if line.move_line_id:
                move = line.move_line_id.move_id
                if move and move.move_type == 'in_invoice':
                    is_from_vendor_bill = True

            # Only count if it's not from a vendor bill
            if not is_from_vendor_bill:
                other_costs += abs(line.amount)

        return other_costs

    def _calculate_costs_with_tax(self, analytic_account, labor_costs, other_costs):
        """
        Calculate total costs with tax included.
        In German accounting, we need to add VAT to costs.

        IMPORTANT: account.analytic.line.amount is typically the NET amount (without tax).
        We need to add the tax from the related move_line_id to get the total with tax.

        Note: We only add tax for lines that have a move_line_id (journal entries).
        Labor costs from timesheets typically don't have taxes at this level.
        """
        total_costs_with_tax = labor_costs + other_costs

        # Get all cost lines that have journal entry references (these might have taxes)
        cost_lines = self.env['account.analytic.line'].search([
            ('account_id', '=', analytic_account.id),
            ('amount', '<', 0),
            ('move_line_id', '!=', False)  # Only lines with journal entries
        ])

        for line in cost_lines:
            # Skip if already counted in vendor_bills_total (to avoid double counting)
            if line.move_line_id and line.move_line_id.move_id:
                move = line.move_line_id.move_id
                if move.move_type in ['in_invoice', 'in_refund']:
                    # This is from a vendor bill, tax already included in vendor_bills_total
                    continue

            # Add tax for non-vendor-bill expense lines
            if line.move_line_id and line.move_line_id.tax_ids:
                line_amount = abs(line.amount)
                for tax in line.move_line_id.tax_ids:
                    if tax.amount_type == 'percent':
                        tax_amount = line_amount * (tax.amount / 100.0)
                        total_costs_with_tax += tax_amount
                    elif tax.amount_type == 'fixed':
                        total_costs_with_tax += tax.amount

        return total_costs_with_tax