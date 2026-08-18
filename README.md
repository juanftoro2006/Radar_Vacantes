# Radar de Vacantes

Sistema automatizado que detecta ofertas de empleo **en las primeras 24 horas de publicadas**, directamente desde los ATS de las empresas, y las puntúa contra un perfil profesional estructurado.

No es un buscador de empleo. Es un filtro: convierte cientos de vacantes diarias en una lista corta de las que realmente vale la pena leer.

---

## El problema

Buscar trabajo como desarrollador tiene tres fallas estructurales que ninguna plataforma resuelve:

**1. Las vacantes fantasma.** Entre el 18% y el 27% de los avisos publicados nunca se llenan. Se mantienen activos para alimentar pipelines de reclutamiento o por simple inercia administrativa. El costo promedio de postularse a una es de unas 9 horas entre investigación, adaptación del CV y espera.

**2. La ventana se cierra rápido.** Una vacante de ingeniería puede acumular cientos de postulaciones en días. Varios ATS presentan los candidatos al reclutador en orden de llegada, no por puntaje: postular tarde equivale a no postular.

**3. Los agregadores llegan tarde y sucios.** LinkedIn e Indeed replican avisos con retraso y mantienen visibles los que ya se cerraron. Para cuando la vacante aparece ahí, ya lleva días compitiendo.

## La solución

Los ATS más usados (Greenhouse, Lever, Ashby) exponen sus vacantes en **feeds JSON públicos, sin autenticación**. Es la misma fuente que alimenta la página de empleos de la empresa, disponible antes de que el aviso llegue a ningún agregador.

Este sistema consulta esos feeds a diario, detecta lo nuevo y lo evalúa.

```
Feeds JSON de ATS
        ↓
  Normalización        un esquema único para todos los proveedores
        ↓
  Deduplicación        doble clave: id técnico + huella de contenido
        ↓
  Prefiltro            lista blanca de títulos y ubicaciones
        ↓
  Scoring              stack, seniority, contexto de negocio
        ↓
  Vista candidatas     lista corta, ordenada, lista para leer
```

---

## Decisiones de diseño

Esta sección es el núcleo del proyecto. El código es reemplazable; las decisiones no.

### Filtro barato antes que filtro caro

De ~250 vacantes diarias, unas 180 se descartan con búsqueda de texto: costo cero, resultado determinista. Solo las que sobreviven pasan al scoring, y solo las mejores llegarían a un análisis con LLM.

Invertir el orden significaría pagar juicio caro para descubrir que un puesto de contabilidad no es un puesto de desarrollo.

### Lista blanca, nunca lista negra

El conjunto de títulos que sirven es corto y conocido (engineer, developer, automation, integration, data...). El conjunto de los que no sirven es infinito: payroll, legal, enfermería, ventas, diseño, reclutamiento...

**Se enumera el conjunto pequeño y conocido, nunca el infinito.** Una lista negra siempre tiene un agujero que no previste.

Lo mismo aplica a la ubicación: enumerar dónde eres elegible es corto; enumerar dónde no lo eres es todo el planeta.

### La lista blanca es generosa a propósito

Un falso positivo cuesta una evaluación adicional. Un falso negativo cuesta una oportunidad que nunca viste.

**Cuando el costo de equivocarse es asimétrico, el filtro se inclina hacia el error barato.**

### Knockout descarta, brecha no

Tres tipos de señal, tratados distinto:

| Señal | Ejemplo | Efecto |
|---|---|---|
| `KNOCKOUT` | Exige autorización laboral en otro país | Descarta |
| `BRECHA` | Piden 5 años, tienes 2 | Marca, no descarta |
| `RIESGO` | Exigen inglés avanzado | Marca, no descarta |

Un requisito de años es negociable con evidencia. Una jurisdicción legal no lo es. Mezclarlas en un solo puntaje destruye esa distinción — y produce el "27% de coincidencia" que no le sirve a nadie.

### Se guarda todo, se puntúa poco

Las vacantes descartadas por el prefiltro **también se registran**. Si no, el sistema volvería a detectarlas como nuevas al día siguiente, indefinidamente.

**El registro sirve a la deduplicación. El puntaje sirve a la decisión.** Son propósitos distintos y por eso todo se guarda pero solo una parte se evalúa.

### Celda vacía no es cero

Una vacante sin puntaje significa "no se evaluó". Un puntaje de cero significa "se evaluó y quedó descartada". Rellenar lo primero con lo segundo destruye información.

### Doble clave de deduplicación

- **Clave técnica:** `fuente:empresa:id` — identifica la vacante exacta en el ATS
- **Huella de contenido:** `empresa:titulo_normalizado` — sobrevive a la republicación

Cuando una empresa borra un aviso y lo vuelve a publicar, el ATS asigna un id nuevo. Sin la huella, el churn de republicaciones inundaría el sistema.

### Configuración fuera del código

Lo que varía **en valor** entre proveedores (la URL del feed) vive en la hoja de cálculo. Lo que varía **en estructura** (los nombres de los campos: `title` vs `text`, `absolute_url` vs `hostedUrl`) vive en el código, en un único mapa.

Agregar un ATS nuevo son tres cambios de una línea, sin refactor.

### Fallar fuerte vs. descartar suave

- Una vacante malformada se descarta y se registra en el log. El resto del lote es válido.
- Una desalineación estructural (más respuestas que empresas) **lanza excepción y detiene todo**. Si no se sabe a qué empresa pertenece cada vacante, ningún dato de esa corrida sirve.

Y todo lo que se descarta deja rastro: **ningún descarte silencioso.**

---

## Stack

| Componente | Tecnología |
|---|---|
| Orquestación | n8n (schedule + HTTP + Code) |
| Verificación de tokens | Python 3 + `requests` |
| Persistencia | Google Sheets |
| Fuentes | Greenhouse, Lever y Ashby Job Board APIs |

Google Sheets se eligió sobre Postgres deliberadamente: el volumen es de miles de filas, no hay concurrencia, y el flujo de trabajo requiere marcar filas a mano. Migrar es cambiar un nodo — el esquema es idéntico.

---

## Estructura

```
radar-vacantes/
├── README.md
├── BITACORA.md              registro de sesiones y decisiones
├── verificar_tokens.py      valida tokens de ATS y genera empresas.csv
├── perfil.ejemplo.json      plantilla del perfil (el real no se publica)
├── workflow.json            flujo de n8n exportado
├── requirements.txt
└── docs/
    └── esquema.md           estructura de las hojas
```

---

## Uso

**1. Cosechar tokens.** Buscar en Google con el operador `site:` sobre los dominios de ATS y copiar las URLs completas de las empresas de interés.

**2. Verificar.**

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python verificar_tokens.py
```

Genera `empresas.csv` con los tokens válidos y su plantilla de URL.

**3. Importar** `empresas.csv` a la hoja `empresas` del Sheet.

**4. Importar** `workflow.json` en n8n, conectar credenciales de Google Sheets y programar la ejecución diaria.

---

## Privacidad

`perfil.json` y `empresas.csv` **no se publican**. Contienen el perfil profesional real y la lista de empresas objetivo — estrategia personal, no contenido de repositorio. Se incluyen en `.gitignore` y se publica solo la plantilla de ejemplo.

---

## Estado

Funcionando en producción con ejecución diaria.

**Siguiente:** capa de análisis con LLM sobre las mejores candidatas, para comparar el requerimiento contra la evidencia del perfil y orientar la carta de presentación.

**Deuda técnica conocida:** las listas del prefiltro están embebidas en los nodos de n8n en lugar de leerse desde `perfil.json`. Hay dos copias de la misma verdad y van a divergir. Se resuelve moviendo el perfil a una hoja adicional del Sheet.
