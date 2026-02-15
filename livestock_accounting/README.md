# Módulo de Contabilidad Ganadera para Odoo 19

Este módulo implementa una solución integral de **registro de ganado y coste histórico**:

## Funcionalidades

- Ficha de ganado por categorías: **Nacimientos, Desarrollo y Producción**.
- Control de pesos por fecha y cálculo automático del **peso actual**.
- Estado del ganado: **En inventario, Dado de baja o Vendido**.
- Registro del **coste histórico** por animal.
- Asignación de costes desde líneas de facturas de proveedor publicadas.
- Métodos de asignación: **igualitario, por peso y por edad**.
- Campo de categoría ganadera en líneas de factura para trazabilidad contable.
- Registro sanitario y bienestar por animal.
- Formulario de **movimientos masivos** para registrar pesos, eventos sanitarios, bajas y reclasificación por categoría con histórico por animal.
- Evidencia de baja/venta con motivo y notas para auditoría.

## Aportes de cumplimiento y buenas prácticas

Además de los campos solicitados, se agregaron controles para reforzar la trazabilidad:

1. Identificación individual (código y arete).
2. Historial sanitario y de bienestar animal.
3. Motivo obligatorio cuando hay baja o venta.
4. Chatter y actividades para evidencia de decisiones contables.

Estos elementos ayudan a sostener un expediente técnico-contable robusto por activo biológico.
