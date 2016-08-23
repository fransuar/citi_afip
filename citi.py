#! -*- coding: utf8 -*-
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.

from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from decimal import Decimal
import datetime
import calendar
import logging
logger = logging.getLogger(__name__)

__all__ = ['CitiExportar', 'CitiStart', 'CitiWizard']
__metaclass__ = PoolMeta

MONTHS = [
    ('1', 'January'),
    ('2', 'February'),
    ('3', 'March'),
    ('4', 'April'),
    ('5', 'May'),
    ('6', 'June'),
    ('7', 'July'),
    ('8', 'August'),
    ('9', 'September'),
    ('10', 'October'),
    ('11', 'November'),
    ('12', 'December')
]

TABLA_MONEDAS = {
    'ARS': 'PES',
    'USD': 'DOL',
    'UYU': '011',
    'BRL': '012',
    'DKK': '014',
    'NOK': '015',
    'CAD': '018',
    'CHF': '009',
    'BOB': '031',
    'COP': '032',
    'CLP': '033',
    'HKD': '051',
    'SGD': '052',
    'JMD': '053',
    'TWD': '054',
    'EUR': '060',
    'CNY': '064',
}

ALICUOTAS_IVA = {
    "No Gravado": "1",
    "Exento": "2",
    "0%": "3",
    "10.50%": "4",
    "21%": "5",
    "27%": "6",
    "5%": "8", # RG3337. Actualmente es el 3%
    "2,50%": "9",
}

NO_CORRESPONDE = [
    6,
    11,
    7,
    8,
    9,
    10,
    12,
    13,
    15,
    16,
    18,
    25,
    26,
    28,
    35,
    36,
    40,
    41,
    43,
    46,
    61,
    64,
    82,
    83,
    111,
    113,
    114,
    116,
    117,
]

class CitiStart(ModelView):
    'CITI Start'
    __name__ = 'citi.afip.start'
    month = fields.Selection(MONTHS,u'Month', sort=False, required=True)
    #period = fields.Many2One('account.period', 'Period', required=True)
    year = fields.Char(u'Year', required=True, size=4)


class CitiExportar(ModelView):
    'Exportar'
    __name__ = 'citi.afip.exportar'
    comprobante_compras = fields.Binary('Comprobante compras', readonly=True)
    alicuota_compras = fields.Binary('Alicuota compras', readonly=True)
    comprobante_ventas = fields.Binary('Comprobante ventas', readonly=True)
    alicuota_ventas = fields.Binary('Alicuota ventas', readonly=True)


class CitiWizard(Wizard):
    'CitiWizard'
    __name__ = 'citi.afip.wizard'

    start = StateView(
        'citi.afip.start',
        'citi_afip.citi_afip_start_view', [
            Button('Cancelar', 'end', 'tryton-cancel'),
            Button('Generar archivos', 'exportar_citi', 'tryton-ok', True),
        ])
    exportar = StateView(
        'citi.afip.exportar',
        'citi_afip.citi_afip_exportar_view', [
            Button('Volver a generar archivos', 'start', 'tryton-ok'),
            Button('Done', 'end', 'tryton-close'),
        ])
    exportar_citi = StateTransition()

    def default_start(self, fields):
        res = {}
        return res

    def default_exportar(self, fields):
        comprobante_compras = self.exportar.comprobante_compras
        alicuota_compras = self.exportar.alicuota_compras
        comprobante_ventas = self.exportar.comprobante_ventas
        alicuota_ventas = self.exportar.alicuota_ventas

        self.exportar.comprobante_compras = False
        self.exportar.alicuota_compras = False
        self.exportar.comprobante_ventas = False
        self.exportar.alicuota_ventas = False

        res = {
            'comprobante_compras': comprobante_compras,
            'alicuota_compras': alicuota_compras,
            'comprobante_ventas': comprobante_ventas,
            'alicuota_ventas': alicuota_ventas,
        }
        return res

    def transition_exportar_citi(self):
        logger.info('exportar CITI REG3685')
        self.exportar.message = u''
        year = int(self.start.year)
        month = int(self.start.month)
        monthrange = calendar.monthrange(year, month)
        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, monthrange[1])
        self.export_citi_alicuota_compras(start_date, end_date)
        self.export_citi_comprobante_compras(start_date, end_date)
        self.export_citi_alicuota_ventas(start_date, end_date)
        self.export_citi_comprobante_ventas(start_date, end_date)

        return 'exportar'


    def export_citi_alicuota_ventas(self, start_date, end_date):
        logger.info('exportar CITI REG3685 Alicuota Ventas')

        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', 'in', ['out_invoice','out_credit_note']), # Invoice, Credit Note
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
        ])
        lines = ""
        for invoice in invoices:
            tipo_comprobante = invoice.invoice_type.invoice_type.rjust(3,'0')
            punto_de_venta = invoice.number.split('-')[0].encode().rjust(5, '0')
            if int(punto_de_venta) in [33,99,331,332]:
                punto_de_venta = ''.rjust(5, '0') # se informan ceros.
            numero_comprobante = invoice.number.split('-')[1].encode().rjust(20, '0')

            importe_neto_gravado = Decimal('0')
            impuesto_liquidado = Decimal('0')
            for invoice_line in invoice.lines:
                if invoice_line.invoice_taxes is not ():
                    for invoice_tax in invoice_line.invoice_taxes:
                        if 'IVA' in invoice_tax.tax.group.code:
                            alicuota_id = str(invoice_tax.tax.sequence).rjust(4,'0')
                            importe_neto_gravado = invoice_line.amount
                            impuesto_liquidado = invoice_line.amount * invoice_tax.tax.rate
                            importe_neto_gravado = Currency.round(invoice.currency, importe_neto_gravado).to_eng_string().replace('.','').rjust(15,'0')
                            impuesto_liquidado = Currency.round(invoice.currency, impuesto_liquidado).to_eng_string().replace('.','').rjust(15,'0')
                            lines += tipo_comprobante + punto_de_venta + numero_comprobante + \
                                    importe_neto_gravado + alicuota_id + impuesto_liquidado + '\r\n'

        logger.info(u'Comienza attach alicuota de venta')
        self.exportar.alicuota_ventas = unicode(
            lines).encode('utf-8')

    def export_citi_comprobante_ventas(self, start_date, end_date):
        logger.info('exportar CITI REG3685 Comprobante Ventas')
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', 'in', ['out_invoice','out_credit_note']), # Invoice, Credit Note
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
        ])
        lines = ""
        for invoice in invoices:
            alicuotas = {
                "3": 0,
                "4": 0,
                "5": 0,
                "6": 0,
                "8": 0,
                "9": 0,
            }
            cant_alicuota = 0
            fecha_comprobante = invoice.invoice_date.strftime("%Y%m%d")
            tipo_comprobante = invoice.invoice_type.invoice_type.rjust(3,'0')
            punto_de_venta = invoice.number.split('-')[0].encode().rjust(5, '0')
            if int(punto_de_venta) in [33,99,331,332]:
                punto_de_venta = ''.rjust(5, '0') # se informan ceros.
            numero_comprobante = invoice.number.split('-')[1].encode().rjust(20, '0')
            #if int(punto_de_venta) in [33, 331, 332]:
            #    numero_comprobante = 'COE'
            numero_comprobante_hasta = invoice.number.split('-')[1].encode().rjust(20, '0')

            codigo_documento_comprador = invoice.party.tipo_documento
            if invoice.party.vat_number:
                # Si tenemos vat_number, entonces tenemos CUIT Argentino
                # use the Argentina AFIP's global CUIT for the country:
                identificacion_comprador = invoice.party.vat_number
            elif invoice.party.vat_number_afip_foreign:
                # use the VAT number directly
                identificacion_comprador = invoice.party.vat_number_afip_foreign
            else:
                identificacion_comprador = "0" # only "consumidor final"

            identificacion_comprador = identificacion_comprador.rjust(20,'0')
            if codigo_documento_comprador == '99':
                apellido_nombre_comprador = 'VENTA GLOBAL DIARIA'.ljust(30)
            else:
                s = invoice.party.name[:30].encode('utf8')
                apellido_nombre_comprador = "".join(x for x in s if x.isalnum()).ljust(30)

            importe_total = Currency.round(invoice.currency, invoice.total_amount).to_eng_string().replace('.','').rjust(15,'0')

            # iterar sobre lineas de facturas
            importe_total_lineas_sin_impuesto = Decimal('0') # se calcula
            percepcion_no_categorizados = Decimal('0') # se calcula
            importe_operaciones_exentas = Decimal('0') # 0
            importe_total_percepciones = Decimal('0') # 0
            importe_total_impuesto_iibb = Decimal('0') # se calcula
            importe_total_percepciones_municipales = Decimal('0') # 0
            importe_total_impuestos_internos = Decimal('0') # 0

            for line in invoice.lines:
                if line.invoice_taxes is ():
                    if int(tipo_comprobante) not in [19, 20, 21, 22]: # COMPROBANTES QUE NO CORESPONDE
                        importe_total_lineas_sin_impuesto += line.amount
                else:
                    for invoice_tax in line.invoice_taxes:
                        if 'IVA' in invoice_tax.tax.group.code:
                            #alicuota_id = str(invoice_tax.tax.sequence).rjust(4,'0')
                            alicuotas[str(invoice_tax.tax.sequence)] += 1
                        if 'PERCEPCION' in invoice_tax.tax.group.code:
                            importe_total_impuesto_iibb += line.amount * invoice_tax.tax.rate
                        if 'INTERNO' in invoice_tax.tax.group.code:
                            importe_total_impuestos_internos += line.amount * invoice_tax.tax.rate

            importe_total_lineas_sin_impuesto = Currency.round(invoice.currency, importe_total_lineas_sin_impuesto).to_eng_string().replace('.','').rjust(15,'0')
            percepcion_no_categorizados = Currency.round(invoice.currency, percepcion_no_categorizados).to_eng_string().replace('.','').rjust(15,'0')

            if invoice.party.iva_condition == 'exento' or invoice.party.iva_condition == 'no_alcanzado':
                importe_operaciones_exentas = Currency.round(invoice.currency, invoice.total_amount)
            importe_operaciones_exentas = Currency.round(invoice.currency, importe_operaciones_exentas).to_eng_string().replace('.','').rjust(15,'0')

            importe_total_percepciones = Currency.round(invoice.currency, importe_total_percepciones).to_eng_string().replace('.','').rjust(15,'0')
            importe_total_impuesto_iibb = Currency.round(invoice.currency, importe_total_impuesto_iibb).to_eng_string().replace('.','').rjust(15,'0')
            importe_total_percepciones_municipales = Currency.round(invoice.currency, importe_total_percepciones_municipales).to_eng_string().replace('.','').rjust(15,'0')
            importe_total_impuestos_internos = Currency.round(invoice.currency, importe_total_impuestos_internos).to_eng_string().replace('.','').rjust(15,'0')
            codigo_moneda = TABLA_MONEDAS[invoice.currency.code]
            if codigo_moneda != 'PES':
                ctz = Currency.round(invoice.currency, 1 / invoice.currency.rate)
                tipo_de_cambio =  str("%.6f" % ctz)
                tipo_de_cambio = tipo_de_cambio.replace('.','').rjust(10,'0')
            else:
                tipo_de_cambio = '0001000000'

            # recorrer alicuotas y saber cuantos tipos de alicuotas hay.
            for key, value in alicuotas.iteritems():
                if value != 0:
                    cant_alicuota += 1

            cantidad_alicuotas = str(cant_alicuota)
            if cant_alicuota == 0:
                cantidad_alicuotas = '1'
                if int(invoice.invoice_type.invoice_type) in [19, 20, 21, 22]: # Factura E
                    codigo_operacion = 'X'
                elif int(invoice.invoice_type.invoice_type) in NO_CORRESPONDE:
                    codigo_operacion = '0' # No corresponde
                elif invoice.party.iva_condition == 'exento': # Operacion exenta
                    codigo_operacion = 'E'
                else:
                    codigo_operacion = 'N'
            else:
                codigo_operacion = ' ' # Segun tabla codigo de operaciones.
            otros_atributos = '0'.rjust(15, '0')
            fecha_venc_pago = '0'.rjust(8, '0') #Opcional para resto de comprobantes. Obligatorio para liquidacion servicios clase A y B

            lines += fecha_comprobante + tipo_comprobante + punto_de_venta + numero_comprobante + numero_comprobante_hasta + \
                codigo_documento_comprador + identificacion_comprador + apellido_nombre_comprador + importe_total + \
                importe_total_lineas_sin_impuesto + percepcion_no_categorizados + importe_operaciones_exentas + importe_total_percepciones + \
                importe_total_impuesto_iibb + importe_total_percepciones_municipales + importe_total_impuestos_internos + \
                codigo_moneda + tipo_de_cambio + cantidad_alicuotas + codigo_operacion + \
                otros_atributos + fecha_venc_pago + '\r\n'

        logger.info(u'Comienza attach comprobante de venta')
        self.exportar.comprobante_ventas = unicode(
            lines).encode('utf-8')

    def export_citi_alicuota_compras(self, start_date, end_date):
        logger.info('exportar CITI REG3685 Comprobante Compras')
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', 'in', ['in_invoice', 'in_credit_note']), # Supplier Invoice, Supplier Credit Note
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
        ])
        lines = ""
        for invoice in invoices:
            if invoice.tipo_comprobante != None:
                tipo_comprobante = invoice.tipo_comprobante
                if int(invoice.tipo_comprobante) not in [63,64]: #resumenes bancarios
                    punto_de_venta = invoice.reference.split('-')[0].encode().rjust(5, '0')
                    numero_comprobante = invoice.reference.split('-')[1].encode().rjust(20, '0')
                    tipo_comprobante = '099'
                else:
                    punto_de_venta = '0'.rjust(5, '0')
                    numero_comprobante = invoice.reference.encode().rjust(20, '0')
                codigo_documento_vendedor = invoice.party.tipo_documento
                cuit_vendedor = invoice.party.vat_number.rjust(20,'0')

                importe_neto_gravado = Decimal('0')
                impuesto_liquidado = Decimal('0')
                for invoice_line in invoice.lines:
                    if invoice_line.invoice_taxes is not ():
                        for invoice_tax in invoice_line.invoice_taxes:
                            if 'IVA' in invoice_tax.tax.group.code:
                                alicuota_id = str(invoice_tax.tax.sequence).rjust(4,'0')
                                importe_neto_gravado = invoice_line.amount
                                impuesto_liquidado = invoice_line.amount * invoice_tax.tax.rate
                                importe_neto_gravado = Currency.round(invoice.currency, importe_neto_gravado).to_eng_string().replace('.','').rjust(15,'0')
                                impuesto_liquidado = Currency.round(invoice.currency, impuesto_liquidado).to_eng_string().replace('.','').rjust(15,'0')
                                lines += tipo_comprobante + punto_de_venta + numero_comprobante + \
                                    codigo_documento_vendedor + cuit_vendedor + importe_neto_gravado + \
                                    alicuota_id + impuesto_liquidado + '\r\n'

        logger.info(u'Comienza attach alicuota de compras')
        self.exportar.alicuota_compras = unicode(
            lines).encode('utf-8')

    def export_citi_comprobante_compras(self, start_date, end_date):
        logger.info('exportar CITI REG3685 Comprobante Compras')
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        invoices = Invoice.search([
            ('state', 'in', ['posted', 'paid']),
            ('type', 'in', ['in_invoice', 'in_credit_note']), # Supplier Invoice, Supplier Credit Note
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', end_date),
        ])

        lines = ""
        for invoice in invoices:
            alicuotas = {
                "3": 0,
                "4": 0,
                "5": 0,
                "6": 0,
                "8": 0,
                "9": 0,
            }
            cant_alicuota = 0
            if invoice.tipo_comprobante != None:
                fecha_comprobante = invoice.invoice_date.strftime("%Y%m%d")
                tipo_comprobante = invoice.tipo_comprobante
                if int(invoice.tipo_comprobante) not in [63,64]: #resumenes bancarios
                    punto_de_venta = invoice.reference.split('-')[0].encode().rjust(5, '0')
                    numero_comprobante = invoice.reference.split('-')[1].encode().rjust(20, '0')
                    tipo_comprobante = '099'
                else:
                    punto_de_venta = '0'.rjust(5, '0')
                    numero_comprobante = invoice.reference.encode().rjust(20, '0')

                despacho_importacion = ''.ljust(16)

                codigo_documento_vendedor = invoice.party.tipo_documento
                identificacion_vendedor = invoice.party.vat_number.rjust(20,'0')
                s = invoice.party.name[:30].encode('utf8')
                apellido_nombre_vendedor = "".join(x for x in s if x.isalnum()).ljust(30)
                importe_total = Currency.round(invoice.currency, invoice.total_amount).to_eng_string().replace('.','').rjust(15,'0')

                # iterar sobre lineas de facturas
                importe_total_lineas_sin_impuesto = Decimal('0') # se calcula
                importe_operaciones_exentas = Decimal('0') # 0
                importe_total_impuesto_iva = Decimal('0') # se calcula
                importe_total_percepciones = Decimal('0') # 0
                importe_total_impuesto_iibb = Decimal('0') # se calcula
                importe_total_percepciones_municipales = Decimal('0') # 0
                importe_total_impuestos_internos = Decimal('0') # 0

                for line in invoice.lines:
                    if line.invoice_taxes is ():
                        if int(invoice.tipo_comprobante) not in NO_CORRESPONDE: # COMPROBANTES QUE NO CORESPONDE
                            importe_total_lineas_sin_impuesto += line.amount
                    else:
                        for invoice_tax in line.invoice_taxes:
                            if 'IVA' in invoice_tax.tax.group.code:
                                #importe_total_impuesto_iva += invoice_tax.amount
                                alicuotas[str(invoice_tax.tax.sequence)] += 1
                            if 'PERCEPCION' in invoice_tax.tax.group.code:
                                importe_total_impuesto_iibb += line.amount * invoice_tax.tax.rate

                importe_total_lineas_sin_impuesto = Currency.round(invoice.currency, importe_total_lineas_sin_impuesto).to_eng_string().replace('.','').rjust(15,'0')

                if invoice.party.iva_condition == 'exento' or invoice.party.iva_condition == 'no_alcanzado':
                    if int(invoice.tipo_comprobante) not in NO_CORRESPONDE: # COMPROBANTES QUE NO CORESPONDE
                        importe_operaciones_exentas = Currency.round(invoice.currency, invoice.total_amount)
                importe_operaciones_exentas = Currency.round(invoice.currency, importe_operaciones_exentas).to_eng_string().replace('.','').rjust(15,'0')

                importe_total_impuesto_iva = Currency.round(invoice.currency, importe_total_impuesto_iva).to_eng_string().replace('.','').rjust(15,'0')
                importe_total_impuesto_iibb = Currency.round(invoice.currency, importe_total_impuesto_iibb).to_eng_string().replace('.','').rjust(15,'0')

                importe_total_percepciones = Currency.round(invoice.currency, importe_total_percepciones).to_eng_string().replace('.','').rjust(15,'0')
                importe_total_percepciones_municipales = Currency.round(invoice.currency, importe_total_percepciones_municipales).to_eng_string().replace('.','').rjust(15,'0')
                importe_total_impuestos_internos = Currency.round(invoice.currency, importe_total_impuestos_internos).to_eng_string().replace('.','').rjust(15,'0')
                codigo_moneda = TABLA_MONEDAS[invoice.currency.code]
                #tipo_de_cambio = '0001000000'
                #tipo_de_cambio = invoice.currency.rate.to_eng_string().replace('.','').rjust(10,'0')
                codigo_moneda = TABLA_MONEDAS[invoice.currency.code]
                if codigo_moneda != 'PES':
                    ctz = Currency.round(invoice.currency, 1 / invoice.currency.rate)
                    tipo_de_cambio =  str("%.6f" % ctz)
                    tipo_de_cambio = tipo_de_cambio.replace('.','').rjust(10,'0')
                else:
                    tipo_de_cambio = '0001000000'

                # recorrer alicuotas y saber cuantos tipos de alicuotas hay.
                for key, value in alicuotas.iteritems():
                    if value != 0:
                        cant_alicuota += 1

                cantidad_alicuotas = str(cant_alicuota)
                if cant_alicuota == 0:
                    if int(invoice.tipo_comprobante) in [19, 20, 21, 22]: # Factura E
                        codigo_operacion = 'X'
                    elif int(invoice.tipo_comprobante) in NO_CORRESPONDE: # COMPROBANTES QUE NO CORESPONDE
                        codigo_operacion = '0' # No corresponde
                    elif invoice.party.iva_condition == 'exento': # Operacion exenta
                        codigo_operacion = 'E'
                    else:
                        codigo_operacion = 'N'
                else:
                    codigo_operacion = ' ' # Segun tabla codigo de operaciones.
                credito_fiscal_computable = '0'.rjust(15, '0')
                otros_atributos = '0'.rjust(15, '0')

                if int(tipo_comprobante) in [33,58,59,60,63]:
                    cuit_emisor = invoice.party.vat_number.rjust(11,'0')
                    denominacion_emisor = apellido_nombre_vendedor
                    iva_comision = Currency.round(invoice.currency, invoice.total_amount - (invoice.total_amount / Decimal('1.21'))).to_eng_string().replace('.','').rjust(15,'0')
                else:
                    cuit_emisor = '0'.rjust(11, '0')
                    denominacion_emisor = ' '.rjust(30)
                    iva_comision = '0'.rjust(15, '0')

                lines += fecha_comprobante + tipo_comprobante + punto_de_venta + numero_comprobante + despacho_importacion + \
                    codigo_documento_vendedor + identificacion_vendedor + apellido_nombre_vendedor + importe_total + \
                    importe_total_lineas_sin_impuesto + importe_operaciones_exentas + importe_total_impuesto_iva + importe_total_percepciones + \
                    importe_total_impuesto_iibb + importe_total_percepciones_municipales + importe_total_impuestos_internos + \
                    codigo_moneda + tipo_de_cambio + cantidad_alicuotas + codigo_operacion + credito_fiscal_computable + \
                    otros_atributos + cuit_emisor + denominacion_emisor + iva_comision + '\r\n'


        logger.info('Comienza attach comprobante compra')
        self.exportar.comprobante_compras = unicode(
            lines).encode('utf-8')
