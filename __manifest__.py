{
    'name': 'Project Analytics Report',
    'version': '18.0.1.0.0',
    'category': 'Project',
    'summary': 'Enhanced project analytics with financial data',
    'depends': ['project','account', 'accountant', 'sale_management' , 'sale_project'],
    'author':'Hamza Aslam',
    'data': [
        'security/ir.model.access.csv',
        'views/project_analytics_views.xml',
        'data/menuitem.xml',
    ],
    'installable': True,
    'auto_install': False,
    'uninstall_hook': 'uninstall_hook',
}