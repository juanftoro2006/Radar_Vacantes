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

## 2026-08-18 (tarde) — Recuperación del flujo, migración del repo y primera medición

**Objetivo:** aplicar en n8n el prefiltro y el scoring corregidos en la mañana, y correr para medir contra el baseline de 71 de 249.

\---

**Construido:**

* Flujo de n8n restaurado y funcionando de punta a punta (10 nodos, 18s, sin errores)
* Repo movido a `C:\\PROYECTOS\\AUTOMATIZACIONES\\NoA-radar\_vacantes`
* Fórmula de la vista `candidatas` corregida
* `Puntuar` corregido pegado en el flujo real (sin ejecutar todavía)

\---

**Problemas y causa raíz:**

* *El workflow de n8n se perdió.* Se eliminó el flujo que funcionaba y se importó `workflow.json` — el export público, sin ID de Sheet ni credenciales. Causa raíz: no se releyó el pendiente 1 del propio `ESTADO.md`, que advertía explícitamente contra reimportar. **Documentación que no se relee no sirve de nada.** Recuperado gracias a `Radar de Vacantes.json` (export con credenciales, bloqueado por `.gitignore`) — la separación entre export publicable y export ejecutable, tomada esa misma mañana, fue lo que hizo que costara minutos y no una tarde.
* *La credencial de Google Sheets ya no existía.* Se reasignó a mano en los tres nodos Sheets. `documentId` sí viajaba en el export.
* *El repo vivía en Google Drive (`G:\\Mi unidad\\`).* `.git` son miles de archivos pequeños sincronizados constantemente sobre un drive virtual: índice lento, locks en conflicto, riesgo de corrupción silenciosa por stubs no materializados. Se copió (no se movió) a `C:` con `robocopy /E`, se verificó `git status` / `log` / `remote` en el destino, y solo después se retiró el original. **Destruir el estado bueno es siempre el último paso, nunca parte del mismo paso que crea el nuevo.**
* *La fórmula de `candidatas` devolvía vacío.* No eran las letras de columna — `K`=prefiltro, `M`=puntaje, `O`=banderas estaban bien. Causa raíz: `FILTER` con rangos de altura distinta (`A:O` completo contra condiciones de columna completa) no alinea y falla en silencio. Se acotaron los rangos a `A2:O` y se corrigió el `SORT` de la columna 14 (`desglose`) a la 13 (`puntaje`). Diagnosticado con tres `CONTAR.SI` — una condición a la vez, no cambiando la fórmula al azar. Sondas: 75 con `prefiltro="si"`, 24 con `puntaje>=5`, 270 filas.
* *No se pudo medir el scoring nuevo.* Ver abajo.

\---

**Decisiones:**

* **La descripción no se persiste en el Sheet.** El `Puntuar` la tiene viva en memoria cuando corre — el pipeline nunca tuvo el problema. Para la capa 2b se releerá el feed desde la `url` guardada, en vez de almacenar 3500 caracteres por fila. La decisión original de no guardarla sigue siendo correcta; lo que cambió fue el requisito, no el criterio.
* **La medición del `Puntuar` se hará en producción, no en un banco de pruebas.** Medir sin descripción daría un número falso — peor que no medir. Se pegó el código corregido y se comparará contra los puntajes ya guardados en la próxima corrida real.
* **Sin cron todavía.** Un flujo que no se ha visto correr limpio varias veces no se automatiza; automatizar un flujo con bugs solo hace que los bugs corran solos.
* **`verificar\_tokens.py` y n8n no se integran.** Son dos herramientas separadas a propósito: Python se corre a mano cuando se agregan empresas, su salida se pega en la hoja `empresa`, y n8n lee de ahí. El punto de contacto es la hoja, y lo cruza el humano.

\---

**Resultados:**

* Flujo completo: 4 empresas → 247 normalizadas → 8 nuevas (dedup correcta) → 3 pasan el prefiltro → 8 guardadas
* **Prefiltro corregido medido: 71 de 264 pasan.** Las correcciones (límite de palabra `\\b`, siglas de bloqueo) no tumbaron candidatas. Que el entero coincida con el baseline de 71/249 es casualidad, no confirmación: 28,5% antes, 26,9% ahora.
* Medido con un workflow desechable `TEMP - medir scoring` (leer hoja → prefiltro → contar), ya borrado. **Principio: la lógica sin efectos secundarios se puede probar; la que escribe en algún lado, no.** Aplicarlo desde el diseño en la capa 2b.
* Confirmado: **n8n corre en Railway**, no local. El cron sí dispararía con el PC apagado — el README no miente en eso.

\---

**Deuda asumida:**

* **`a0bd19a` ("corregir scoring") ya está en `origin/main` sin haberse medido nunca contra datos reales.** Push antes de validar. Es la misma falla que originó la auditoría de la mañana —lo publicado no es lo verificado— con dos días de vida. El pendiente 3 de `ESTADO.md` no está hecho: está saltado.
* El trigger se llama `Cada dia 6am` pero está configurado como `interval: \[{ field: "hours" }]` — corre **cada hora**. Nombre mintiendo, igual que el README.
* La hoja `vacantes` puede no tener fila de encabezados. Si es así, el `Map Automatically` de n8n no tiene contra qué mapear y las 270 filas podrían estar desalineadas. **Sin verificar.**
* Las 3 vacantes nuevas del 18 que pasaron el prefiltro se puntuaron con el código viejo. Sin revisar por qué ninguna llegó a `candidatas`.
* `docs/Hoja\_de\_ruta\_para\_negocios.png` y `docs/Nuevo\_Ecosistema\_Digital\_de\_Ventas.png` sin trackear y sin relación aparente con el radar. Decidir si se quedan antes del próximo `git add -A`.
* Commits `5d75da5` y `ff954f9` son el mismo, duplicado con y sin tildes. Cicatriz del enredo de bitácoras del 14. En historial público, no se toca.
* Las listas del prefiltro siguen duplicadas entre `perfil.json` y los nodos.

\---

**Riesgo de diseño detectado para la capa 2b:**

Las descripciones vienen de feeds públicos de ATS — **entrada no confiable**. Una oferta real de hoy incluía la frase "experience working with Claude ... is required" dentro del texto; inofensiva, pero muestra la forma exacta que tendría una inyección de prompt. Cuando la capa 2b mande esos 3500 caracteres a un LLM, el prompt debe delimitar explícitamente la descripción como **dato, no como instrucción**. Se piensa antes de escribir la capa, no después.

\---

**Siguiente:**

1. Verificar si `vacantes` tiene fila de encabezados
2. Correr el flujo real con el `Puntuar` corregido y comparar contra los puntajes guardados
3. Revisar las 3 del 18: ¿puntaje bajo o KNOCKOUT?
4. Arreglar el trigger (cada hora → 6am) y actualizar el README
5. Después: capa 2b


## 2026-08-19 (tarde) — Cuatro bugs de scoring, ventana de 48h y 10 fuentes

**Objetivo:** entender por qué el radar traía sábana y nada útil, y depurar hasta tener una lista corta que sirva.

---

**Construido:**

- **`verificar_tokens.py`**: se probaron 29 tokens candidatos. Sobrevivieron 6 nuevos → **10 fuentes** (antes 4): `remotecom` (215), `clara` (103), `bitso` (9), `nubank` (0, board válido sin ofertas hoy), `mural` (ashby, 10), `runa` (ashby, 2). Primeras fuentes no-Greenhouse del proyecto. De ~250 a **628 vacantes**.
- **Nodo `Puntuar`** — cuatro correcciones y un piso nuevo.
- **Vista `candidatas`** — reescrita con ventana de frescura.
- **Hoja `vacantes`** — columna `R` (`antiguedad_dias`) creada como encabezado, **deliberadamente sin usar**.

---

**Los cuatro bugs del scoring, todos encontrados leyendo datos reales:**

1. **Cadena `else if` en orden invertido.** `"Sr. Software Engineer II"` matcheaba la rama de `ii` antes que la de `senior` y salía con `seniority 10` — el puntaje de un mid. La rama `sr.` nunca se evaluaba. Dos líneas mal ordenadas premiando exactamente lo contrario de lo que debían.
2. **Plurales invisibles.** `\bintegration\b` no matchea `"integrations"`: la `s` es carácter de palabra y mata el límite. Lo mismo con `apis`, `webhooks`. Las ofertas escriben casi todo en plural — se perdía la mayoría de los matches de stack. Corregido con `\b{término}s?\b`.
3. **Vocabulario propio en vez de vocabulario de mercado.** Las listas estaban escritas con los términos con que uno se describe, no con los que escriben las ofertas: `fintech` (nadie lo escribe; escriben *trading*, *brokerage*, *payments*), `javascript` (escriben *Node.js*), `trade` (no matchea *trading*). `node.js` no existía en ninguna lista.
4. **`seniority` medía prestigio del puesto, no distancia.** Un `senior` daba 4 sobre 10 en vez de 0. Toda vacante con título alto flotaba hacia arriba.

**Evidencia acumulada del bug 1 + 3:** NinjaTrader `Sr. Software Engineer II, Platform/API` — un broker de futuros, con Node/TypeScript, colas y event-driven — salía con `stack 1.0 | seniority 10 | contexto 0`. Los tres números mentían a la vez.

---

**El quinto hallazgo, y el más importante — piso de stack:**

Clara `Junior Data Scientist` sacó **5.1 con `stack 1.6`**. Pasó el umbral por `seniority 9` (dice "Junior") y `contexto 8` (es fintech). Pedía Scikit-learn, TensorFlow, AWS, Databricks — nada del perfil.

La ponderación `stack 0.5 / seniority 0.3 / contexto 0.2` permite pasar con encaje técnico casi nulo si las otras dos dimensiones van llenas. **Ninguna de esas dos mide si sabes hacer el trabajo.**

Se agregó `PISO_STACK = 2.0`: si el stack no llega, el puntaje se corta a 0 sin importar lo demás.

---

**Decisiones:**

- **Ventana de 48 horas, dura.** Razón del negocio, no técnica: *una vacante de 3 días con 100 aplicaciones ya no es una oportunidad, es una estadística*. La ventaja del radar es llegar al ATS antes que los agregadores. Si no hay nada fresco, no hay nada — mejor vacío que basura.
- **`antiguedad_dias` se calcula al vuelo en la fórmula, no se almacena.** Un valor guardado se congela: una vacante de hoy diría `0` para siempre. `publicada` ya está guardada; con eso basta.
- **`candidatas` ordena por `publicada` (col. 17), no por puntaje.** Dentro de una ventana de 48h todas están frescas: lo que decide es cuál llegó primero, donde aún no hay cola.
- **Piso arranca en 2.0, no en 3.0.** No hay datos para justificar 3.0. Se aprieta con evidencia — el error que se cometió con `a0bd19a`.
- **El piso deja bandera, no descarta callado.** `KNOCKOUT: stack 1.8 bajo el piso de 2.0` permite ver qué tan cerca quedó y recalibrar. Principio: ningún descarte silencioso.
- **LinkedIn e Indeed descartados como fuentes.** No tienen feed público; sus APIs son solo para partners. El conector de Indeed sirve para búsqueda manual, no para un cron.

---

**Fórmula final de `candidatas`:**

```
=IFNA(SORT(FILTER(vacantes!A2:Q, vacantes!K2:K="si", vacantes!M2:M>=5,
  NOT(REGEXMATCH(vacantes!O2:O&"", "KNOCKOUT")), vacantes!Q2:Q<>"",
  (NOW()-DATEVALUE(LEFT(vacantes!Q2:Q&"          ",10)))<=2), 17, FALSE),
  "Sin candidatas en las últimas 48 horas")
```

`LEFT(...,10)` corta el ISO a fecha; `DATEVALUE` lo convierte. El relleno de espacios protege las celdas vacías: `DATEVALUE("")` revienta la fórmula entera.

---

**Resultado medido:**

**Cero candidatas de 628.** No es falla: 620 son histórico descargado hoy de golpe al agregar 6 boards completos. Diagnóstico por partes: 359 filas con `publicada`, 25 con puntaje ≥5, y **solo 1 con ambas** — Clara, publicada el 22 de mayo. Rechazada correctamente por la ventana.

Sin `publicada`, esa vacante de mayo habría entrado hoy como "nueva". **El trabajo del 19 en la mañana evitó una postulación a una oferta de hace tres meses.**

---

**Deuda viva:**

- **Las 628 guardadas conservan puntaje viejo.** El dedup las salta, no se repuntúan. La medición real del scoring corregido empieza con el flujo entrante de mañana. **El scoring sigue sin medirse contra un lote grande.**
- **Mapeos de `publicada` de Lever y Ashby: aún sin verificar.** Mural y Runa entraron hoy; falta confirmar que traen fecha. Si vienen `null`, el filtro `Q<>""` las mata enteras y no se notaría.
- **Columna `R` creada y vacía.** Decidir si se borra.
- **Trigger** sigue en `field: "hours"` (cada hora) con nombre `Cada dia 6am`. Uso previsto: manual, 2 veces al día.
- **Tokens 404 no significan que la empresa no use Greenhouse** — significa que el token no es ese. Rappi, Platzi, Kavak, Mercadolibre y los 6 de Lever casi seguro tienen board con otro slug. Se cosechan entrando al sitio de carreras y copiando la URL. Duplicaría el alcance.
- **Las listas del prefiltro siguen duplicadas** entre `perfil.json` y los nodos. Hoy se editó solo el nodo: **`perfil.json` quedó desincronizado** (le faltan `node.js`, los sectores nuevos, el piso). Deuda que creció hoy.
- `verificar_tokens.py` tiene los tokens dentro del código (`URLS_CANDIDATAS`, línea 15). Al menos está aislada y documentada.
- Capa 2b sin empezar. Riesgo de inyección de prompt ya identificado.

---

**Aprendizajes:**

- **Una consola que muestra mal no es evidencia de un archivo dañado.** `Get-Content` en PowerShell 5.1 decodifica en ANSI si no hay BOM: mostró `â€"` sobre un UTF-8 intacto. Casi se "repara" un archivo sano.
- **Un número de fila no es un identificador.** Se persiguió la "fila fantasma 272" de la sesión anterior y hoy la 272 era otra vacante distinta. Se busca por condición (`COUNTIFS`), no por posición.
- **`#N/A` en un `FILTER` no es error de sintaxis** — es "ninguna fila cumple". `#VALUE!` sería la fórmula; `#REF!` el rango. El error dice dónde mirar.
- **Un `FILTER` con 5 condiciones que da vacío no dice cuál falló.** Se aislaron con `COUNTA`, `COUNTIF`, `MAX` y `COUNTIFS` hasta encontrar el número exacto.
- **Las listas de matching no son autodescripción, son vocabulario de mercado.** La pregunta correcta no es "¿qué sé hacer?" sino "¿cómo lo nombran los que publican?".

---

**Siguiente:**

1. Correr manual mañana y medir con flujo entrante real — primera medición honesta del scoring corregido
2. Verificar que Mural y Runa traen `publicada` (test real de Ashby)
3. Cosechar los tokens reales de los 404 (Rappi, Platzi, Kavak, Mercadolibre, Nowports, Belvo)
4. Sincronizar `perfil.json` con los nodos, o pagar la deuda moviendo las listas a una hoja del Sheet
5. Actualizar `ESTADO.md`, que sigue dos sesiones atrasado
6. Después: capa 2b

**Si en 3 días sigue en cero, el problema no es el código: son las fuentes.** El arreglo sería llegar a 50-100 empresas, no volver a tocar el scoring.
---

## 2026-09-21 — v2: de n8n en Railway a Python en GitHub Actions

**Objetivo:** entender por qué el radar dejó de mostrar vacantes y dejarlo funcionando solo, sin servidor que pagar.

**Diagnóstico** (medido sobre los 10 feeds reales, con el código del 19 de agosto):

- **Causa cero: el radar no corría.** Se perdió el acceso a Railway. Nada avisó: el único síntoma fue no ver vacantes.
- **El recorte a 3500 caracteres rompía el puntaje.** 65 de las 70 vacantes que pasaban el prefiltro llegaban cortadas; el puntaje leía la presentación de la empresa, no los requisitos. Clara *AI Growth Automation Engineer* (pide n8n, Python, OpenAI, Anthropic, Zapier) sacaba 4.7 → invisible. Con texto completo: 7.3. En todo el corpus, las vacantes ≥5 pasaban de 6 a 23.
- **Ventana de 48h sobre `publicada` + dedup = pérdida permanente.** Lo que se descubría tarde se guardaba, el dedup no lo reevaluaba y la vista nunca lo mostraba. Últimas 48h: 5 publicadas en las 10 fuentes, 0 pasaban el prefiltro.
- **Fuentes insuficientes.** Bitso 404 (perdida en silencio), Nubank 0 (se mudó a Ashby), Runa era otra empresa (Londres).
- **"Senior" era knockout disfrazado.** 36 de 70 eran senior con seniority 0: necesitaban stack 10 para llegar a 5; el máximo observado fue 5.4.
- **La lista negra de ubicación tenía agujeros.** `Sweden (Remote)`, `Remote, Singapore`, `San Francisco / Remote` pasaban como "remoto sin país".
- **Huella permanente.** 281 de 594 vacantes repetían título dentro de su empresa; una reapertura se descartaba sin dejar fila.
- **Otra vez, lo publicado no era lo que corría.** Último commit del 19 de agosto; el flujo de septiembre solo existía dentro de n8n.

**Construido:**

- Paquete `radar/` en Python: `fuentes`, `prefiltro`, `puntuar`, `pipeline`, `registro`, `telegram`, `config`, `modelos` (pydantic), `texto`
- `config/radar.json`: **única** fuente de verdad de listas, pesos y umbrales. Se paga la deuda de listas duplicadas: el código lee este archivo y no hay otra copia
- `config/empresas.csv`: 28 fuentes activas (antes 10), verificadas una por una contra los feeds reales el 21-sep
- `.github/workflows/radar.yml`: cron 4 veces al día (06:17, 11:17, 15:17, 19:17 Bogotá), botón manual, commit de `data/` solo si cambia
- `.github/workflows/pruebas.yml`: CI con 71 pruebas + corrida completa sin red en cada push
- Telegram: alerta inmediata por candidata, resumen diario con salud de fuentes, comandos `/visto N` y `/pendientes`
- `verificar_tokens.py` v3: lee `config/urls_candidatas.txt` y agrega a `config/empresas.csv` sin pisar
- n8n movido a `legacy/n8n/`

**Decisiones:**

- **GitHub Actions sobre n8n Cloud o Railway.** Gratis en repo público, sin servidor, y el código que corre es exactamente el del repo. Descartado: n8n en cuenta temporal (vence y vuelve a pasar lo de Railway).
- **Registro en CSV versionado, no en Google Sheets.** Un solo escritor, miles de filas, y el historial de git es la auditoría. Sheets exigía cuenta de servicio y la vista `candidatas` se rompió dos veces por letras de columna.
- **csv de la stdlib, no pandas, para el registro.** Solo se leen y escriben filas; pandas agrega ~30 MB y convierte tipos solo. Para analizar, `pandas.read_csv(..., dtype=str)`.
- **Texto completo para puntuar.** El tope de contexto es problema de la capa que paga tokens, no del filtro gratis.
- **Ubicación con lista blanca real.** Pasa solo lo que nombra un lugar elegible o lo que es remoto sin nombrar ningún lugar. Se elimina la excepción de lista negra de `UBIC_BLOQUEO`.
- **Seniority por tipo de rol.** Desarrollo: senior 3 + BRECHA, lead knockout. Automatización/operaciones: senior 8, lead 4 + BRECHA. Staff/principal/director: knockout en ambas. Razón: "senior" en desarrollo mide años de código; en automatización mide entender el negocio, y ahí los 25 años cuentan.
- **Ventana de 7 días** (antes 48h) y **huella de 30 días** (antes permanente). Todo descarte por huella queda como `duplicada`, con referencia a la vacante original.
- **Autorización laboral:** knockout solo si es en OTRO país. "Authorized to work in Colombia" ya no descarta.
- **Híbrido en Medellín no marca.** Híbrido en otra ciudad sigue siendo RIESGO (o KNOCKOUT si es explícito).
- **Sin comando `/postule`.** El registro es público; a qué empresa se postula uno no va en un repo público.
- **Sin conteo doble:** los términos largos se evalúan primero y se retiran (`rest api` ya no cuenta además como `api`).
- **Lever lee `lists`.** Ahí pone los requisitos; antes solo se leía `descriptionPlain`.
- **Señal de vida:** el resumen llega todos los días aunque no haya nada. Si no llega, el radar está caído.

**Problemas y causa raíz:**

- *Síntoma: "no volví a ver vacantes".* Causa: cinco fallas que se sumaban (no corría + recorte + ventana + fuentes + seniority). Ninguna sola explicaba el cero; juntas lo garantizaban. Lección: antes de tocar el scoring, medir el embudo completo sobre datos reales, etapa por etapa.
- *La red del entorno de desarrollo bloquea los ATS.* Las pruebas usan fixtures sintéticos con la forma real de cada API (campos verificados contra los feeds). La primera corrida con red es la de Actions.

**Deuda asumida:**

- **El scoring nuevo no se ha corrido sobre el corpus real en Python.** Se validó en JavaScript contra los feeds y en Python contra fixtures. La primera corrida de Actions es la medición real: revisar cuántas candidatas salen.
- **Términos agregados al stack sin confirmar:** `agent`, `rag`, `whatsapp`. Salen de proyectos propios (multi-agente, RAG en n8n, WhatsApp Business API). Confirmar o quitar en `config/radar.json`.
- **`perfil.json` privado conserva las secciones `prefiltro`/`scoring`/`knockout` viejas.** Ya no las lee nadie. Borrarlas a mano (no se tocaron para no perder nada irrecuperable).
- **Empresas colombianas grandes fuera de alcance** (Rappi, Mercado Libre, Platzi, Kavak, Truora, Habi...): no usan Greenhouse/Lever/Ashby. Siguiente adaptador: SmartRecruiters (API pública).
- **GitHub desactiva crons tras 60 días sin actividad en el repo.** Los commits diarios del bot deberían contar como actividad; si un día no llega el resumen, revisar primero eso.

**Siguiente:**

1. Copiar `radar.yml` y `pruebas.yml` a `.github/workflows/` (la herramienta no puede escribir en esa carpeta), crear el bot, cargar los dos secrets, push, y correr el workflow a mano en modo seco
2. Correr en modo normal y medir: candidatas de la primera corrida vs. lo esperado (~1-2 por semana)
3. Confirmar o quitar `agent`, `rag`, `whatsapp` del stack
4. Limpiar `perfil.json` privado
5. Después: capa 2b con LLM (descripción delimitada como dato, no instrucción)

---

## 2026-09-21 (noche) — Primera corrida real y dashboard

**Primera medición real** (modo seco, 28 fuentes): 28/28 OK · 1.946 vacantes · 279 pasan prefiltro · 44 con puntaje ≥5 sin knockout. En la ventana de 7 días: 10 pasan prefiltro, **0 llegan a 5**. En 30 días: 8.

- El puntaje ordena bien: la #1 del corpus es Clara *AI Growth Automation Engineer* (9.4), la misma que la v1 enterraba con 4.7.
- El cero de la semana es del mercado, no del código. Esperable: 1–2 alertas por semana, con semanas en cero.

**Hallazgo:** lo bueno del último mes quedaba fuera de la ventana de 7 días y el radar nunca lo iba a mostrar. Las mejores 6 se entregaron a mano en el chat.

**Construido:**

- `radar/dashboard.py`: genera `site/index.html` desde el registro. Muestra todo lo abierto con puntaje ≥5 (cualquier antigüedad), una tarjeta por huella, botón **Aplicar** y botón **Postulé**
- `radar.yml`: genera el dashboard en cada corrida y lo publica con GitHub Pages (job `pagina`)
- Acciones actualizadas a versiones con Node 24 (`checkout@v7`, `setup-python@v7`); las v4/v5 usaban Node 20
- Banderas con tildes ("años", "inglés", "híbrido"); el dashboard corrige las filas viejas al mostrarlas

**Decisiones:**

- **Telegram para lo urgente (≤7 días), dashboard para el inventario (todo lo abierto).** Resuelve el hallazgo sin agrandar la ventana de alertas.
- **GitHub Pages, no una página privada.** Se regenera sola 4 veces al día; el registro ya era público.
- **"Postulé" en localStorage, no en el repo.** Privado; no se sincroniza entre dispositivos (asumido).
- **El HTML no se versiona** (`site/` en `.gitignore`): es un derivado de `data/`.
- **Seguridad:** títulos y URLs son de terceros. JSON escapado dentro de `<script>`, texto con `textContent`, solo enlaces http(s). Cubierto por pruebas.

**Deuda:**

- Falsos positivos observados: *Sales Development Representative (AI & Automation)* 7.4 y *Growth Designer (AI Focused)* 6.0 pasan por "AI" en el título. Medir dos semanas antes de tocar.
- Decisión pendiente de Juan: ¿*Solutions Engineer* / *Sales Engineer* (preventa técnica) son objetivo?
- Quitar `_TEXTO_LEGADO` de `dashboard.py` cuando no queden vacantes abiertas anteriores al 21-sep.

**Incidente, misma noche:** la corrida programada de las 00:17 UTC (19:17 Bogotá) **nunca ocurrió**. Verificado en la página pública de Actions a las 02:35 UTC: solo existía la corrida manual. La configuración estaba bien (cron válido, archivo en `main`, Actions habilitado). Causa: GitHub no garantiza el cron. Con carga alta lo retrasa y a veces lo descarta, y las 00:00 UTC son la hora más congestionada del día.

- **Decisión:** 5 turnos en vez de 4, ninguno cerca de las 00:00 UTC (06:17, 09:17, 12:17, 15:17, 18:17 Bogotá). El diseño ya tolera un turno perdido: el dedup por clave y la ventana de 7 días hacen que perder una corrida solo retrase el aviso, no lo pierda.
- **Lección:** un cron gratuito es "a lo mejor", no "a la hora". Si algún día la hora exacta importa, el disparo va por fuera (cron-job.org llamando a `workflow_dispatch`), con su propia credencial.

**Cierre del día:** GitHub Pages activado (Source: GitHub Actions). Corrida #2: `radar` OK, `pagina` falló porque Pages no estaba activado; se volvió a correr solo el job fallido y el dashboard quedó publicado en `juanftoro2006.github.io/Radar_Vacantes`. Telegram confirmado. Mañana 06:17 es la primera corrida automática con el horario nuevo.
