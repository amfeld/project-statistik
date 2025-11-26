from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class ProjectAnalytics(models.Model):
    _inherit = 'project.project'

    project_id_display = fields.Char(string='Project ID', compute='_compute_project_id_display', store=True)
    client_name = fields.Char(string='Name of Client', related='partner_id.name', store=True)
    head_of_project = fields.Char(string='Head of Project', related='user_id.name', store=True)
    project_id = fields.Many2one("project.project", string="Project", readonly=True)

    # Enhanced Customer Invoice fields
    customer_total_to_invoice = fields.Float(string='Customer Total to Invoice', compute='_compute_financial_data',
                                             store=True,
                                             help="Total amount that should be invoiced to customer")
    customer_invoiced_amount = fields.Float(string='Customer Invoiced Amount', compute='_compute_financial_data',
                                            store=True,
                                            help="Total amount already invoiced to customer")
    customer_paid_amount = fields.Float(string='Customer Paid Amount', compute='_compute_financial_data', store=True,
                                        help="Total amount paid by customer")
    customer_outstanding_amount = fields.Float(string='Customer Outstanding', compute='_compute_financial_data',
                                               store=True,
                                               help="Amount still owed by customer (Invoiced - Paid)")
    customer_pending_invoice = fields.Float(string='Customer Pending Invoice', compute='_compute_financial_data',
                                            store=True,
                                            help="Amount not yet invoiced to customer")

    # Vendor Bill fields
    vendor_bills_total = fields.Float(string='Vendor Bills Total', compute='_compute_financial_data', store=True,
                                      help="Total amount of vendor bills for this project")
    vendor_bills_paid = fields.Float(string='Vendor Bills Paid', compute='_compute_financial_data', store=True,
                                     help="Total amount paid to vendors")
    vendor_bills_outstanding = fields.Float(string='Vendor Bills Outstanding', compute='_compute_financial_data',
                                            store=True,
                                            help="Amount still owed to vendors")

    # Summary fields
    total_costs_net = fields.Float(string='Total Costs Net', compute='_compute_financial_data', store=True)
    total_costs_with_tax = fields.Float(string='Total Cost with Tax', compute='_compute_financial_data', store=True)
    profit_loss = fields.Float(string='Profit/Loss', compute='_compute_financial_data', store=True)
    negative_difference = fields.Float(string='Negative Difference', compute='_compute_financial_data', store=True)

    # Labor/Timesheet fields
    total_hours_booked = fields.Float(string='Total Hours Booked', compute='_compute_financial_data', store=True,
                                      help="Total hours logged in timesheets for this project")
    labor_costs = fields.Float(string='Labor Costs', compute='_compute_financial_data', store=True,
                               help="Total cost of labor based on employee hourly rates and timesheet entries")

    @api.depends('project_id')
    def _compute_project_id_display(self):
        for record in self:
            record.project_id_display = str(record.id)

    @api.model
    def get_views(self, views, options=None):
        """Override get_views to trigger analytics computation on specific view loads"""
        result = super().get_views(views, options)

        # Only trigger for list/pivot views that need analytics
        view_types = [view[1] for view in views] if views else []
        context = self.env.context or {}

        # Check if we're loading analytics-related views
        if ('list' in view_types or 'pivot' in view_types) and not context.get('skip_analytics_auto_compute'):
            # Get current domain and search for records that need computation
            domain = context.get('search_default_domain', [])
            if not domain:
                domain = []

            # Limit records to avoid performance issues
            projects = self.search(domain, limit=100, order='id desc')
            if projects:
                try:
                    projects._compute_financial_data()
                except Exception as e:
                    _logger.warning(f"Analytics computation failed: {e}")

        return result

    def _compute_financial_data(self):
        for project in self:
            # Initialize all customer invoice fields
            customer_total_to_invoice = 0.0
            customer_invoiced_amount = 0.0
            customer_paid_amount = 0.0
            customer_outstanding_amount = 0.0
            customer_pending_invoice = 0.0

            # Initialize vendor bill fields
            vendor_bills_total = 0.0
            vendor_bills_paid = 0.0
            vendor_bills_outstanding = 0.0

            # Initialize other fields
            total_costs_net = 0.0
            total_costs_with_tax = 0.0
            profit_loss = 0.0
            negative_difference = 0.0
            total_hours_booked = 0.0
            labor_costs = 0.0

            # Keep track of processed invoices to avoid duplicates
            processed_customer_invoices = set()
            processed_vendor_bills = set()

            # Get the analytic account associated with the project
            analytic_account = getattr(project, 'account_id', None) or getattr(project, 'analytic_account_id', None)

            if analytic_account:
                # Calculate timesheet data
                total_hours_booked, labor_costs = self._calculate_timesheet_data(project, analytic_account)

                # Calculate costs from analytic lines
                total_costs_net, total_costs_with_tax = self._calculate_analytic_costs(analytic_account)

            # Calculate customer invoice data
            customer_data = self._calculate_customer_invoice_data(project, analytic_account,
                                                                  processed_customer_invoices)
            customer_total_to_invoice = customer_data['total_to_invoice']
            customer_invoiced_amount = customer_data['invoiced_amount']
            customer_paid_amount = customer_data['paid_amount']

            # Calculate vendor bill data
            vendor_data = self._calculate_vendor_bill_data(project, analytic_account, processed_vendor_bills)
            vendor_bills_total = vendor_data['bills_total']
            vendor_bills_paid = vendor_data['bills_paid']

            # Calculate derived fields
            customer_outstanding_amount = customer_invoiced_amount - customer_paid_amount
            customer_pending_invoice = customer_total_to_invoice - customer_invoiced_amount
            vendor_bills_outstanding = vendor_bills_total - vendor_bills_paid

            # Calculate profit/loss
            total_revenue = customer_invoiced_amount
            profit_loss = total_revenue - total_costs_net - vendor_bills_total
            negative_difference = abs(min(0, profit_loss))

            # Update all computed fields
            project.update({
                'customer_total_to_invoice': customer_total_to_invoice,
                'customer_invoiced_amount': customer_invoiced_amount,
                'customer_paid_amount': customer_paid_amount,
                'customer_outstanding_amount': customer_outstanding_amount,
                'customer_pending_invoice': customer_pending_invoice,
                'vendor_bills_total': vendor_bills_total,
                'vendor_bills_paid': vendor_bills_paid,
                'vendor_bills_outstanding': vendor_bills_outstanding,
                'total_costs_net': total_costs_net,
                'total_costs_with_tax': total_costs_with_tax,
                'profit_loss': profit_loss,
                'negative_difference': negative_difference,
                'total_hours_booked': total_hours_booked,
                'labor_costs': labor_costs,
            })

    def _calculate_timesheet_data(self, project, analytic_account):
        """Calculate timesheet hours and labor costs"""
        total_hours_booked = 0.0
        labor_costs = 0.0

        if not analytic_account:
            return total_hours_booked, labor_costs

        # Get timesheet lines
        timesheet_domain = [
            ('account_id', '=', analytic_account.id),
            ('is_timesheet', '=', True)
        ]

        # Add project filter if available
        if hasattr(self.env['account.analytic.line'], 'project_id'):
            timesheet_domain.append(('project_id', '=', project.id))

        timesheet_lines = self.env['account.analytic.line'].search(timesheet_domain)

        # If no results with project filter, try without it
        if not timesheet_lines and hasattr(self.env['account.analytic.line'], 'project_id'):
            timesheet_lines = self.env['account.analytic.line'].search([
                ('account_id', '=', analytic_account.id),
                ('is_timesheet', '=', True)
            ])

        # Sum hours and costs
        for line in timesheet_lines:
            total_hours_booked += line.unit_amount or 0.0
            labor_costs += abs(line.amount or 0.0)

        return total_hours_booked, labor_costs

    def _calculate_analytic_costs(self, analytic_account):
        """Calculate costs from analytic lines"""
        total_costs_net = 0.0
        total_costs_with_tax = 0.0

        if not analytic_account:
            return total_costs_net, total_costs_with_tax

        # Get all cost lines (negative amounts)
        cost_lines = self.env['account.analytic.line'].search([
            ('account_id', '=', analytic_account.id),
            ('amount', '<', 0)
        ])

        # Calculate net costs
        total_costs_net = sum(abs(line.amount) for line in cost_lines)

        # Calculate costs with tax
        total_costs_with_tax = total_costs_net
        for line in cost_lines:
            if line.move_line_id and line.move_line_id.tax_ids:
                tax_amount = 0.0
                for tax in line.move_line_id.tax_ids:
                    if tax.amount_type == 'percent':
                        tax_amount += abs(line.amount) * (tax.amount / 100)
                    elif tax.amount_type == 'fixed':
                        tax_amount += tax.amount
                total_costs_with_tax += tax_amount

        return total_costs_net, total_costs_with_tax

    def _calculate_customer_invoice_data(self, project, analytic_account, processed_invoices):
        """Calculate customer invoice related data"""
        result = {
            'total_to_invoice': 0.0,
            'invoiced_amount': 0.0,
            'paid_amount': 0.0
        }

        # Method 1: From related sale orders
        related_sale_orders = self._get_related_sale_orders(project, analytic_account)

        # Calculate total that should be invoiced from sale orders
        for sale_order in related_sale_orders:
            result['total_to_invoice'] += sale_order.amount_total

            # Process invoices from this sale order
            invoices = sale_order.invoice_ids.filtered(
                lambda inv: inv.state == 'posted' and inv.move_type == 'out_invoice')
            for invoice in invoices:
                if invoice.id not in processed_invoices:
                    processed_invoices.add(invoice.id)
                    result['invoiced_amount'] += invoice.amount_total
                    result['paid_amount'] += self._calculate_invoice_paid_amount(invoice)

        # Method 2: Direct project invoices (if no sale orders found)
        if not related_sale_orders and hasattr(project, 'invoice_ids'):
            for invoice in project.invoice_ids.filtered(
                    lambda inv: inv.state == 'posted' and inv.move_type == 'out_invoice'):
                if invoice.id not in processed_invoices:
                    processed_invoices.add(invoice.id)
                    result['invoiced_amount'] += invoice.amount_total
                    result['paid_amount'] += self._calculate_invoice_paid_amount(invoice)
                    result['total_to_invoice'] += invoice.amount_total  # Assume fully invoiceable

        # Method 3: From analytic distribution (if analytic account exists)
        if analytic_account and not related_sale_orders:
            invoice_lines = self.env['account.move.line'].search([
                ('analytic_distribution', '!=', False),
                ('parent_state', '=', 'posted'),
                ('move_id.move_type', '=', 'out_invoice')
            ])

            for line in invoice_lines:
                if line.analytic_distribution and str(analytic_account.id) in line.analytic_distribution:
                    invoice = line.move_id
                    if invoice.id not in processed_invoices:
                        processed_invoices.add(invoice.id)

                        portion_data = self._calculate_project_invoice_portion(invoice, analytic_account)
                        result['invoiced_amount'] += portion_data['invoiced']
                        result['paid_amount'] += portion_data['paid']
                        result['total_to_invoice'] += portion_data[
                            'invoiced']  # Assume what's invoiced was fully invoiceable

        return result

    def _calculate_vendor_bill_data(self, project, analytic_account, processed_bills):
        """Calculate vendor bill data for the project"""
        result = {
            'bills_total': 0.0,
            'bills_paid': 0.0
        }

        # Method 1: Purchase orders linked to project
        purchase_orders = self._get_related_purchase_orders(project, analytic_account)

        for purchase_order in purchase_orders:
            # Get vendor bills from this purchase order
            bills = purchase_order.invoice_ids.filtered(
                lambda bill: bill.state == 'posted' and bill.move_type == 'in_invoice'
            )

            for bill in bills:
                if bill.id not in processed_bills:
                    processed_bills.add(bill.id)
                    result['bills_total'] += bill.amount_total
                    result['bills_paid'] += self._calculate_bill_paid_amount(bill)

        # Method 2: Vendor bills via analytic distribution
        if analytic_account:
            bill_lines = self.env['account.move.line'].search([
                ('analytic_distribution', '!=', False),
                ('parent_state', '=', 'posted'),
                ('move_id.move_type', '=', 'in_invoice')
            ])

            for line in bill_lines:
                if line.analytic_distribution and str(analytic_account.id) in line.analytic_distribution:
                    bill = line.move_id
                    if bill.id not in processed_bills:
                        processed_bills.add(bill.id)

                        portion_data = self._calculate_project_bill_portion(bill, analytic_account)
                        result['bills_total'] += portion_data['bill_amount']
                        result['bills_paid'] += portion_data['paid_amount']

        return result

    def _get_related_sale_orders(self, project, analytic_account):
        """Get all sale orders related to this project"""
        related_orders = self.env['sale.order']

        # Method 1: Direct project_id relationship
        if hasattr(self.env['sale.order'], 'project_id'):
            orders_by_project = self.env['sale.order'].search([('project_id', '=', project.id)])
            related_orders |= orders_by_project

        # Method 2: Via analytic account if available
        if analytic_account and hasattr(self.env['sale.order'], 'analytic_account_id'):
            orders_by_analytic = self.env['sale.order'].search([('analytic_account_id', '=', analytic_account.id)])
            related_orders |= orders_by_analytic

        return related_orders.filtered(lambda so: so.state in ['sale', 'done'])

    def _get_related_purchase_orders(self, project, analytic_account):
        """Get all purchase orders related to this project"""
        related_orders = self.env['purchase.order']

        # Method 1: Direct project_id relationship
        if hasattr(self.env['purchase.order'], 'project_id'):
            orders_by_project = self.env['purchase.order'].search([('project_id', '=', project.id)])
            related_orders |= orders_by_project

        # Method 2: Via analytic account
        if analytic_account:
            # Check purchase order lines for analytic distribution
            po_lines = self.env['purchase.order.line'].search([
                ('analytic_distribution', '!=', False)
            ])

            relevant_po_lines = po_lines.filtered(
                lambda line: line.analytic_distribution and str(analytic_account.id) in line.analytic_distribution
            )

            if relevant_po_lines:
                related_orders |= relevant_po_lines.mapped('order_id')

        return related_orders.filtered(lambda po: po.state in ['purchase', 'done'])

    def _calculate_invoice_paid_amount(self, invoice):
        """Calculate the paid amount for a customer invoice"""
        if hasattr(invoice, 'amount_residual'):
            return max(0.0, invoice.amount_total - invoice.amount_residual)

        # Fallback method using payment reconciliation
        paid_amount = 0.0
        payment_lines = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )

        for line in payment_lines:
            # Sum matched debits and credits
            for matched_debit in line.matched_debit_ids:
                paid_amount += matched_debit.amount
            for matched_credit in line.matched_credit_ids:
                paid_amount += matched_credit.amount

        return max(0.0, paid_amount)

    def _calculate_bill_paid_amount(self, bill):
        """Calculate the paid amount for a vendor bill"""
        if hasattr(bill, 'amount_residual'):
            return max(0.0, bill.amount_total - bill.amount_residual)

        # Fallback method using payment reconciliation
        paid_amount = 0.0
        payment_lines = bill.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable'
        )

        for line in payment_lines:
            # Sum matched debits and credits
            for matched_debit in line.matched_debit_ids:
                paid_amount += matched_debit.amount
            for matched_credit in line.matched_credit_ids:
                paid_amount += matched_credit.amount

        return max(0.0, paid_amount)

    def _calculate_project_invoice_portion(self, invoice, analytic_account):
        """Calculate what portion of a customer invoice belongs to this project"""
        result = {'invoiced': 0.0, 'paid': 0.0}

        project_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.analytic_distribution and str(analytic_account.id) in line.analytic_distribution
        )

        if not project_lines:
            return result

        project_total = sum(project_lines.mapped('price_total'))

        if invoice.amount_total > 0:
            proportion = project_total / invoice.amount_total
            result['invoiced'] = project_total

            total_paid = self._calculate_invoice_paid_amount(invoice)
            result['paid'] = total_paid * proportion

        return result

    def _calculate_project_bill_portion(self, bill, analytic_account):
        """Calculate what portion of a vendor bill belongs to this project"""
        result = {'bill_amount': 0.0, 'paid_amount': 0.0}

        project_lines = bill.invoice_line_ids.filtered(
            lambda line: line.analytic_distribution and str(analytic_account.id) in line.analytic_distribution
        )

        if not project_lines:
            return result

        project_total = sum(project_lines.mapped('price_total'))

        if bill.amount_total > 0:
            proportion = project_total / bill.amount_total
            result['bill_amount'] = project_total

            total_paid = self._calculate_bill_paid_amount(bill)
            result['paid_amount'] = total_paid * proportion

        return result