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
    holder_name = fields.Char('Nombre del Titular', tracking=True)
    identification = fields.Char('Doc. del Titular', tracking=True)
    student_name = fields.Char('Nombre del Estudiante', tracking=True)
    student_id = fields.Char('Doc. Estudiante', tracking=True)
    student_campus = fields.Char('Sede Estudiante', readonly=True)
    partner_id = fields.Many2one('res.partner', 'Revisor', tracking=True)

    # --- INFORMACIÓN DEL RECIBO Y PAGO ---
    date = fields.Date('Fecha Recibo', readonly=True)
    payment_date = fields.Date('Fecha Consignación', readonly=True)
    contract_number = fields.Char('Número Contrato', tracking=True)
    receipt_number = fields.Char('Número Recibo', tracking=True)
    invoice_number = fields.Char('Número Factura', readonly=True)
    reference = fields.Char('Referencia', tracking=True)
    concept = fields.Char('Concepto', readonly=True)
    detail = fields.Text('Detalle', readonly=True)
    bank_name = fields.Char('Banco', readonly=True)
    

    # --- DESGLOSE DEL VALOR PAGADO ---
    currency_id = fields.Many2one('res.currency', string='Moneda', default=lambda self: self.env.company.currency_id)
    amount = fields.Monetary('Valor Pagado', currency_field='currency_id', readonly=True)
    cash_payment = fields.Monetary('Efectivo', currency_field='currency_id', readonly=True)
    check_payment = fields.Monetary('Cheque', currency_field='currency_id', readonly=True)
    voucher_payment = fields.Monetary('Voucher', currency_field='currency_id', readonly=True)
    deposit_payment = fields.Monetary('Consignación', currency_field='currency_id', readonly=True)

    # --- CAMPOS TÉCNICOS Y DE CONTROL ---
    origin_data = fields.Char('Origen del Dato', readonly=True)
    type_conciliation = fields.Char('Tipo de Conciliación', readonly=True)
    external_data = fields.Text('Datos Externos', readonly=True)
    image = fields.Binary('Comprobante', tracking=True)
    ocr_text = fields.Text('Texto OCR', readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('financial.reconciliation') or _('New')
        return super().create(vals)

    def import_from_external_db(self):
        """Consulta BD externa y crea registros mapeando los campos CORRECTAMENTE."""
        External = self.env['external.db.connector']
        results = External.search_external_data()
        
        if not results:
            raise UserError(_("No se encontraron nuevos datos en la base de datos externa."))

        count = 0
        receipts_processed = []
        for data in results:
            # Evitar duplicados por número de recibo
            receipt_number = data.get('numero_recibo')
            if not receipt_number:
                continue # Omitir registros sin número de recibo
            
            exists = self.search([('receipt_number', '=', receipt_number)], limit=1)
            if not exists:
                # --- ¡AQUÍ ESTÁ LA CORRECCIÓN CLAVE! ---
                # Usamos los nombres de columna correctos que devuelve la consulta
                self.create({
                    'identification': data.get('doc_titular'),
                    'holder_name': data.get('nombre_titular'),
                    'student_id': data.get('doc_estudiante'),
                    'student_name': data.get('nombre_estudiante'),
                    'student_campus': data.get('sede'),
                    'contract_number': data.get('numero_contrato'),
                    'receipt_number': data.get('numero_recibo'),
                    'invoice_number': data.get('numero_factura'),
                    'date': data.get('fecha_recibo'),
                    'payment_date': data.get('fecha_consignacion'),
                    'reference': data.get('referencia'),
                    'concept': data.get('concepto'),
                    'detail': data.get('detalles'),
                    'bank_name': data.get('banco'),
                    'amount': data.get('valor_pagado'),
                    'cash_payment': data.get('valor_efectivo'),
                    'check_payment': data.get('valor_cheque'),
                    'voucher_payment': data.get('valor_voucher'),
                    'deposit_payment': data.get('valor_consignacion'),
                    'origin_data': data.get('origen_dato'),
                    'type_conciliation': data.get('tipo_conciliacion'),
                    'external_data': _("Importado automáticamente el %s") % fields.Date.today(),
                })
                count += 1
                receipts_processed.append(receipt_number)

        # (Opcional pero recomendado) Marcar registros como procesados en la BD externa
        if receipts_processed:
            External.mark_records_as_processed(receipts_processed)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Importación completada"),
                'message': _("%d nuevos registros importados desde la BD externa.") % count,
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
