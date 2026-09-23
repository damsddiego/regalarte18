# Configuración autorizada de Regalarte: 16 de septiembre de 2026

El cliente autorizó cancelar administrativamente las 39 sesiones anteriores,
asignar `admin2@regalartecr.com` como Jefatura y usar los feriados oficiales de
Costa Rica. Se ejecutó en `RegalarteProd` mediante ORM, primero con reversión
y después confirmando una única transacción. No se reinició el servicio.

## Resultado

- Las 39 sesiones y sus 269 líneas quedaron canceladas, conservando cantidades,
  capturas e historial. Cada sesión tiene el motivo en su ficha y en el chatter.
- Las 269 existencias conservaron exactamente sus cantidades físicas y
  reservadas durante la operación. Se retiraron sus propuestas de conteo
  canceladas y se liberaron los cupos. No se aplicaron ajustes.
- La bodega Regalarte (ID 1) quedó con cero cupos ocupados al terminar.
- Se asignó como Jefatura al usuario existente `admin2@regalartecr.com` (ID 10).
  Ya tenía permiso de Jefatura; no se le concedió Gerencia.
- Se creó un calendario exclusivo para conteos (ID 4), lunes a viernes,
  07:30–17:00, zona `America/Costa_Rica`, con los 12 feriados oficiales de 2026.
  No se modificó el calendario laboral de la compañía.
- Se verificaron cinco vencimientos mediante el método real del módulo:
  lunes normal, feriados del 15 de septiembre y 1 de diciembre, Navidad con
  fin de semana y Semana Santa. Se validaron las horas 07:30 y 17:00.
- No se enviaron notificaciones de correo ni de bandeja de entrada durante
  la cancelación administrativa; las notas de auditoría se conservaron.

Fuente: [MTSS, calendario oficial de feriados de 2026](https://www.mtss.go.cr/temas-laborales/feriados/feriados_calendario_2026.pdf),
CARTA-MTSS-DAJ-AER-1076-2025. Se incluyen los feriados de pago obligatorio y
no obligatorio, sin trasladar al lunes los que coinciden con fin de semana.
Los feriados de años posteriores requieren carga y verificación anual;
el módulo no descarga automáticamente calendarios del MTSS.

## Evidencia y ejecución

Script: `configure_regalarte_20260916.py`. Por defecto revierte; únicamente
confirma si se establece `APPLY=True`. Verifica los 39 identificadores
autorizados, su bodega, estado, vinculación a existencias y ausencia de
solicitudes manuales superpuestas. Bloquea sesiones y existencias mientras
comprueba y cancela. Cualquier error revierte toda la transacción.

Respaldo previo a confirmar, con acceso restringido:
`/opt/odoo18/backups/sng_cycle_control/20260916/194807999080_apply.json`.
Contiene las sesiones, líneas, existencias, actividades y configuración
anterior de la bodega. No debe importarse directamente sobre datos nuevos.

La estructura de control ya estaba instalada y la migración registrada el
12 de septiembre. Esta operación configuró datos y canceló las sesiones
autorizadas; no realizó una actualización de módulos ni verificó la versión
del código cargado en cada proceso del servicio web.
