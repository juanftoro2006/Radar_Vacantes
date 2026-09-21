# v1: n8n + Google Sheets (retirada en sep-2026)

`workflow.json` es el export saneado del flujo de 10 nodos (ago-2026). Se conserva como referencia.

Por qué se retiró:

- Corría en Railway. Al perderse el acceso, el radar dejó de correr sin que nada lo avisara.
- El flujo real vivía solo dentro de n8n: dos veces lo publicado en el repo no fue lo que corría.
- Las listas del prefiltro estaban duplicadas entre los nodos y `perfil.json`.

Diferencias de lógica con la v2 (detalle en la BITACORA, entrada 2026-09-21): descripción recortada a 3500 caracteres antes de puntuar, ubicación con lista negra de países, huella de dedup permanente, ventana de 48h, `senior` = 0 en todos los roles.

Nota: en este export `Leer registro` no tiene `executeOnce`. El flujo real sí lo tenía; si alguien lo importa tal cual, lee la hoja completa una vez por cada vacante.
