# Bitácora

Registro de sesiones de desarrollo. Cada entrada documenta **qué se construyó, qué se decidió y por qué** — el porqué es lo que no se puede reconstruir leyendo el código después.

---

## Plantilla

```markdown
## AAAA-MM-DD — Título de la sesión

**Objetivo:** qué se quería lograr al empezar.

**Construido:**
- componente o cambio concreto

**Decisiones:**
- Decisión tomada. Alternativa descartada y motivo.

**Problemas y causa raíz:**
- Síntoma → causa real → solución. No solo "se arregló".

**Deuda asumida:**
- Atajo consciente y bajo qué condición se paga.

**Siguiente:**
- lo inmediato
```

---

## 2026-08-14 — Del scoring roto al radar funcionando

**Objetivo:** arreglar un tracker de vacantes que puntuaba todo por debajo de 27% y no servía para decidir nada.

**Diagnóstico inicial.** El problema no era el umbral, era el modelo. Un puntaje único agregaba stack, inglés, seniority y ubicación en un número que no permitía saber qué componente hundía el resultado. Un score bajo no dice qué hacer el lunes; un desglose por dimensión sí.

**Hallazgos de investigación:**
- La cifra de que "el 75% de los CV son rechazados por el ATS" no tiene respaldo. Se rastrea a un pitch comercial de 2012 de una empresa que ya no existe. La mayoría de fuentes que la repiten venden optimización de CV.
- El corte real no está en el match de keywords sino en las preguntas de knockout y en los fallos de parseo.
- Varios ATS presentan candidatos al reclutador en orden de llegada, no por puntaje. El timing pesa más que la optimización del CV.
- Entre 18% y 27% de los avisos son vacantes fantasma. Costo estimado: ~9 horas por ciclo.

**Consecuencia:** el producto cambió. Dejó de ser un puntuador de CV y pasó a ser un detector de vacantes frescas y vivas. El match quedó como segunda etapa, no como primera.

**Construido:**
- `verificar_tokens.py` — recibe URLs completas de ATS, extrae fuente y token con `urlparse`, verifica el feed y genera `empresas.csv` con las cuatro columnas listas para importar
- Flujo de n8n de 8 nodos: schedule → leer empresas → HTTP → normalizar → leer registro → deduplicar → prefiltrar → IF → puntuar → guardar
- Esquema de dos hojas en Google Sheets
- `perfil.json` — perfil profesional estructurado como datos, no como prosa
- Vista `candidatas` con fórmula de Sheets

**Decisiones:**
- **Sin historial ni estadísticas.** Solo deduplicación. La detección de vacantes de 24h sale gratis de la dedup: si la clave no está en el registro, es nueva. No hacía falta una capa analítica.
- **Doble clave de dedup.** Clave técnica más huella de contenido, porque la republicación con id nuevo burlaría la primera.
- **Lista blanca, no negra**, tanto en títulos como en ubicaciones.
- **Google Sheets sobre Postgres.** Volumen bajo, sin concurrencia, y hace falta marcar filas a mano.
- **Inglés no descarta.** Se marca como riesgo de entrevista. Usarlo como knockout eliminaba el 70% del mercado remoto.
- **Los 25 años de experiencia no técnica se traducen, no se listan.** Se convirtieron en una dimensión de scoring (`contexto_negocio`) en vez de un párrafo genérico de CV.
- **La vista `candidatas` es una fórmula, no un nodo.** No se agrega un paso al pipeline para algo que es presentación.

**Problemas y causa raíz:**
- *El flujo se detenía en `Leer registro`.* La hoja estaba vacía → cero items → en n8n un nodo sin entrada no se ejecuta. Solución: `Always Output Data` más un filtro del item vacío en el código. Solo ocurre en el arranque, que es justo el tipo de bug más difícil de encontrar después.
- *Todo puntuaba bajo.* El nodo de normalización descartaba el campo `content` pese a pedirlo en la URL. Sin descripción, el scoring solo leía el título.
- *La fórmula de la vista devolvía `#N/A`.* Se asumieron 13 columnas; había 17, con `motivo` duplicada y `descripcion` guardándose sin necesidad. Las letras estaban corridas. Se resolvió midiendo con `CONTAR.SI` una condición a la vez, no cambiando la fórmula al azar.
- *Solo aparecían vacantes de Greenhouse.* No era un bug: las cuatro empresas cargadas eran de Greenhouse. Revisar la entrada antes de sospechar del código.

**Resultados:**
- 249 vacantes capturadas de 4 empresas
- Deduplicación validada: segunda ejecución consecutiva → 0 duplicados
- Prefiltro: 71 pasan, 178 marcadas y registradas
- Vista `candidatas`: ~20 finalistas

**Deuda asumida:**
- Las listas del prefiltro están duplicadas entre `perfil.json` y los nodos de n8n. Dos copias de la misma verdad; van a divergir. Se paga moviendo el perfil a una hoja del Sheet.
- Columna `motivo` duplicada y `descripcion` innecesaria en el Sheet. Al eliminarlas se corren las letras de columna y hay que ajustar la fórmula.

**Siguiente:**
- Capa 2b: análisis con LLM sobre las mejores candidatas, comparando requerimiento contra evidencia del perfil
- Cosechar tokens de Lever y Ashby para diversificar fuentes
- Publicar en GitHub sin `perfil.json` ni `empresas.csv`
