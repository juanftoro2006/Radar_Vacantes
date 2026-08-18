# Esquema de las hojas

El nodo `Guardar nuevas` usa `autoMapInputData`: **los encabezados del Sheet deben llamarse exactamente igual que las claves del JSON.** Si un encabezado no coincide, esa columna se guarda vacía sin error.

---

## Hoja `empresas` — fuentes a consultar

La genera `verificar_tokens.py`. Se importa a mano.

| Col | Campo | Ejemplo | Notas |
|---|---|---|---|
| A | `empresa` | `Sezzle` | Nombre legible. Entra en `clave` y `huella` |
| B | `fuente` | `greenhouse` | `greenhouse` \| `lever` \| `ashby`. Elige el mapeo en Normalizar |
| C | `token` | `sezzle` | Identificador de la empresa en el ATS |
| D | `plantilla_url` | `https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true` | `{t}` se sustituye por el token |

---

## Hoja `vacantes` — registro completo

**16 columnas, A–P.** Se guarda todo (incluso lo descartado por el prefiltro): el registro sirve a la deduplicación, el puntaje sirve a la decisión.

| Col | Campo | Lo escribe | Notas |
|---|---|---|---|
| A | `id_externo` | Normalizar | ID en el ATS. No es único entre empresas |
| B | `titulo` | Normalizar | |
| C | `ubicacion` | Normalizar | `sin especificar` si el feed no la trae |
| D | `url` | Normalizar | Enlace a la vacante |
| E | `descripcion` | Normalizar | HTML limpio, tope 3500 caracteres |
| F | `empresa` | Normalizar | |
| G | `fuente` | Normalizar | |
| H | `clave` | Normalizar | `fuente:empresa:id_externo` — **dedup 1** |
| I | `huella` | Normalizar | `empresa:titulo_normalizado` — **dedup 2**, sobrevive a republicación |
| J | `descubierta` | Normalizar | `AAAA-MM-DD`. Fecha de detección, no de publicación |
| K | `estado` | Normalizar | `nueva`. Se edita a mano al postular |
| L | `prefiltro` | Prefiltro | `si` \| `no` |
| M | `motivo` | Prefiltro | Por qué pasó o por qué no |
| N | `puntaje` | Puntuar | 0–10. **Vacío = no se evaluó. Cero = evaluada y descartada.** No son lo mismo |
| O | `desglose` | Puntuar | `stack X (bruto Y) \| seniority Z \| contexto W` |
| P | `banderas` | Puntuar | `KNOCKOUT` / `BRECHA` / `RIESGO`, separadas por `\|\|` |

Las que no pasan el prefiltro llegan por la rama falsa del `If` y se guardan **sin** N, O ni P. Esas celdas quedan vacías a propósito.

---

## Hoja `candidatas` — vista filtrada

No es un nodo del flujo: es presentación, y la presentación no se paga con un paso de pipeline.

Fórmula en `A1` (deja la hoja vacía, la fórmula expande sola):

```
=SORT(
  FILTER(
    {vacantes!N2:N, vacantes!B2:B, vacantes!F2:F, vacantes!C2:C, vacantes!P2:P, vacantes!D2:D, vacantes!J2:J},
    (vacantes!L2:L="si") * (vacantes!N2:N>=5) * (vacantes!N2:N<>"")
  ),
  1, FALSE
)
```

Devuelve: puntaje, título, empresa, ubicación, banderas, url, fecha — ordenado por puntaje descendente.

**Por qué `N<>""` además de `N>=5`:** una celda vacía se compara como 0 en algunas condiciones y puede colarse. Es la traducción literal de "celda vacía no es cero".

**Si sale `#N/A`:** ninguna fila cumple. Diagnostica una condición a la vez antes de tocar la fórmula:

```
=CONTAR.SI(vacantes!L2:L; "si")      → cuántas pasan el prefiltro
=CONTAR.SI(vacantes!N2:N; ">=5")     → cuántas superan el umbral
```

Si la primera da 0, el problema está en el prefiltro. Si la segunda da 0, baja el umbral. **Nunca cambies la fórmula al azar: mide primero.**

**Si cambias las columnas de `vacantes`, esta fórmula se rompe** — las letras se corren. Actualiza esta tabla en el mismo commit.
