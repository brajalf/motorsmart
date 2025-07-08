from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class FinancialReconciliation(models.Model):
    _name = 'financial.reconciliation'
    _inherit = ['mail.thread']
    _description = 'Conciliación Financiera'
    _order = 'date desc'

     # --- CAMPO CONSECUTIVO Y ESTADO ---
    name = fields.Char('Consecutivo', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('review', 'En Revisión'),
        ('validated', 'Validado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True)

    # --- INFORMACIÓN DEL TITULAR Y ESTUDIANTE ---
    holder_name = fields.Char('Nombre del Titular', readonly=True)
    identification = fields.Char('Doc. del Titular', readonly=True)
    student_name = fields.Char('Nombre del Estudiante', readonly=True)
    student_id = fields.Char('Doc. Estudiante', readonly=True)
    student_campus = fields.Char('Sede Estudiante', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Revisor')

    # --- INFORMACIÓN DEL RECIBO Y PAGO ---
    date = fields.Date('Fecha Recibo', readonly=True)
    payment_date = fields.Date('Fecha Consignación', readonly=True)
    contract_number = fields.Char('Número Contrato')
    receipt_number = fields.Char('Número Recibo', readonly=True)
    invoice_number = fields.Char('Número Factura', readonly=True)
    reference = fields.Char('Referencia')
    concept = fields.Char('Concepto', readonly=True)
    detail = fields.Text('Detalle', readonly=True)
    bank_id = fields.Many2one('res.bank', string='Banco', readonly=True)

    # --- DESGLOSE DEL VALOR PAGADO ---
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary('Valor Pagado', currency_field='currency_id', readonly=True)
    cash_payment = fields.Monetary('Efectivo', currency_field='currency_id', readonly=True)
    check_payment = fields.Monetary('Cheque', currency_field='currency_id', readonly=True)
    voucher_payment = fields.Monetary('Voucher', currency_field='currency_id', readonly=True)
    deposit_payment = fields.Monetary('Consignación', currency_field='currency_id', readonly=True)

    # --- CAMPOS TÉCNICOS Y DE CONTROL ---
    external_data = fields.Text('Datos Externos', readonly=True)
    image = fields.Binary('Comprobante')
    ocr_text = fields.Text('Texto OCR', readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('financial.reconciliation') or _('New')
        return super().create(vals)

    def import_from_external_db(self):
        """Consulta BD externa sin filtros y crea múltiples registros con toda la nueva data."""
        External = self.env['external.db.connector']
        results = External.search_external_data()

        if not results:
            raise UserError(_("No se encontraron datos en la base de datos externa."))

        count = 0
        for data in results:
            # Evitar duplicados basados en una combinación de campos clave
            exists = self.search([
                ('identification', '=', data.get('cedula')),
                ('contract_number', '=', data.get('contrato')),
                ('receipt_number', '=', data.get('recibo')),
                ('reference', '=', data.get('referencia')),
            ], limit=1)

            if not exists:
                # Buscar el banco por nombre para obtener el ID
                bank_name = data.get('banco')
                bank_id = self.env['res.bank'].search([('name', '=', bank_name)], limit=1)

                self.create({
                    # Datos principales
                    'identification': data.get('cedula'),
                    'holder_name': data.get('titular'),
                    'student_id': data.get('doc_estudiante'),
                    'student_name': data.get('estudiante'),
                    'student_campus': data.get('sede'),
                    'contract_number': data.get('contrato'),
                    'receipt_number': data.get('recibo'),
                    'invoice_number': data.get('factura'),
                    'date': data.get('fecha'),
                    'payment_date': data.get('fecha_pago'),
                    'reference': data.get('referencia'),
                    'concept': data.get('concepto'),
                    'detail': data.get('detalle'),
                    'bank_id': bank_id.id if bank_id else False,
                    # Montos
                    'amount': data.get('monto'),
                    'cash_payment': data.get('efectivo'),
                    'check_payment': data.get('cheque'),
                    'voucher_payment': data.get('voucher'),
                    'deposit_payment': data.get('consignacion'),
                    # Info de importación
                    'external_data': _("Importado automáticamente el %s") % fields.Date.today(),
                })
                count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Importación completada"),
                'message': _("%d registros importados desde la BD externa.") % count,
                'type': 'success',
                'sticky': False,
            }
        }

    def process_ocr(self):
        self.ensure_one()
        if not self.image:
            raise UserError(_("Por favor cargue un comprobante primero"))
        ocr_result = self.env['ocr.controller'].extract_text(self.image)
        self.ocr_text = ocr_result
        return self._show_notification('OCR completado: Texto extraído')

    def clear_ocr(self):
        self.ensure_one()
        self.ocr_text = False
        return self._show_notification('Texto OCR limpiado')

    def write(self, vals):
        if 'image' in vals and not vals.get('image'):
            vals['ocr_text'] = False
        return super().write(vals)

    @api.depends('image')
    def _compute_has_image(self):
        for record in self:
            record.has_image = bool(record.image)

    def action_to_review(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Solo se puede pasar a Revisión desde el estado Borrador."))
            rec.state = 'review'

    def action_to_validated(self):
        for rec in self:
            if rec.state != 'review':
                raise UserError(_("Solo se puede Validar desde el estado Revisión."))
            rec.state = 'validated'

    def action_insert_external(self):
        """Inserta en la BD externa registros que no existían."""
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("Solo se puede insertar si está Validado."))
            if rec.external_data:
                raise UserError(_("Ya existe en la BD externa, usa 'Actualizar registro'."))
            external = self.env['external.db.connector']
            external.insert_external_record(
                identification=rec.identification,
                contract=rec.contract_number,
                receipt=rec.receipt_number,
                monto=rec.amount,
                fecha=rec.date,
                reference=rec.reference,
                name=rec.name,
            )
            rec.external_data = _("Insertado en BD externa el %s") % fields.Date.today()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Insertado"),
                'message': _("Registros insertados en la BD externa correctamente."),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_update_external(self):
        """Actualiza en la BD externa registros ya importados."""
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("Solo se puede actualizar si está Validado."))
            if not rec.external_data:
                raise UserError(_("No existe en la BD externa, usa 'Insertar registro'."))
            external = self.env['external.db.connector']
            external.update_external_record(
                monto=rec.amount,
                fecha=rec.date,
                name=rec.name,
            )
            rec.external_data = _("Actualizado en BD externa el %s") % fields.Date.today()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Actualizado"),
                'message': _("Registros actualizados en la BD externa correctamente."),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == 'validated':
                raise UserError(_("No se puede cancelar un registro ya Validado."))
            rec.state = 'cancelled'
