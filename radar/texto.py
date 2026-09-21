"""Utilidades de texto: normalizar, limpiar HTML y buscar terminos.

Todo el matching del radar pasa por aqui. Si una regla de comparacion
cambia, cambia en un solo lugar.
"""

from __future__ import annotations

import html
import re
import unicodedata
from functools import lru_cache


def norm(texto: str | None) -> str:
    """Minusculas y sin tildes: 'Medellín' y 'medellin' deben ser lo mismo."""
    if not texto:
        return ""
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return sin_tildes.lower()


_ETIQUETA = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"\s+")


def limpiar_html(contenido: str | None) -> str:
    """HTML -> texto plano, SIN recortar.

    Greenhouse manda el HTML escapado dos veces (&lt;p&gt;...&amp;nbsp;), por
    eso se desescapa antes y despues de quitar etiquetas.

    Por que no se recorta: el prefiltro y el puntaje son gratis. Recortar a
    3500 caracteres dejaba al puntaje leyendo la presentacion de la empresa y
    no los requisitos (65 de 70 vacantes llegaban cortadas). Si una capa con
    LLM necesita un tope, lo aplica ella.
    """
    if not contenido:
        return ""
    texto = html.unescape(contenido)
    texto = _ETIQUETA.sub(" ", texto)
    texto = html.unescape(texto)
    return _ESPACIOS.sub(" ", texto).strip()


@lru_cache(maxsize=4096)
def _patron(termino: str, modo: str) -> re.Pattern[str]:
    """Compila el regex de un termino una sola vez (se usan miles de veces por corrida)."""
    t = re.escape(norm(termino))
    if modo == "estricto":      # ai, ml, api: nunca dentro de otra palabra
        return re.compile(rf"\b{t}\b")
    if modo == "plural":        # integration -> integrations, api -> apis
        return re.compile(rf"\b{t}s?\b")
    if modo == "raiz":          # engineer -> engineering, engineers
        return re.compile(rf"\b{t}\w*")
    raise ValueError(f"modo desconocido: {modo}")


def contiene(texto: str, termino: str, modo: str = "estricto") -> bool:
    """texto ya debe venir normalizado con norm()."""
    return bool(_patron(termino, modo).search(texto))


def contiene_titulo(titulo: str, termino: str) -> bool:
    """Regla del prefiltro de titulos.

    Siglas de 3 letras o menos (ai, ml, api, rpa, n8n): estrictas, para que
    'ai' no pegue en 'chair' ni 'ml' en 'html'.
    El resto: raiz abierta, para que 'engineer' pegue en 'Engineering' e
    'integration' en 'Integrations'. Con limite estricto se perdian.
    """
    modo = "estricto" if len(termino) <= 3 else "raiz"
    return contiene(titulo, termino, modo)


def terminos_presentes(texto: str, terminos: list[str]) -> list[str]:
    """Que terminos aparecen en el texto, contando cada uno UNA vez y sin doble conteo.

    Los terminos largos se evaluan primero y su texto se retira antes de
    evaluar los cortos. Asi 'rest api' no cuenta ademas como 'api', ni
    'node.js' como 'node'. Si 'api' aparece en OTRA parte del texto, si cuenta.
    """
    restante = texto
    encontrados = []
    for termino in sorted(set(terminos), key=len, reverse=True):
        patron = _patron(termino, "plural")
        if patron.search(restante):
            encontrados.append(termino)
            restante = patron.sub(" ", restante)
    return encontrados
