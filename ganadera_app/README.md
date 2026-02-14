# Ganadería - Aplicación (Odoo 19)

Este módulo convierte la solución en una **aplicación instalable independiente** dentro de Odoo.

## Objetivo

- Publicar una app principal (`ganadera_app`) para instalar desde Apps.
- Mantener la lógica funcional en `livestock_accounting`.

## Funcionamiento

- `ganadera_app` depende de `livestock_accounting`.
- Al instalar `ganadera_app`, Odoo instala automáticamente el módulo base y habilita sus menús, modelos y seguridad.
