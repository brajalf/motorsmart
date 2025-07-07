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
    'author': 'Brandon León',
    'website': 'https://www.invictustechnologytic.com',
    'depends': ['base', 'web', 'account', 'mail'],
    'data': [
        'security/security_rules.xml',
        'security/ir.model.access.csv',
        'views/reconciliation_views.xml',
        'data/financial_sequence.xml',
    ],
    'assets': {
    'web.assets_backend': [
        'financial_reconciliation/static/src/scss/reconciliation.scss',
        #'financial_reconciliation/static/src/js/reconciliation.js',
      ],
    },
    'external_dependencies': {
        'python': ['psycopg2', 'pytesseract', 'pdf2image', 'Pillow'],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}