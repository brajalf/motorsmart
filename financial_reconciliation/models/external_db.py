import psycopg2
import logging
from psycopg2.extras import DictCursor
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ExternalDBConnector(models.Model):
    _name = 'external.db.connector'
    _description = 'Conector a Base de Datos Externa'

    @api.model
    def _get_db_credentials(self):
        """Obtiene las credenciales de la BD desde los parámetros del sistema de Odoo."""
        params = self.env['ir.config_parameter'].sudo()
        return {
            'dbname': params.get_param('external_db.dbname', 'financial_reconciliation_motor'),
            'user': params.get_param('external_db.user', 'postgres.iqvzkdbychgnwmwcyhbj'),
            'password': params.get_param('external_db.password', 'vFMQ33W%mZ&bFE#'),
            'host': params.get_param('external_db.host', 'aws-0-us-east-2.pooler.supabase.com'),
            'port': params.get_param('external_db.port', '6543'),
        }

    @api.model
    def get_connection(self):
        """Obtener conexión a la base de datos externa."""
        creds = self._get_db_credentials()
        try:
            conn = psycopg2.connect(**creds)
            return conn
        except psycopg2.Error as e:
            _logger.error("❌ ERROR DE CONEXIÓN A BD EXTERNA: %s", e)
            raise UserError(_("No se pudo conectar a la base de datos externa: %s") % e)

    def search_external_data(self, **kwargs):
        """Busca y devuelve todos los registros desde la vista vw_oddo_motor."""
        query = """
            SELECT
                "Numero Recibo" AS numero_recibo,
                "Numero Factura" AS numero_factura,
                "Numero Contrato" AS numero_contrato,
                "Doc. de Titular" AS doc_titular,
                "Nombre Titular" AS nombre_titular,
                "Doc. de Estudiante" AS doc_estudiante,
                "Nombre Estudiante" AS nombre_estudiante,
                concepto,
                detalles,
                "Date" AS fecha_consignacion,
                "Fecha Recibo" AS fecha_recibo,
                "Valor Pagado" AS valor_pagado,
                "Valor Efectivo" AS valor_efectivo,
                "Valor Cheque" AS valor_cheque,
                "Valor Voucher" AS valor_voucher,
                "Valor de Consignacion" AS valor_consignacion,
                "Referencia" AS referencia,
                "Banco" AS banco
            FROM
                stg_reconciliation_motor.vw_oddo_motor;
        """

        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query)
                results = [dict(row) for row in cursor.fetchall()]
                _logger.info("✅ Consulta exitosa: Se encontraron %d registros.", len(results))
                return results
        except psycopg2.Error as e:
            _logger.error("❌ ERROR DE CONSULTA SQL: %s", e)
            raise UserError(_("Ocurrió un error al consultar la vista en la BD externa: %s") % e)
        finally:
            if conn:
                conn.close()

    def mark_records_as_processed(self, receipt_numbers):
        """Marca los recibos como procesados en la tabla base."""
        if not receipt_numbers:
            return
        
        # Ajusta la tabla (resumen) y columna (A) si es necesario
        query = "UPDATE stg_reconciliation_motor.resumen SET A = FALSE WHERE numero_de_recibo IN %s"
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, (tuple(receipt_numbers),))
                conn.commit()
                _logger.info("✅ Se marcaron como procesados %d registros.", cursor.rowcount)
        except psycopg2.Error as e:
            _logger.error("❌ Error al actualizar registros: %s", e)
            conn.rollback()
        finally:
            if conn:
                conn.close()