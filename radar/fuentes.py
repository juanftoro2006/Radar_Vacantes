"""Descarga y normalizacion de los feeds publicos de los ATS.

Toda la diferencia ESTRUCTURAL entre proveedores (URL, nombres de campos)
vive en este archivo y solo aqui. Lo que varia en VALOR (que empresas se
consultan) vive en config/empresas.csv.

Agregar un ATS nuevo = una URL en URLS + una funcion en NORMALIZADORES.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .modelos import Empresa, ReporteFuente, Vacante
from .texto import limpiar_html

log = logging.getLogger(__name__)

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}?includeCompensation=false",
}

AGENTE = "RadarVacantes/2.0 (+https://github.com/juanftoro2006/Radar_Vacantes)"


def _sesion() -> requests.Session:
    """Sesion con reintentos: un 502 pasajero no debe tumbar una fuente."""
    reintentos = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=reintentos))
    s.headers["User-Agent"] = AGENTE
    return s


# --- Normalizadores: JSON crudo de cada ATS -> Vacante --------------------

def _unir(*partes: str | None) -> str:
    """Une ubicaciones sin repetir ni dejar vacios, separadas por ' / '."""
    vistas: list[str] = []
    for p in partes:
        p = (p or "").strip()
        if p and p not in vistas:
            vistas.append(p)
    return " / ".join(vistas) or "sin especificar"


def _greenhouse(v: dict[str, Any], e: Empresa) -> Vacante:
    return Vacante(
        fuente="greenhouse", token=e.token, empresa=e.empresa,
        id_externo=str(v["id"]),
        titulo=(v.get("title") or "").strip(),
        ubicacion=_unir((v.get("location") or {}).get("name")),
        url=v.get("absolute_url") or "",
        publicada=v.get("first_published") or None,
        descripcion=limpiar_html(v.get("content")),
    )


def _lever(v: dict[str, Any], e: Empresa) -> Vacante:
    cat = v.get("categories") or {}
    # Lever pone los requisitos en 'lists', no en descriptionPlain.
    # Leer solo descriptionPlain era puntuar sin los requisitos.
    listas = " ".join(
        f"{l.get('text', '')} {limpiar_html(l.get('content'))}" for l in v.get("lists") or []
    )
    creada = v.get("createdAt")  # epoch en milisegundos
    return Vacante(
        fuente="lever", token=e.token, empresa=e.empresa,
        id_externo=str(v["id"]),
        titulo=(v.get("text") or "").strip(),
        ubicacion=_unir(cat.get("location"), *(cat.get("allLocations") or [])),
        url=v.get("hostedUrl") or "",
        publicada=(
            datetime.fromtimestamp(creada / 1000, tz=timezone.utc).isoformat()
            if creada else None
        ),
        descripcion=" ".join(
            x for x in (v.get("descriptionPlain"), listas, v.get("additionalPlain")) if x
        ).strip(),
    )


def _ashby(v: dict[str, Any], e: Empresa) -> Vacante:
    secundarias = [s.get("location") for s in v.get("secondaryLocations") or []]
    return Vacante(
        fuente="ashby", token=e.token, empresa=e.empresa,
        id_externo=str(v["id"]),
        titulo=(v.get("title") or "").strip(),
        ubicacion=_unir(v.get("location"), *secundarias),
        url=v.get("jobUrl") or "",
        publicada=v.get("publishedAt") or None,
        descripcion=(v.get("descriptionPlain") or limpiar_html(v.get("descriptionHtml"))),
    )


NORMALIZADORES: dict[str, Callable[[dict[str, Any], Empresa], Vacante]] = {
    "greenhouse": _greenhouse,
    "lever": _lever,
    "ashby": _ashby,
}


def _lista_de_vacantes(fuente: str, datos: Any) -> list[dict[str, Any]]:
    """Greenhouse y Ashby envuelven en {'jobs': [...]}; Lever devuelve la lista directa."""
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict) and isinstance(datos.get("jobs"), list):
        return datos["jobs"]
    raise ValueError(f"respuesta de {fuente} con forma inesperada: {type(datos).__name__}")


# --- Descarga -------------------------------------------------------------

def _leer_fixture(directorio: Path, e: Empresa) -> Any:
    ruta = directorio / f"{e.fuente}_{e.token}.json"
    if not ruta.exists():
        raise FileNotFoundError(f"no hay fixture {ruta.name}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def descargar(
    empresas: list[Empresa],
    fixtures: Path | None = None,
) -> tuple[list[Vacante], list[ReporteFuente]]:
    """Consulta cada fuente. Una fuente caida se REPORTA y no tumba la corrida.

    fixtures: si se pasa un directorio, lee JSON locales en vez de ir a la red
    (pruebas y modo sin conexion).
    """
    sesion = None if fixtures else _sesion()
    vacantes: list[Vacante] = []
    reportes: list[ReporteFuente] = []

    for e in empresas:
        base = dict(empresa=e.empresa, fuente=e.fuente, token=e.token)
        try:
            if fixtures:
                datos = _leer_fixture(fixtures, e)
            else:
                r = sesion.get(URLS[e.fuente].format(t=e.token), timeout=25)
                if r.status_code != 200:
                    reportes.append(ReporteFuente(**base, ok=False, detalle=f"HTTP {r.status_code}"))
                    continue
                datos = r.json()
            crudas = _lista_de_vacantes(e.fuente, datos)
        except (requests.RequestException, ValueError, FileNotFoundError) as error:
            reportes.append(ReporteFuente(**base, ok=False, detalle=str(error)[:200]))
            continue

        omitidas = 0
        for cruda in crudas:
            try:
                v = NORMALIZADORES[e.fuente](cruda, e)
            except (KeyError, TypeError, ValueError) as error:
                omitidas += 1
                log.warning("%s: vacante malformada omitida (%s)", e.empresa, error)
                continue
            if not v.titulo:
                omitidas += 1
                log.warning("%s: vacante %s sin titulo, omitida", e.empresa, v.id_externo)
                continue
            vacantes.append(v)

        reportes.append(ReporteFuente(
            **base, ok=True, vacantes=len(crudas) - omitidas, omitidas=omitidas,
            detalle="sin vacantes publicadas" if not crudas else "",
        ))

    return vacantes, reportes
