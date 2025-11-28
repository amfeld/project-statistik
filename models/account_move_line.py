from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self._trigger_project_analytics_recompute(lines)
        return lines

    def write(self, vals):
        result = super().write(vals)
        if any(key in vals for key in ['analytic_distribution', 'price_subtotal', 'debit', 'credit', 'balance']):
            self._trigger_project_analytics_recompute(self)
        return result

    def unlink(self):
        self._trigger_project_analytics_recompute(self)
        return super().unlink()

    def _trigger_project_analytics_recompute(self, lines):
        """
        Trigger recomputation of project analytics when move lines with analytic distribution change.
        """
        if not lines:
            return

        project_ids = set()

        for line in lines:
            if not line.analytic_distribution:
                continue

            try:
                project_plan = self.env.ref('analytic.analytic_plan_projects', raise_if_not_found=False)
                if not project_plan:
                    continue

                for analytic_account_id_str in line.analytic_distribution.keys():
                    try:
                        analytic_account_id = int(analytic_account_id_str)
                        analytic_account = self.env['account.analytic.account'].browse(analytic_account_id)

                        if analytic_account.exists() and analytic_account.plan_id == project_plan:
                            projects = self.env['project.project'].search([
                                '|',
                                ('analytic_account_id', '=', analytic_account.id),
                                ('account_id', '=', analytic_account.id)
                            ])
                            project_ids.update(projects.ids)
                    except (ValueError, TypeError):
                        continue
            except Exception as e:
                _logger.warning(f"Error finding projects for analytic distribution: {e}")
                continue

        if project_ids:
            projects = self.env['project.project'].browse(list(project_ids))
            projects._compute_financial_data()
            _logger.info(f"Recomputed financial data for {len(projects)} project(s)")
