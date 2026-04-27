# models/__init__.py
# -*- coding: utf-8 -*-
from __future__ import annotations

# ============================================================
# SEGURIDAD / ACCESO
# ============================================================

from .auth.usuario import Rol, Usuario

# ============================================================
# MAESTROS
# ============================================================

from .maestros.cliente import Cliente
from .maestros.proveedor import (
    Proveedor,
    ProveedorBanco,
    ProveedorContacto,
    ProveedorDireccion,
)

# ============================================================
# COMERCIAL
# ============================================================

from .leasing_operativo.models import (
    LeasingOpActivoDepreciacion,
    LeasingOpActivoFijo,
    LeasingOpComite,
    LeasingOpContrato,
    LeasingOpCostoPlantilla,
    LeasingOpCuota,
    LeasingOpDocumentoProceso,
    LeasingOpHistorial,
    LeasingOpParametroTipo,
    LeasingOpPolitica,
    LeasingOpSimulacion,
    LeasingOpTipoActivo,
)
from .comercial.credito_riesgo import (
    CreditoComite,
    CreditoDocumento,
    CreditoEvaluacion,
    CreditoGarantia,
    CreditoHistorial,
    CreditoPolitica,
    CreditoSolicitud,
)
from .comercial.leasing_financiero_credito import LeasingFinancieroAnalisisCredito
from .comercial.leasing_financiero_cotizacion import LeasingFinancieroCotizacion, LeasingFinancieroProyeccionLinea
from .comercial.nota_venta import NotaVenta, NotaVentaDetalle
from .comercial.orden_servicio import OrdenServicio
from .comercial.orden_servicio_linea import OrdenServicioCotizacionLinea
from .comercial.vehiculo import Vehiculo

# ============================================================
# COBRANZA
# ============================================================

from .cobranza.cuentas_por_cobrar import CuentaPorCobrar, PagoCliente

# ============================================================
# COMUNICACIONES
# ============================================================

from .comunicaciones.email_log import EmailLog

# ============================================================
# POSTVENTA / CRM
# ============================================================

from .postventa.postventa import PostventaCasoEvento, PostventaInteraccion, PostventaSolicitud

# ============================================================
# INVENTARIO
# ============================================================

from .inventario.inventario import (
    CategoriaProducto,
    UnidadMedida,
    Producto,
    InventarioMovimiento,
)

# ============================================================
# FINANZAS / CAJA
# ============================================================

from .finanzas.caja import Caja, MovimientoCaja

# ============================================================
# FINANZAS / CONTABILIDAD
# ============================================================

from .finanzas.plan_cuentas import PlanCuenta
from .finanzas.contabilidad_asientos import AsientoContable, AsientoDetalle

# ============================================================
# FINANZAS / COMPRAS / CUENTAS POR PAGAR
# ============================================================

from .finanzas.compras_finanzas import (
    ProveedorFin,
    CategoriaGasto,
    CentroCosto,
    Periodo,
    APDocumento,
    APDocumentoDetalle,
    APDocumentoImpuesto,
    APPago,
    APPagoAplicacion,
)

# ============================================================
# FONDOS POR RENDIR / TRANSPORTE
# ============================================================

from .fondos_rendir.empleado import Empleado
from .fondos_rendir.vehiculo_transporte import VehiculoTransporte
from .fondos_rendir.fondo_rendir import (
    ESTADOS_FONDO,
    FondoRendir,
    FondoRendirGasto,
)
from .fondos_rendir.flota_mantencion import FlotaMantencion, TIPOS_MANTENCION

# ============================================================
# TRANSPORTE / HOJAS DE RUTA
# ============================================================

from .transporte.viaje import ESTADOS_VIAJE, TransporteViaje

__all__ = [
    "Rol",
    "Usuario",
    "Cliente",
    "Proveedor",
    "ProveedorBanco",
    "ProveedorContacto",
    "ProveedorDireccion",
    "NotaVenta",
    "NotaVentaDetalle",
    "LeasingFinancieroAnalisisCredito",
    "LeasingFinancieroCotizacion",
    "LeasingFinancieroProyeccionLinea",
    "CreditoPolitica",
    "CreditoSolicitud",
    "CreditoEvaluacion",
    "CreditoGarantia",
    "CreditoDocumento",
    "CreditoComite",
    "CreditoHistorial",
    "LeasingOpTipoActivo",
    "LeasingOpPolitica",
    "LeasingOpCostoPlantilla",
    "LeasingOpSimulacion",
    "LeasingOpActivoFijo",
    "LeasingOpActivoDepreciacion",
    "LeasingOpParametroTipo",
    "LeasingOpContrato",
    "LeasingOpCuota",
    "LeasingOpDocumentoProceso",
    "LeasingOpComite",
    "LeasingOpHistorial",
    "OrdenServicio",
    "OrdenServicioCotizacionLinea",
    "Vehiculo",
    "CuentaPorCobrar",
    "PagoCliente",
    "EmailLog",
    "PostventaInteraccion",
    "PostventaSolicitud",
    "PostventaCasoEvento",
    "CategoriaProducto",
    "UnidadMedida",
    "Producto",
    "InventarioMovimiento",
    "Caja",
    "MovimientoCaja",
    "PlanCuenta",
    "AsientoContable",
    "AsientoDetalle",
    "ProveedorFin",
    "CategoriaGasto",
    "CentroCosto",
    "Periodo",
    "APDocumento",
    "APDocumentoDetalle",
    "APDocumentoImpuesto",
    "APPago",
    "APPagoAplicacion",
    "Empleado",
    "VehiculoTransporte",
    "ESTADOS_FONDO",
    "FondoRendir",
    "FondoRendirGasto",
    "FlotaMantencion",
    "TIPOS_MANTENCION",
    "ESTADOS_VIAJE",
    "TransporteViaje",
]