# --- Imports para OCR ---
import base64
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
from io import BytesIO
from datetime import datetime
# --- Imports de Odoo y Python ---
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import re

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
    image = fields.Binary('Comprobante')
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

    def _get_ocr_text_from_image(self, image_data):
        """Helper privado para ejecutar el OCR en la imagen."""
        try:
            image_binary = base64.b64decode(image_data)
            if image_binary.startswith(b'%PDF'):
                images = convert_from_bytes(image_binary)
                text = "".join([pytesseract.image_to_string(img, lang='spa') for img in images])
                return text
            else:
                img = Image.open(BytesIO(image_binary))
                return pytesseract.image_to_string(img, lang='spa')
        except Exception as e:
            _logger.error("Error en OCR: %s", e)
            raise UserError(_("Error procesando la imagen con OCR: %s") % e)

    def _parse_date(self, date_str):
        """Intenta convertir una cadena de texto a un objeto de fecha de Odoo."""
        if not date_str:
            return None
        
        month_map = {
            'enero': '01', 'ene': '01', 'febrero': '02', 'feb': '02', 'marzo': '03', 'mar': '03',
            'abril': '04', 'abr': '04', 'mayo': '05', 'may': '05', 'junio': '06', 'jun': '06',
            'julio': '07', 'jul': '07', 'agosto': '08', 'ago': '08', 'septiembre': '09', 'sep': '09',
            'octubre': '10', 'oct': '10', 'noviembre': '11', 'nov': '11', 'diciembre': '12', 'dic': '12'
        }
        
        date_str_lower = date_str.lower()
        for k, v in month_map.items():
            date_str_lower = date_str_lower.replace(k, v)

        # Formatos a intentar en orden de probabilidad
        formats_to_try = [
            '%d %m %Y',          # 27 07 2025
            '%d/%m/%Y',          # 27/07/2025
            '%Y-%m-%d',          # 2025-07-27
        ]
        
        for fmt in formats_to_try:
            try:
                # Extraer solo la parte de la fecha
                cleaned_date_str = re.search(r'(\d{1,2}[/\s]\d{1,2}[/\s]\d{4})', date_str_lower)
                if cleaned_date_str:
                    return fields.Date.to_string(datetime.strptime(cleaned_date_str.group(1).replace(' ', '/'), '%d/%m/%Y').date())
                
                return fields.Date.to_string(datetime.strptime(date_str_lower, fmt).date())
            except (ValueError, TypeError):
                continue
        _logger.warning("No se pudo convertir la fecha: %s", date_str)
        return None

    def process_ocr(self):
        """
        Lógica mejorada de OCR que procesa línea por línea y usa patrones más robustos.
        """
        self.ensure_one()
        if not self.image:
            raise UserError(_("Por favor cargue un comprobante primero"))

        ocr_text_raw = self._get_ocr_text_from_image(self.image)
        self.ocr_text = ocr_text_raw
        
        vals = {}
        lines = ocr_text_raw.split('\n')

        # Definición de patrones de REGEX mejorados basados en las imágenes de ejemplo
        patterns = {
            'amount': r'[\$\s]*([\d.,]+)',
            'identification': r'([Cc\.\s]*\d[\d.-]{5,})',
            'contract_number': r'([A-Z0-9-]+)',
            'receipt_number': r'(\w+)',
            'holder_name': r'([A-Za-zÁÉÍÓÚáéíóúñÑ\s]+)',
            'date': r'(\d{1,2}[\s/](?:de\s)?\w+[\s/](?:de\s)?\d{4}|\d{1,2}/\d{1,2}/\d{4})'
        }

        # Palabras clave para cada campo. La primera es la principal.
        keywords = {
            'amount': ['valor pagado', 'valor de la transferencia', 'cuánto', 'valor del pago', 'total pagado'],
            'identification': ['titular documento', 'identificaci', 'cédula', 'c.c', 'usuario pagador'],
            'holder_name': ['titular nombre', 'nombre', 'titular'],
            'contract_number': ['número de contrato', 'contrato'],
            'receipt_number': ['comprobante no', 'factura de comercio', 'número de factura', 'cus', 'no. transacción'],
            'reference': ['referencia', 'no. autorización'],
            'date': ['fecha de solicitud', 'fecha'],
            'bank_name': ['banco', 'producto destino']
        }

        # Procesa cada línea del texto extraído
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            if not line_lower:
                continue

            for field, keys in keywords.items():
                for key in keys:
                    if key in line_lower:
                        # Extraer el valor de la misma línea o de la siguiente
                        value_line = line
                        if not re.search(r'\d', value_line.replace(key, '')): # Si no hay dígitos (o valor) en la línea, probar la siguiente
                           if i + 1 < len(lines):
                               value_line += " " + lines[i+1]

                        match = re.search(patterns.get(field, r'(.+)'), value_line, re.IGNORECASE)
                        if match:
                            extracted_value = match.group(1).strip()
                            
                            # Limpieza de datos específicos por campo
                            if field == 'amount':
                                clean_val = re.sub(r'[^\d,]', '', extracted_value).replace(',', '.')
                                if '.' in clean_val:
                                    # Asumimos que el último punto es el decimal
                                    parts = clean_val.split('.')
                                    clean_val = "".join(parts[:-1]) + "." + parts[-1]
                                vals[field] = float(clean_val)
                            elif field == 'identification':
                                vals[field] = re.sub(r'[^\d]', '', extracted_value)
                            elif field == 'date':
                                parsed_date = self._parse_date(extracted_value)
                                if parsed_date:
                                    vals[field] = parsed_date
                            elif field == 'holder_name':
                                # Eliminar la palabra clave para no guardarla en el nombre
                                vals[field] = re.sub(key, '', extracted_value, flags=re.IGNORECASE).strip()
                            elif field not in vals: # Evitar sobreescribir con valores menos prioritarios
                                vals[field] = extracted_value
                        break # Pasar al siguiente campo una vez que se encuentra una clave

        if vals:
            # Para campos que no se pudieron rellenar, dejar que el usuario los complete
            for field in ['holder_name', 'identification', 'amount', 'date', 'contract_number', 'receipt_number', 'reference']:
                if vals.get(field):
                    self[field] = vals[field]
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("OCR Procesado"),
                'message': _("Se han autocompletado los campos basados en la imagen. Por favor, verifique los datos."),
                'type': 'success',
                'sticky': True,
            }
        }


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
            # Se ajusta la lógica para permitir la inserción si no viene de una importación
            # if rec.external_data and "Importado" in rec.external_data:
            #     raise UserError(_("Este registro fue importado. Usa 'Actualizar registro' en su lugar."))
            
            external = self.env['external.db.connector']
            external.insert_external_record({
                'doc_titular': rec.identification,
                'nombre_titular': rec.holder_name,
                'doc_estudiante': rec.student_id,
                'nombre_estudiante': rec.student_name,
                'numero_contrato': rec.contract_number,
                'numero_recibo': rec.receipt_number,
                'fecha_recibo': rec.date,
                'valor_pagado': rec.amount,
                'referencia': rec.reference,
                'consecutivo_odoo': rec.name, # Campo para futura referencia
            })
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
            # if not rec.external_data:
            #     raise UserError(_("No existe en la BD externa, usa 'Insertar registro'."))
            
            external = self.env['external.db.connector']
            external.update_external_record({
                'valor_pagado': rec.amount,
                'fecha_recibo': rec.date,
                'doc_titular': rec.identification,
                'numero_contrato': rec.contract_number,
                # Usamos el número de recibo como identificador único para la actualización
                'numero_recibo': rec.receipt_number,
            })
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