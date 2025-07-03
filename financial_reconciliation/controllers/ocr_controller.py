import base64
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
from io import BytesIO
from odoo import http, _
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class OCRController(http.Controller):
    
    @http.route('/financial_reconciliation/process_ocr', type='json', auth='user')
    def extract_text(self, image_data):
        """Procesar imagen con OCR"""
        try:
            # Convertir base64 a imagen
            image_binary = base64.b64decode(image_data)
            
            # Si es PDF, convertir a imagen
            if image_binary.startswith(b'%PDF'):
                images = convert_from_bytes(image_binary)
                text = ""
                for img in images:
                    text += pytesseract.image_to_string(img)
                return text
            else:
                img = Image.open(BytesIO(image_binary))
                return pytesseract.image_to_string(img)
        except Exception as e:
            _logger.error("Error en OCR: %s", e)
            return _("Error procesando imagen: %s") % e