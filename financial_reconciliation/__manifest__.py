{
    'name': 'Conciliación Financiera',
    'version': '1.1.0',
    'summary': 'Módulo para conciliación financiera con conexión a BD externa y OCR',
    'description': '''
        Módulo de conciliación financiera con:
        - Conexión a base de datos PostgreSQL externa
        - Funcionalidad OCR para comprobantes
        - Vistas: árbol, kanban y formulario
        - Búsquedas por cédula, contrato, recibo y fechas
    ''',
    'category': 'Accounting',
    'author': 'Brandon León (Invictus Technology Tic S.A.S)',
    'website': 'https://www.invictustechnologytic.com',
    'depends': ['base', 'web', 'account', 'mail'],
    'data': [
        'security/security_rules.xml',
        'security/ir.model.access.csv',
        'views/reconciliation_views.xml',
        'views/reconciliation_menus.xml',
        'data/financial_sequence.xml',
    ],
    'assets': {
    'web.assets_backend': [
        'financial_reconciliation/static/src/scss/reconciliation.scss',
        #'financial_reconciliation/static/src/js/reconciliation.js',
        'https://d3js.org/d3.v7.min.js',
        'financial_reconciliation/static/src/js/dashboard.js',
      ],
      'web.assets_qweb': [
            'financial_reconciliation/static/src/xml/dash.xml',
      ],
    },
    'external_dependencies': {
        'python': ['psycopg2', 'pytesseract', 'pdf2image', 'Pillow'],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}