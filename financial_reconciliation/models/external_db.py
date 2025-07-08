import psycopg2
import logging
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ExternalDBConnector(models.Model):
    _name = 'external.db.connector'
    _inherit = ['mail.thread']
    _description = 'Conector a Base de Datos Externa'

    @api.model
    def get_connection(self):
        """Obtener conexión a la base de datos externa."""
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user="postgres.iqvzkdbychgnwmwcyhbj",
                password="vFMQ33W%mZ&bFE#",
                host="aws-0-us-east-2.pooler.supabase.com",
                port="6543"
            )
            _logger.info("✅ Conexión exitosa a BD externa")
            return conn
        except Exception as e:
            _logger.error("❌ Error de conexión: %s", e)
            raise UserError(_("Error conectando a base de datos externa: %s") % e)

    def search_external_data(self, **kwargs):
        """
        Busca registros opcionalmente filtrados y devuelve:
          - cedula
          - contrato
          - recibo
          - fecha
          - monto
          - referencia
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        base_query = """
            SELECT * FROM (
            SELECT     numero_de_recibo AS "Numero Recibo",
                    numero_de_factura AS "Numero Factura",
                    numero_de_contrato AS "Numero Contrato",
                    numero_documento_titular AS "Doc. de Titular",        
                    nombre_completo AS "Nombre Titular",
                    numero_documento_estudiante AS "Doc. de Estudiante",
                    nombre_completo_estudiante AS "Nombre Estudiante",
                    concepto,
                    detalles,
                    date_purchase_val AS "Date",
                    fecha_de_recibo AS "Fecha Recibo",
                    valor_pagado AS "Valor Pagado",
                    valor_efectivo AS "Valor Efectivo",
                    valor_cheque AS "Valor Cheque", 
                    valor_voucher AS "Valor Voucher",
                    valor_consignacion AS "Valor de Consignacion",
                    id_transacion AS "Referencia",
                    'Mercado Pago' AS "Banco"
            FROM stg_reconciliation_motor.resumen
            WHERE A = TRUE
        ) AS A
        """
        clauses, params = [], []
        if kwargs.get('identification'):
            clauses.append("numero_documento_titular = %s")
            params.append(kwargs['identification'])
        # Añadir más filtros si es necesario...

        final_query = base_query
        if clauses:
            final_query += " AND " + " AND ".join(clauses)

        conn = self.get_connection()
        try:
            # Usamos 'with' para asegurar que el cursor y la conexión se cierren siempre.
            with conn:
                with conn.cursor() as cursor:
                    _logger.debug("Ejecutando query: %s con params: %s", cursor.mogrify(final_query, params))
                    cursor.execute(final_query, params)
                    
                    # Mapeo dinámico y robusto de resultados a diccionarios
                    columns = [desc[0] for desc in cursor.description]
                    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    
                    _logger.info("✅ Se encontraron %d registros en la base de datos externa.", len(results))
                    return results
        except psycopg2.Error as e:
            _logger.error("❌ Error al ejecutar la consulta en la base de datos externa: %s", e)
            raise UserError(_("Ocurrió un error al consultar los datos externos."))
        finally:
            if conn:
                conn.close()

    #def update_external_record(self, monto, fecha, name):
        #"""Actualiza el registro externo que coincida con todas las claves."""
        #conn = self.get_connection()
        #cur = conn.cursor()
        #cur.execute("""
         #   UPDATE public.stg_src_oddo
          #     SET valor_pagado = %s,
           #        fechaCompra  = %s
            # WHERE name              = %s
        #""", (monto, fecha, name))
        #conn.commit()
        #cur.close()
        #conn.close()
        #_logger.info("Registro externo actualizado: %s", name)

    #def insert_external_record(self, identification, contract, receipt, monto, fecha, reference, name):
        #"""Inserta un nuevo registro en la base externa."""
        #conn = self.get_connection()
        #cur = conn.cursor()
        #cur.execute("""
            #INSERT INTO public.stg_src_oddo
                #(name,cedulatitular, numerocontrato, numero_de_recibo, valor_pagado, fechaCompra, referencia)
            #VALUES (%s, TRIM(%s), %s, %s, %s, %s, %s)
        #""", (name, identification.strip(), contract, receipt, monto, fecha, reference))
        #conn.commit()
        #cur.close()
        #conn.close()
        #_logger.info("Registro externo insertado: %s", name)-->