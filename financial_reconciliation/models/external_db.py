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
            SELECT     numero_recibo, 
                numero_factura, 
                numero_contrato, 
                doc_titular, 
                nombre_titular, 
                doc_estudiante, 
                nombre_estudiante, 
                concepto, 
                detalles, 
                fecha_consignacion, 
                fecha_recibo, 
                valor_pagado, 
                valor_efectivo, 
                valor_cheque, 
                valor_voucher, 
                valor_consignacion, 
                referencia, 
                banco, 
                origen_dato, 
                tipo_conciliacion
            FROM stg_reconciliation_motor.resumen_conciliation;

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

    def insert_external_record(self, data):
        """
        Inserta un nuevo registro en la tabla resumen_conciliation de la BD externa.
        'data' es un diccionario con los valores a insertar.
        """
        # Columnas que se insertarán. Asegúrate de que coincidan con la tabla externa.
        columns = [
            'doc_titular', 'nombre_titular', 'doc_estudiante', 'nombre_estudiante',
            'numero_contrato', 'numero_recibo', 'fecha_recibo', 'valor_pagado',
            'referencia', 'consecutivo_odoo' 
        ]
        
        # Filtramos los datos que realmente se van a insertar
        record_to_insert = {key: data.get(key) for key in columns}
        
        # Creamos la sentencia SQL dinámicamente
        cols_str = ", ".join(record_to_insert.keys())
        vals_str = ", ".join(["%s"] * len(record_to_insert))
        query = f"INSERT INTO stg_reconciliation_motor.resumen_conciliation ({cols_str}) VALUES ({vals_str})"

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(record_to_insert.values()))
                conn.commit()
                _logger.info("✅ Registro insertado en la BD externa: %s", data.get('numero_recibo'))
        except psycopg2.Error as e:
            _logger.error("❌ Error al insertar en BD externa: %s", e)
            conn.rollback()
            raise UserError(_("No se pudo insertar el registro en la base de datos externa: %s") % e)
        finally:
            if conn:
                conn.close()

    def update_external_record(self, data):
        """
        Actualiza un registro existente en la tabla resumen_conciliation.
        Usa 'numero_recibo' como identificador único para la cláusula WHERE.
        """
        # Campos que se pueden actualizar.
        update_fields = ['valor_pagado', 'fecha_recibo', 'doc_titular', 'numero_contrato']
        
        # Valores a actualizar y la cláusula WHERE
        values_to_update = []
        set_clauses = []
        
        for field in update_fields:
            if field in data:
                set_clauses.append(f"{field} = %s")
                values_to_update.append(data[field])

        if not set_clauses:
            _logger.warning("⚠️ No hay campos para actualizar en la BD externa para el recibo %s.", data.get('numero_recibo'))
            return

        # El número de recibo es el último elemento en la tupla de valores
        values_to_update.append(data.get('numero_recibo'))
        
        query = f"UPDATE stg_reconciliation_motor.resumen_conciliation SET {', '.join(set_clauses)} WHERE numero_recibo = %s"

        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(values_to_update))
                conn.commit()
                if cursor.rowcount == 0:
                     _logger.warning("⚠️ No se encontró el registro con recibo %s para actualizar en la BD externa.", data.get('numero_recibo'))
                else:
                    _logger.info("✅ Registro actualizado en BD externa: %s", data.get('numero_recibo'))
        except psycopg2.Error as e:
            _logger.error("❌ Error al actualizar en BD externa: %s", e)
            conn.rollback()
            raise UserError(_("No se pudo actualizar el registro en la base de datos externa: %s") % e)
        finally:
            if conn:
                conn.close()