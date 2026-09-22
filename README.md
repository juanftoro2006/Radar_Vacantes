# Radar de Vacantes

Sistema automatizado que detecta ofertas de empleo **en sus primeros días**, directamente desde los ATS de las empresas, las puntúa contra un perfil profesional y **avisa por Telegram** solo las que vale la pena leer.

No es un buscador de empleo. Es un filtro: convierte miles de vacantes en un par de avisos por semana.

---

## El problema

Buscar trabajo como desarrollador tiene tres fallas estructurales que ninguna plataforma resuelve:

**1. Las vacantes fantasma.** Entre el 18% y el 27% de los avisos publicados nunca se llenan. Se mantienen activos para alimentar pipelines de reclutamiento o por simple inercia administrativa.

**2. La ventana se cierra rápido.** Una vacante de ingeniería puede acumular cientos de postulaciones en días. Varios ATS presentan los candidatos al reclutador en orden de llegada, no por puntaje: postular tarde equivale a no postular.

**3. Los agregadores llegan tarde y sucios.** LinkedIn e Indeed replican avisos con retraso y mantienen visibles los que ya se cerraron.

## La solución

Los ATS más usados (Greenhouse, Lever, Ashby) exponen sus vacantes en **feeds JSON públicos, sin autenticación**. Es la misma fuente que alimenta la página de empleos de la empresa, disponible antes de que el aviso llegue a ningún agregador.

```
GitHub Actions (5 veces al día)
        ↓
  Feeds JSON de 28 empresas      Greenhouse · Lever · Ashby
        ↓
  Normalización                  un esquema único, texto completo
        ↓
  Deduplicación                  clave técnica + huella con ventana de 30 días
        ↓
  Prefiltro                      lista blanca de títulos y ubicaciones
        ↓
  Puntaje                        stack · seniority por tipo de rol · sector
        ↓
  Candidatas                     puntaje ≥ 5, sin knockout, publicadas hace ≤ 7 días
        ↓
  Telegram                       alerta inmediata + resumen diario con salud de fuentes
        ↓
  data/vacantes.csv              registro versionado en git
        ↓
  Dashboard (GitHub Pages)       inventario de lo abierto, con botón para aplicar
```

---

## Decisiones de diseño

Esta sección es el núcleo del proyecto. El código es reemplazable; las decisiones no.

### Filtro barato antes que filtro caro

El prefiltro y el puntaje son búsqueda de texto: costo cero, resultado determinista. Solo lo que sobrevive llegaría a un análisis con LLM. Invertir el orden sería pagar juicio caro para descubrir que un puesto de contabilidad no es un puesto de desarrollo.

**Corolario que costó un bug:** al filtro barato no se le recorta la entrada. La v1 cortaba las descripciones a 3500 caracteres "para ahorrar tokens del LLM", y el puntaje terminaba leyendo la presentación de la empresa en vez de los requisitos. Una vacante que pedía n8n, Python, OpenAI y Zapier sacaba 4.7 y nunca aparecía; con el texto completo, el mismo scoring le daba 7.3 (medido el 21-sep-2026 sobre el feed real). El recorte, si hace falta, es trabajo de la capa que paga tokens.

### Lista blanca, nunca lista negra

El conjunto de títulos que sirven es corto y conocido. El de los que no sirven es infinito. **Se enumera el conjunto pequeño y conocido, nunca el infinito.**

Lo mismo en ubicación, y aquí la v1 se traicionó a sí misma: bloqueaba una lista de países y dejaba pasar como "remoto" todo lo demás. `Sweden (Remote)`, `Remote, Singapore` y `San Francisco / Remote` pasaban. Hay 190 países; la lista negra siempre tiene un agujero. Ahora una ubicación pasa solo si nombra un lugar elegible (Colombia, LATAM…) o si es remota **sin nombrar ningún lugar** (`Remote`, `Remote, Global`, `Home based - Americas`).

### La lista blanca es generosa a propósito

Un falso positivo cuesta una lectura. Un falso negativo cuesta una oportunidad que nunca viste. **Cuando el costo de equivocarse es asimétrico, el filtro se inclina hacia el error barato.**

### Knockout descarta, brecha y riesgo marcan

| Señal | Ejemplo | Efecto |
|---|---|---|
| `KNOCKOUT` | Exige autorización laboral en EE. UU.; stack bajo el piso; staff/principal | Puntaje 0 |
| `BRECHA` | Piden 5 años; título senior en un rol de desarrollo | Marca, no descarta |
| `RIESGO` | Inglés avanzado; menciona híbrido | Marca, no descarta |

Un requisito de años es negociable con evidencia. Una jurisdicción legal no lo es. Mezclarlas en un solo puntaje destruye esa distinción.

### La seniority depende del tipo de rol

"Senior" no mide lo mismo en todos los puestos. En desarrollo puro mide años escribiendo código en producción. En automatización e integraciones mide entender el proceso del negocio, y ahí 25 años de operación cuentan.

| Título | Desarrollo | Automatización / operaciones |
|---|---|---|
| junior | 9 | 8 |
| sin marca | 6 | 10 |
| mid / II | 10 | 10 |
| senior | 3 + BRECHA | 8 |
| lead / manager / architect | KNOCKOUT | 4 + BRECHA |
| staff / principal / director | KNOCKOUT | KNOCKOUT |

### Piso de stack

La ponderación `stack 0.5 · seniority 0.3 · contexto 0.2` permitía pasar el umbral con encaje técnico casi nulo si el título decía "Junior" y la empresa era fintech. Ninguna de esas dos dimensiones mide si sabes hacer el trabajo. Si el stack no llega a 2.0, es knockout con bandera visible.

### Se guarda todo, se avisa poco

Todo lo que se descarga queda en `data/vacantes.csv`, pase o no el filtro, con el motivo. **El registro sirve a la deduplicación y a la auditoría. El aviso sirve a la decisión.**

### Celda vacía no es cero

Una vacante sin puntaje significa "no se evaluó". Un puntaje de cero significa "se evaluó y quedó descartada".

### Doble clave de deduplicación, con memoria limitada

- **Clave técnica:** `fuente:token:id`. Identifica la vacante exacta.
- **Huella:** `token:título_normalizado`. Si la misma empresa ya avisó el mismo título en los últimos 30 días, la nueva queda `duplicada`: registrada, no avisada. Pasa cuando una vacante se publica en tres ciudades o se republica con otro id.

La v1 aplicaba la huella para siempre: si Clara reabría un "Backend Engineer" tres meses después, se descartaba sin dejar fila. Ahora la huella caduca y todo descarte queda registrado.

### Ventana de 7 días, no de 48 horas

La ventaja del radar es llegar antes que la cola, pero una ventana de 48h medida sobre la fecha de publicación convierte cualquier corrida tardía en una pérdida permanente. Con 7 días y alertas inmediatas, lo fresco llega fresco y lo que se descubre tarde todavía aparece, con su antigüedad a la vista.

### Configuración fuera del código

Lo que varía **en valor** vive en `config/`: qué empresas se consultan (`empresas.csv`) y qué cuenta como encaje (`radar.json`, única fuente de verdad de listas, pesos y umbrales). Lo que varía **en estructura** (nombres de campos de cada ATS) vive en `radar/fuentes.py`, en un único mapa.

### Telegram para lo urgente, dashboard para el inventario

Telegram avisa solo lo publicado hace 7 días o menos: la alerta sirve para llegar antes que la cola. El dashboard muestra todo lo que sigue abierto con puntaje ≥ 5, sin importar la antigüedad, con un botón **Aplicar** que abre la vacante en el ATS. Sin él, una vacante excelente descubierta tarde desaparecía: la primera corrida real encontró la mejor de todas (puntaje 9.4) con 24 días de publicada.

"Postulé" se guarda en el `localStorage` del navegador y no en el repo: el registro es público, y a qué empresas se postula uno no lo es.

Títulos, ubicaciones y URLs vienen de feeds de terceros, así que son entrada no confiable: el JSON se incrusta escapado (un título con `</script>` no cierra la etiqueta), el texto se pinta con `textContent` y solo se aceptan enlaces `http(s)`.

### Ningún descarte silencioso, ninguna caída silenciosa

- Una vacante malformada se omite y queda en el log.
- Una fuente que responde 404 no tumba la corrida: aparece en el resumen diario de Telegram con la fecha desde la que está caída.
- **Señal de vida:** el resumen llega todos los días, aunque no haya candidatas. Si un día no llega, el radar está caído. La v1 dejó de correr cuando se perdió el acceso a Railway, y el único síntoma fue dejar de ver vacantes.

---

## Stack

| Componente | Tecnología | Por qué |
|---|---|---|
| Ejecución | GitHub Actions (cron) | Gratis en repo público, sin servidor que pagar ni mantener |
| Pipeline | Python 3.12 + `requests` + `pydantic` | Validación temprana: un campo mal escrito falla al cargar, no en silencio |
| Registro | CSV versionado en git | Miles de filas, un solo escritor; el historial del repo es la auditoría |
| Avisos | Telegram Bot API | Llega al celular; los comandos se leen con `getUpdates`, sin webhook |
| Dashboard | HTML estático generado por el bot + GitHub Pages | Se regenera en cada corrida; sin servidor ni base de datos |
| Pruebas | `pytest` + fixtures con la forma real de cada API | Se prueba sin red y sin depender del día |

La v1 (n8n + Google Sheets) está en `legacy/n8n/` como referencia.

---

## Estructura

```
├── radar/
│   ├── __main__.py       punto de entrada: python -m radar
│   ├── pipeline.py       orquestación de una corrida
│   ├── fuentes.py        descarga y normalización por ATS
│   ├── prefiltro.py      título + ubicación
│   ├── puntuar.py        stack, seniority, contexto, banderas
│   ├── registro.py       CSV y estado
│   ├── telegram.py       alertas, resumen y comandos
│   ├── dashboard.py      genera site/index.html desde el registro
│   ├── config.py         carga y validación de config/
│   ├── modelos.py        modelos pydantic
│   └── texto.py          normalización y matching
├── config/
│   ├── radar.json        listas, pesos y umbrales (única fuente de verdad)
│   ├── empresas.csv      fuentes a consultar
│   └── urls_candidatas.txt  entrada de verificar_tokens.py
├── data/                 lo escribe el bot
├── tests/
├── verificar_tokens.py   valida tokens nuevos y los agrega a empresas.csv
├── legacy/n8n/           la v1
└── .github/workflows/    radar.yml (cron) y pruebas.yml (CI)
```

---

## Uso

**Correr local sin red** (pruebas y demo):

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
python -m radar --seco --no-guardar --fixtures tests/fixtures
```

**Dashboard local:** `python -m radar.dashboard` genera `site/index.html`; se abre con doble clic.

**Agregar empresas:** pegar URLs en `config/urls_candidatas.txt` → `python verificar_tokens.py` → revisar `git diff config/empresas.csv` → commit.

**Comandos en Telegram** (se aplican en la siguiente corrida):

- `/visto 12 15`: marca candidatas como revisadas y las saca del resumen
- `/pendientes`: pide el resumen en la siguiente corrida

**Configurar en GitHub:** Settings → Secrets and variables → Actions → `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`. Sin ellos corre en modo seco con una advertencia.

---

## Privacidad

`perfil.json` (perfil completo, evidencia, textos de postulación) no se publica. El registro `data/vacantes.csv` sí es público: contiene vacantes públicas, sus puntajes y si se marcaron como vistas. Por eso no existe un comando `/postule`: a qué empresas se postula uno no va en un repo público.

---

## Estado

**v2 en migración (sep-2026):** pipeline en Python y pruebas listos. La ejecución automática empieza con la primera corrida verificada en GitHub Actions; hasta entonces este README no dice "en producción".

**Siguiente:** capa de análisis con LLM sobre las candidatas avisadas, con la descripción delimitada como dato y no como instrucción (una oferta es entrada no confiable: prompt injection). Adaptadores para SmartRecruiters y Workday, donde publican varias empresas colombianas que no usan los tres ATS actuales.
