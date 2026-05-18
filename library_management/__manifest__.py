{
    'name': 'Library Management',
    'version': '19.0.1.0.0',
    'category': 'Services',
    'summary': 'Manage books, members and borrowing records',
    'description': '''
        Library Management System
        =========================
        Features:
        - Manage books and authors
        - Track available copies
        - Record borrowing history
    ''',
    'author': 'Om',
    'depends': ['base', 'website'],
    'data': [
        'security/library_security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/library_report.xml',
        'views/library_website_templates.xml',
        'data/library_sequence.xml',
        'data/library_cron.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}