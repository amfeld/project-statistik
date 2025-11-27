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
            total_costs_net = 0.0
            total_costs_with_tax = 0.0
            profit_loss = 0.0
            negative_difference = 0.0
            total_hours_booked = 0.0
            labor_costs = 0.0

            # Get the analytic account associated with the project (plan_id=1)
            analytic_account = project.analytic_account_id if hasattr(project, 'analytic_account_id') else None
            if not analytic_account:
                analytic_account = project.account_id if hasattr(project, 'account_id') else None

            if not analytic_account:
                _logger.warning(f"Project {project.id} has no analytic account - skipping financial computation")
                project.customer_invoiced_amount = 0.0
                project.customer_paid_amount = 0.0
                project.customer_outstanding_amount = 0.0
                project.vendor_bills_total = 0.0
                project.total_costs_net = 0.0
                project.total_costs_with_tax = 0.0
                project.profit_loss = 0.0
                project.negative_difference = 0.0
                project.total_hours_booked = 0.0
                project.labor_costs = 0.0
                continue

            # Track processed invoices to avoid duplicates
            processed_customer_invoices = set()
            processed_vendor_bills = set()

            # 1. Calculate Customer Invoices (Revenue)
            customer_data = self._get_customer_invoices_from_analytic(analytic_account, processed_customer_invoices)
            customer_invoiced_amount = customer_data['invoiced']
            customer_paid_amount = customer_data['paid']

            # 2. Calculate Vendor Bills (Direct Costs)
            vendor_data = self._get_vendor_bills_from_analytic(analytic_account, processed_vendor_bills)
            vendor_bills_total = vendor_data['total']

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

            # 6. Calculate Profit/Loss
            profit_loss = customer_paid_amount - (vendor_bills_total + total_costs_net)
            negative_difference = abs(min(0, profit_loss))

            # Update all computed fields
            project.customer_invoiced_amount = customer_invoiced_amount
            project.customer_paid_amount = customer_paid_amount
            project.customer_outstanding_amount = customer_outstanding_amount
            project.vendor_bills_total = vendor_bills_total
            project.total_costs_net = total_costs_net
            project.total_costs_with_tax = total_costs_with_tax
            project.profit_loss = profit_loss
            project.negative_difference = negative_difference
            project.total_hours_booked = total_hours_booked
            project.labor_costs = labor_costs

    def _get_customer_invoices_from_analytic(self, analytic_account, processed_invoices):
        """
        Get customer invoices via analytic_distribution in account.move.line.
        This is the Odoo v18 way to link invoices to projects.
        """
        result = {'invoiced': 0.0, 'paid': 0.0}

        # Find all posted customer invoice lines with this analytic account
        invoice_lines = self.env['account.move.line'].search([
            ('analytic_distribution', '!=', False),
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', '=', 'out_invoice')
        ])

        for line in invoice_lines:
            if not line.analytic_distribution:
                continue

            # Parse the analytic_distribution JSON
            try:
                distribution = line.analytic_distribution
                if isinstance(distribution, str):
                    distribution = json.loads(distribution)

                # Check if this project's analytic account is in the distribution
                if str(analytic_account.id) in distribution:
                    invoice = line.move_id

                    # Avoid counting the same invoice multiple times
                    if invoice.id not in processed_invoices:
                        processed_invoices.add(invoice.id)

                        # Get the percentage allocated to this project
                        percentage = distribution.get(str(analytic_account.id), 0.0) / 100.0

                        # Calculate invoiced and paid amounts
                        invoiced_amount = invoice.amount_total * percentage
                        paid_amount = (invoice.amount_total - invoice.amount_residual) * percentage

                        result['invoiced'] += invoiced_amount
                        result['paid'] += paid_amount

            except Exception as e:
                _logger.warning(f"Error parsing analytic_distribution for line {line.id}: {e}")
                continue

        return result

    def _get_vendor_bills_from_analytic(self, analytic_account, processed_bills):
        """
        Get vendor bills via analytic_distribution in account.move.line.
        This is the Odoo v18 way to link bills to projects.
        """
        result = {'total': 0.0}

        # Find all posted vendor bill lines with this analytic account
        bill_lines = self.env['account.move.line'].search([
            ('analytic_distribution', '!=', False),
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', '=', 'in_invoice')
        ])

        for line in bill_lines:
            if not line.analytic_distribution:
                continue

            # Parse the analytic_distribution JSON
            try:
                distribution = line.analytic_distribution
                if isinstance(distribution, str):
                    distribution = json.loads(distribution)

                # Check if this project's analytic account is in the distribution
                if str(analytic_account.id) in distribution:
                    bill = line.move_id

                    # Avoid counting the same bill multiple times
                    if bill.id not in processed_bills:
                        processed_bills.add(bill.id)

                        # Get the percentage allocated to this project
                        percentage = distribution.get(str(analytic_account.id), 0.0) / 100.0

                        # Calculate bill amount
                        bill_amount = bill.amount_total * percentage

                        result['total'] += bill_amount

            except Exception as e:
                _logger.warning(f"Error parsing analytic_distribution for bill line {line.id}: {e}")
                continue

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
        """
        total_costs_with_tax = labor_costs + other_costs

        # Get all cost lines with tax information
        cost_lines = self.env['account.analytic.line'].search([
            ('account_id', '=', analytic_account.id),
            ('amount', '<', 0)
        ])

        for line in cost_lines:
            if line.move_line_id and line.move_line_id.tax_ids:
                line_amount = abs(line.amount)
                for tax in line.move_line_id.tax_ids:
                    if tax.amount_type == 'percent':
                        tax_amount = line_amount * (tax.amount / 100.0)
                        total_costs_with_tax += tax_amount
                    elif tax.amount_type == 'fixed':
                        total_costs_with_tax += tax.amount

        return total_costs_with_tax