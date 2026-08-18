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

---

## 2026-08-18 — Auditoría: lo publicado no era lo que funcionaba

**Objetivo:** auditar el proyecto completo antes de dejarlo corriendo automático y publicarlo.

**Hallazgo raíz.** Había tres versiones del sistema que debían ser una sola:

| Fuente | Qué decía |
|---|---|
| Bitácora | flujo de 8 nodos con prefiltro, IF y scoring |
| README | "Funcionando en producción" |
| `workflow.json` versionado | 7 nodos, sin prefiltro, sin IF, sin scoring |

El `workflow.json` del repo era la plantilla original, nunca un export del flujo real. Prueba: contenía `PEGA_AQUI_EL_ID_DEL_SHEET`, no capturaba `content` (el bug ya corregido en n8n) y le faltaba el `alwaysOutputData` documentado como solución al bloqueo del arranque. El flujo verdadero vivía solo dentro de n8n, sin respaldo en ninguna parte.

Al comparar contra el export real (10 nodos) se confirmó que el código en n8n ya resolvía casi todo lo señalado: validación de desalineación con `throw`, log de omitidas, Ashby en el mapeo, limpieza de HTML con techo de 3500 caracteres. **La auditoría no encontró un sistema malo: encontró un sistema bueno mal publicado.**

**Construido:**
- `workflow.json` — reemplazado por el export real de 10 nodos, saneado
- `perfil.ejemplo.json` — plantilla pública con datos ficticios
- `docs/esquema.md` — las 16 columnas A–P de la hoja `vacantes`, la fórmula de `candidatas` y su procedimiento de diagnóstico
- `perfil.json` — reestructurado para reflejar exactamente lo que ejecutan los nodos
- Nodos `Prefiltro` y `Puntuar` reescritos
- `requirements.txt` regenerado en UTF-8
- `.gitignore` ampliado

**Decisiones:**

- **El export de n8n se sanea antes de versionarse.** El crudo traía el ID del Google Sheet, tres bloques de credenciales y el `instanceId`. En un repo público eso entrega la hoja y la estrategia de búsqueda. Se sustituyen por placeholders. Alternativa descartada: repo privado — el objetivo es que sea portafolio.
- **La escala del stack pasa de `min(10, bruto)` a `bruto / 25`.** El techo saturaba con 5 términos fuertes, y como la lista incluye `api`, `python` e `integration`, casi toda vacante de backend topaba en 10. Medido: la vacante ideal y un PHP legacy empataban en 6.5. Con la escala nueva: 6.4 contra 3.5. El ranking vuelve a discriminar.
- **Toda comparación de términos usa límite de palabra (`\b`), no `includes`.** Sin eso `api` matcheaba "ther**api**st", `ml` matcheaba "ht**ml**", `ai` matcheaba "ch**ai**r" y `uk` matcheaba "**Uk**raine". El parche anterior (`' ai'` con espacio inicial) fallaba al principio del título.
- **Presencial deja de ser KNOCKOUT y pasa a RIESGO.** El patrón viejo (`on-site|in-office|hybrid|relocat`) corría sobre 3500 caracteres: cualquier vacante remota que mencionara una oficina moría en 0. Ahora solo descarta con exigencia explícita ("N días en oficina", "must relocate"). Caso medido: una vacante que decía *"we do not offer relocation... fully distributed"* pasó de 0 a 5. **Esto contradecía el propio principio de asimetría del README: un falso negativo cuesta una oportunidad.**
- **`mid` puntúa 10, `junior` 9, `intern` 4.** Antes `intern` valía 10 — más que un mid. Con 25 años de trayectoria un internship no es mejor match, solo es más fácil de conseguir.
- **Los años pedidos se leen como el mínimo de todas las apariciones**, no la primera. "5 years in business... 2 years of experience" pedía 2, no 5.
- **`UBIC_BLOQUEO` se documenta como excepción consciente al principio de lista blanca**, en vez de dejarla contradiciéndolo en silencio. Solo aplica si la ubicación no matcheó antes contra la lista fuerte, y su agujero cae del lado barato.

**Problemas y causa raíz:**

- *Dos bitácoras versionadas: `BITACORA.md` (0 bytes) y `Bitácora.md` (5151).* El repo tiene `core.ignorecase = true` (Windows), así que localmente parecían una; en GitHub eran dos, y el vacío era el que referenciaban el README y el brief. Un reclutador que abriera BITACORA.md veía una página en blanco.
- *La bitácora nunca se había publicado.* El historial tenía **un solo commit**. Un segundo intento del 14 a las 22:45 **se abortó por mensaje vacío** — `COMMIT_EDITMSG` quedó intacto con `new file: "Bitácora.md"`. Un `git commit` sin `-m` abre el editor; salir sin escribir cancela el commit sin avisar.
- *`git rm --cached "Bitácora.md"` falló sin error visible.* PowerShell envía el pathspec en la codepage de la consola; git tenía el nombre guardado en UTF-8 (`Bit\303\241cora.md`). Los bytes no coincidían y, al pasar dos rutas en un solo comando, **falló el comando completo** — tampoco se removió la otra entrada. **El nombre no se podía escribir desde el teclado.** Solución: reconstruir el índice (`git rm -r --cached .` + `git add .`), que evita el problema por diseño en vez de pelearlo. **Regla adoptada: nombres de archivo en ASCII, sin tildes ni espacios, desde el primer commit.**
- *La deuda de listas duplicadas ya se había materializado.* Verificado punto por punto: `"ai"` contra `' ai'`, `"automatización"` contra `'automatizacion'`, `fintech` puntuando en n8n sin existir en `perfil.json`, y sobre todo una divergencia **estructural** — el nodo tenía tres listas de ubicación (fuerte / ambigua / bloqueo) donde `perfil.json` tenía una sola. El archivo que se autodescribía como "fuente de verdad" llevaba días siendo ficción.
- *La deuda documentada no era auditable.* El nodo de prefiltro no estaba en el repo, así que la divergencia era invisible desde el único lugar donde alguien la buscaría.

**Deuda asumida:**

- **Las listas siguen duplicadas.** Se sincronizaron y se documentó la duplicación dentro del propio `perfil.json`, pero n8n aún no lo lee. Se paga moviendo las listas a una hoja del Sheet. Sincronizar no es resolver: solo reinicia el reloj de la divergencia.
- **Los cambios de scoring están validados contra casos construidos, no contra los datos reales.** La simulación usó seis vacantes de prueba. Falta correr el flujo sobre las 249 y comparar la distribución antes/después.
- **El README no se actualizó en esta sesión.** Ahora describe correctamente los archivos (que ya existen), pero su nota de deuda técnica quedó desfasada y el principio de lista blanca necesita el matiz de `UBIC_BLOQUEO`.
- **La automatización sigue sin verificarse.** No se confirmó dónde corre n8n. Si es local, el cron de las 6am solo dispara con el PC encendido — y entonces "funcionando en producción" es una afirmación falsa en el README.

**Siguiente:**

1. Pegar los nodos `Prefiltro` y `Puntuar` corregidos en n8n (sin reimportar el flujo: se perderían las credenciales) y correr manualmente
2. Registrar los números reales: cuántas pasan el prefiltro y cuántas superan puntaje 5, contra el baseline de 71/249
3. Commit y push del repo saneado
4. Aplicar la fórmula de `candidatas` documentada en `docs/esquema.md`
5. Confirmar dónde corre n8n y si el cron dispara sin intervención
6. Actualizar el README con el estado real
7. Recién entonces: capa 2b con LLM, y publicación en LinkedIn
