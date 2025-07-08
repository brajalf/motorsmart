import psycopg2
import logging
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ExternalDBConnector(models.Model):
    _name = 'external.db.connector'
    _description = 'Conector a Base de Datos Externa'

    @api.model
    def get_connection(self):
        """Obtener conexión a la base de datos externa."""
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user="postgres.iqvzkdbychgnwmwcyhbj",
                password="$d9a-ARCHj65bRV",
                host="vFMQ33W%mZ&bFE#",
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

        # Filtros opcionales
        if kwargs.get('identification'):
            clauses.append("TRIM(cedulatitular) = TRIM(%s)")
            params.append(kwargs['identification'].strip())
        if kwargs.get('contract'):
            clauses.append("numerocontrato = %s")
            params.append(kwargs['contract'])
        if kwargs.get('receipt'):
            clauses.append("numero_de_recibo = %s")
            params.append(kwargs['receipt'])
        if kwargs.get('monto') is not None:
            clauses.append("valor_pagado = %s")
            params.append(kwargs['monto'])
        if kwargs.get('reference'):
            clauses.append("referencia = %s")
            params.append(kwargs['reference'])

        # Construir consulta con o sin filtros
        final_query = base_query + (" AND " + " AND ".join(clauses) if clauses else "")

        _logger.debug("Ejecutando query: %s", final_query)
        _logger.debug("Con parámetros: %s", params)
        cursor.execute(final_query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Mapear resultados a diccionarios
        return [
            {
                'cedula':     r[1],
                'contrato':   r[2],
                'recibo':     r[3],
                'fecha':      r[4],
                'monto':      r[5],
                'referencia': r[6],
            }
            for r in rows
        ]

    def update_external_record(self, monto, fecha, name):
        """Actualiza el registro externo que coincida con todas las claves."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE public.stg_src_oddo
               SET valor_pagado = %s,
                   fechaCompra  = %s
             WHERE name              = %s
        """, (monto, fecha, name))
        conn.commit()
        cur.close()
        conn.close()
        _logger.info("Registro externo actualizado: %s", name)

    def insert_external_record(self, identification, contract, receipt, monto, fecha, reference, name):
        """Inserta un nuevo registro en la base externa."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO public.stg_src_oddo
                (name,cedulatitular, numerocontrato, numero_de_recibo, valor_pagado, fechaCompra, referencia)
            VALUES (%s, TRIM(%s), %s, %s, %s, %s, %s)
        """, (name, identification.strip(), contract, receipt, monto, fecha, reference))
        conn.commit()
        cur.close()
        conn.close()
        _logger.info("Registro externo insertado: %s", name)