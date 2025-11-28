{
    'name': 'Project Statistic',
    'version': '18.0.1.0.1',
    'category': 'Project',
    'summary': 'Enhanced project analytics with financial data',
    'description': """
        Project Analytics Module
        ========================
        Provides comprehensive financial analytics for projects including:
        - Customer invoicing and payment tracking
        - Vendor bill management
        - Cost analysis with tax calculations
        - Profit/loss calculations
        - Labor cost tracking from timesheets
    """,
    'depends': [
        'project',
        'account',
        'accountant', 
        'analytic',
        'hr_timesheet',
    ],
    'author': 'Alex Feld',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'views/project_analytics_views.xml',
        'data/menuitem.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'uninstall_hook': 'uninstall_hook',
}