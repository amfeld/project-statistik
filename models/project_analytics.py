from odoo import models, fields, api, _
import logging
import json

_logger = logging.getLogger(__name__)


class ProjectAnalytics(models.Model):
    _inherit = 'project.project'
    _description = _('Project Analytics Extension')

    project_id_display = fields.Char(
        string='Project ID',
        compute='_compute_project_id_display',
        store=True,
        help="Unique identifier for this project"
    )
    client_name = fields.Char(
        string='Name of Client',
        related='partner_id.name',
        store=True,
        help="The customer/client this project is for. This is automatically filled from the project's partner."
    )
    head_of_project = fields.Char(
        string='Head of Project',
        related='user_id.name',
        store=True,
        help="The person responsible for managing this project. This is the project manager assigned to the project."
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        readonly=True,
        help="Reference to the project record"
    )

    # Customer Invoice fields
    customer_invoiced_amount = fields.Float(
        string='Total Invoiced Amount',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Total amount invoiced to customers for this project. This includes all posted customer invoices and credit notes that are linked to this project via analytic distribution."
    )
    customer_paid_amount = fields.Float(
        string='Total Paid Amount',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Total amount actually paid by customers for this project. This is calculated from invoice payments and shows how much money has actually been received."
    )
    customer_outstanding_amount = fields.Float(
        string='Outstanding Amount',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Amount still owed by customers for this project. This is the difference between what has been invoiced and what has been paid (Invoiced - Paid). A positive value means money is still owed."
    )

    # Vendor Bill fields
    vendor_bills_total = fields.Float(
        string='Vendor Bills Total',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Total amount of vendor bills (Lieferantenrechnungen) for this project. This includes all posted vendor bills and refunds linked to this project via analytic distribution. These are external costs from suppliers."
    )

    # Skonto (Cash Discount) fields
    customer_skonto_taken = fields.Float(
        string='Customer Cash Discounts (Skonto)',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Cash discounts granted to customers for early payment (Gewährte Skonti). This reduces project revenue. Calculated from expense accounts 7300-7303 and liability account 2130."
    )
    vendor_skonto_received = fields.Float(
        string='Vendor Cash Discounts Received',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Cash discounts received from vendors for early payment (Erhaltene Skonti). This reduces project costs and increases profit. Calculated from income accounts 4730-4733 and asset account 2670."
    )

    # Cost fields
    total_costs_net = fields.Float(
        string='Net Costs (without tax)',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Internal project costs without tax (Nettokosten). This includes labor costs from timesheets plus other internal costs. Vendor bills are tracked separately. This is the net amount before tax."
    )
    total_costs_with_tax = fields.Float(
        string='Total Costs (with tax)',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Internal project costs with tax included (Bruttokosten). This is the total internal costs including VAT. Vendor bills are tracked separately and already include their taxes."
    )

    # Summary fields
    profit_loss = fields.Float(
        string='Profit/Loss Amount',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Project profitability (Gewinn/Verlust). Calculated as: (Invoiced Amount - Customer Skonto) - (Vendor Bills - Vendor Skonto + Internal Net Costs). A positive value indicates profit, negative indicates loss."
    )
    negative_difference = fields.Float(
        string='Negative Differences (losses)',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Total project losses as a positive number (Verluste). This shows the absolute value of negative profit/loss. If profit/loss is positive, this field is 0. Useful for tracking and reporting total losses."
    )

    # Labor/Timesheet fields
    total_hours_booked = fields.Float(
        string='Total Hours Booked',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Total hours logged in timesheets for this project (Gebuchte Stunden). This includes all timesheet entries from employees working on this project. Used to track resource utilization and calculate labor costs."
    )
    labor_costs = fields.Float(
        string='Labor Costs',
        compute='_compute_financial_data',
        store=True,
        group_operator='sum',
        help="Total cost of labor based on timesheets (Personalkosten). Calculated from timesheet entries multiplied by employee hourly rates. This is a major component of internal project costs."
    )

    @api.depends('project_id')
    def _compute_project_id_display(self):
        for record in self:
            record.project_id_display = str(record.id)

    @api.depends('partner_id', 'user_id')
    def _compute_financial_data(self):
        """
        Compute all financial data for the project based on analytic account lines (plan_id=1).
        This is the single source of truth for Odoo v18 German accounting.

        Note: We depend on partner_id and user_id (guaranteed core fields) rather than
        account_id or sale_line_id which may not exist if certain modules aren't installed.
        The actual financial data is computed from account.analytic.line records.
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

            # 2. Calculate Vendor Bills (Direct Costs)
            vendor_data = self._get_vendor_bills_from_analytic(analytic_account)
            vendor_bills_total = vendor_data['total']

            # 3. Calculate Skonto (Cash Discounts) from analytic lines
            skonto_data = self._get_skonto_from_analytic(analytic_account)
            customer_skonto_taken = skonto_data['customer_skonto']
            vendor_skonto_received = skonto_data['vendor_skonto']

            # 4. Calculate Labor Costs (Timesheets)
            timesheet_data = self._get_timesheet_costs(analytic_account)
            total_hours_booked = timesheet_data['hours']
            labor_costs = timesheet_data['costs']

            # 5. Calculate Other Costs (non-timesheet, non-bill analytic lines)
            other_costs = self._get_other_costs_from_analytic(analytic_account)

            # 6. Calculate totals
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
        """
        result = {'invoiced': 0.0, 'paid': 0.0}

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

                    # Calculate paid amount for this line
                    # Payment proportion = (invoice.amount_total - invoice.amount_residual) / invoice.amount_total
                    if abs(invoice.amount_total) > 0:
                        payment_ratio = (invoice.amount_total - invoice.amount_residual) / invoice.amount_total
                        line_paid = line_amount * payment_ratio
                        result['paid'] += line_paid

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
        """
        result = {'total': 0.0}

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

            except Exception as e:
                _logger.warning(f"Error parsing analytic_distribution for bill line {line.id}: {e}")
                continue

        return result

    def _get_skonto_from_analytic(self, analytic_account):
        """
        Get Skonto (cash discounts) by querying analytic lines from discount accounts.

        This is a simpler and more reliable approach than analyzing reconciliation.
        Skonto entries are typically posted to specific accounts with analytic distribution.

        Customer Skonto (Gewährte Skonti):
        - Accounts 7300-7303 (expense - reduces profit)
        - Account 2130 (liability account for customer discounts)

        Vendor Skonto (Erhaltene Skonti):
        - Accounts 4730-4733 (income - increases profit)
        - Account 2670 (asset account for vendor discounts)

        Returns:
            dict: {'customer_skonto': amount, 'vendor_skonto': amount}
        """
        result = {'customer_skonto': 0.0, 'vendor_skonto': 0.0}

        # Get all analytic lines for this account
        analytic_lines = self.env['account.analytic.line'].search([
            ('account_id', '=', analytic_account.id)
        ])

        for line in analytic_lines:
            if not line.move_line_id or not line.move_line_id.account_id:
                continue

            account_code = line.move_line_id.account_id.code
            if not account_code:
                continue

            # Customer Skonto (Gewährte Skonti) - expense accounts 7300-7303 + liability 2130
            # These reduce our revenue/profit (customer got discount)
            if account_code.startswith(('7300', '7301', '7302', '7303', '2130')):
                result['customer_skonto'] += abs(line.amount)

            # Vendor Skonto (Erhaltene Skonti) - income accounts 4730-4733 + asset 2670
            # These increase our profit (we got discount from vendor)
            elif account_code.startswith(('4730', '4731', '4732', '4733', '2670')):
                result['vendor_skonto'] += abs(line.amount)

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

    def action_view_account_analytic_line(self):
        """
        Open analytic lines for this project.
        Shows all account.analytic.line records associated with the project's analytic account.
        """
        self.ensure_one()

        # Get the analytic account
        analytic_account = None
        if hasattr(self, 'analytic_account_id') and self.analytic_account_id:
            analytic_account = self.analytic_account_id
        elif hasattr(self, 'account_id') and self.account_id:
            analytic_account = self.account_id

        if not analytic_account:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _('No analytic account found for this project.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        return {
            'type': 'ir.actions.act_window',
            'name': f'Analytic Lines - {self.name}',
            'res_model': 'account.analytic.line',
            'view_mode': 'tree,form',
            'domain': [('account_id', '=', analytic_account.id)],
            'context': {'default_account_id': analytic_account.id},
            'target': 'current',
        }

    def action_open_project_dashboard(self):
        """
        Open the standard project dashboard/form view for this project.
        Called when clicking a row in the analytics list view.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.project',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': False,  # Use default project form view
            'target': 'current',
        }

    def action_open_standard_project_form(self):
        """
        Open the standard Odoo project form view.
        Called from the analytics form view button.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.project',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': False,  # Use default project form view
            'target': 'current',
        }

    def action_open_analytics_form(self):
        """
        Open the project analytics form view.
        Called from the standard project form view button.
        """
        self.ensure_one()
        # Get the analytics form view ID
        analytics_form_view = self.env.ref('project_statistic.view_project_form_account_analytics', raise_if_not_found=False)

        return {
            'type': 'ir.actions.act_window',
            'name': f'Analytics - {self.name}',
            'res_model': 'project.project',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': analytics_form_view.id if analytics_form_view else False,
            'target': 'current',
        }