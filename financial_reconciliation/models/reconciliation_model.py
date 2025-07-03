from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class FinancialReconciliation(models.Model):
    _name = 'financial.reconciliation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Conciliación Financiera'
    _order = 'date desc'

    name = fields.Char('Consecutivo', required=True, default=lambda self: _('New'))
    date = fields.Date('Fecha', default=fields.Date.today)
    identification = fields.Char('Cédula')
    contract_number = fields.Char('Número de Contrato')
    receipt_number = fields.Char('Número de Recibo')
    amount = fields.Float('Monto')
    reference = fields.Char('referencia', help="Referencia del pago asociado a este registro")
    currency_id = fields.Many2one('res.currency', string='Moneda')
    partner_id = fields.Many2one('res.partner', 'Cliente')

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('review', 'Revisión'),
        ('validated', 'Validado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft')

    external_data = fields.Text('Datos Externos')
    image = fields.Binary('Comprobante')
    ocr_text = fields.Text('Texto OCR')
    has_image = fields.Boolean('Tiene Comprobante', compute='_compute_has_image')
    search_results = fields.Text('Resultados Búsqueda', compute='_compute_search_results')

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('financial.reconciliation') or _('New')
        return super().create(vals)

    def import_from_external_db(self):
        """Consulta BD externa sin filtros y crea múltiples registros."""
        External = self.env['external.db.connector']
        results = External.search_external_data()  # sin argumentos

        if not results:
            raise UserError(_("No se encontraron datos en la base de datos externa."))

        count = 0
        for data in results:
            # Evitar duplicados
            exists = self.search([
                ('identification', '=', data['cedula']),
                ('contract_number', '=', data['contrato']),
                ('receipt_number', '=', data['recibo']),
                ('reference', '=', data['referencia']),
            ], limit=1)
            if not exists:
                self.create({
                    'identification': data['cedula'],
                    'contract_number': data['contrato'],
                    'receipt_number': data['recibo'],
                    'date': data['fecha'],
                    'amount': data['monto'],
                    'reference': data['referencia'],
                    'external_data': _(
                        "Importado automáticamente el %s"
                    ) % fields.Date.today(),
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

    def _compute_search_results(self):
        for record in self:
            record.search_results = record.external_data or "No hay resultados"

    def _show_notification(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Búsqueda Externa'),
                'message': message,
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
