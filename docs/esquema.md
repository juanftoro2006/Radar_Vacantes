# Esquema de datos

## `config/empresas.csv`: fuentes a consultar

| Columna | Ejemplo | Notas |
|---|---|---|
| `empresa` | `Nubank` | Nombre legible. Solo para mostrar |
| `fuente` | `ashby` | `greenhouse` \| `lever` \| `ashby`. Elige URL y mapeo en `radar/fuentes.py` |
| `token` | `nubank` | Identificador en el ATS. Entra en `clave` y `huella` |
| `activa` | `si` | `no` la desactiva sin borrarla (queda el porqué en `nota`) |
| `nota` | `se mudo de Greenhouse a Ashby` | Libre |

La URL del feed ya no vive en la hoja: es estructura del ATS, no un valor por empresa.

## `config/radar.json`: qué cuenta como encaje

Única fuente de verdad de listas, pesos y umbrales. Se valida con pydantic al arrancar (`radar/config.py`): un campo faltante o pesos que no suman 1 detienen la corrida con un mensaje claro. Las claves que empiezan con `_` son comentarios.

## `data/vacantes.csv`: registro completo

Se guarda **todo** lo descargado, pase o no el filtro.

| Columna | Lo escribe | Notas |
|---|---|---|
| `n` | pipeline | Número corto y estable. Es el que usas en `/visto 12` |
| `clave` | pipeline | `fuente:token:id_externo`. **Dedup 1** |
| `huella` | pipeline | `token:titulo_normalizado`. **Dedup 2**, ventana de 30 días entre avisos |
| `empresa`, `fuente`, `token`, `id_externo` | fuentes | |
| `titulo`, `ubicacion`, `url` | fuentes | Ubicaciones múltiples unidas con ` / ` |
| `publicada` | fuentes | ISO 8601 del ATS. Vacía si el ATS no la da (nunca inventada) |
| `descubierta` | pipeline | ISO 8601, hora Bogotá. Primera vez que el radar la vio |
| `cerrada` | pipeline | Fecha en que desapareció del feed (solo si la fuente respondió bien) |
| `prefiltro` | prefiltro | `si` \| `no` |
| `motivo` | prefiltro | Siempre explica la decisión |
| `tipo_rol` | puntaje | `desarrollo` \| `automatizacion`: decide la escala de seniority |
| `puntaje` | puntaje | 0–10. **Vacío = no se evaluó. Cero = evaluada y descartada** |
| `desglose` | puntaje | `stack X (bruto Y) \| seniority Z (nivel, tipo) \| contexto W` |
| `banderas` | puntaje | `KNOCKOUT` / `BRECHA` / `RIESGO`, separadas por ` \|\| ` |
| `estado` | pipeline / tú | `nueva` \| `vista` (con `/visto`) \| `duplicada` |
| `notificada` | pipeline | Cuándo se avisó por Telegram. Vacía = no avisada (se reintenta) |

La descripción **no** se guarda: se lee completa en memoria para puntuar y se descarta. Para releerla está la `url`.

## Regla de candidata

Todo en `radar/pipeline.py::es_candidata`:

```
prefiltro = si
y puntaje >= umbral (5.0)
y sin KNOCKOUT
y no cerrada
y estado = nueva
y publicada (o descubierta, si no hay fecha) hace <= 7 dias
```

Después, entre las candidatas no avisadas, la huella decide: si la misma empresa ya avisó el mismo título hace menos de 30 días, la nueva queda `duplicada`.

## `data/estado.json`: estado del bot

| Campo | Para qué |
|---|---|
| `telegram_offset` | Último mensaje de Telegram procesado; evita aplicar un `/visto` dos veces |
| `ultimo_resumen` | Fecha (Bogotá) del último resumen diario |
| `ultima_corrida` | Marca de tiempo de la última corrida |
| `fuentes` | Por token: `ok`, `detalle` y `desde` cuándo está en ese estado |
