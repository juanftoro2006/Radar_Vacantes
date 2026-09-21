"""Prefiltro (capa 0): titulo + ubicacion. Barato, determinista, generoso.

No descarta: MARCA. Todo se registra con su motivo.
"""

from __future__ import annotations

import re

from .config import Prefiltro
from .texto import contiene, contiene_titulo, norm

_SEPARADORES = re.compile(r"[;/|·]")
_NO_LETRAS = re.compile(r"[^a-z\s]")


def titulo_ok(titulo: str, cfg: Prefiltro) -> bool:
    t = norm(titulo)
    return any(contiene_titulo(t, termino) for termino in cfg.titulo_incluye)


def clasificar_ubicacion(ubicacion: str, cfg: Prefiltro) -> str:
    """Devuelve 'fuerte', 'remoto' o 'fuera'.

    Lista BLANCA real: pasa lo que nombra un lugar donde eres elegible, o lo
    que es remoto sin nombrar ningun lugar. Todo lo demas queda fuera.

    Por que se cambio: la version anterior dejaba pasar cualquier cosa con
    'remote' que no estuviera en una lista negra de paises. 'Sweden (Remote)',
    'Remote, Singapore' o 'San Francisco / Remote' pasaban como 'remoto sin
    pais'. Una lista negra de paises siempre tiene un agujero: hay 190 paises.
    """
    u = cfg.ubicacion
    texto = norm(ubicacion)
    if not texto or texto == "sin especificar":
        return "remoto"  # sin dato: pasa y lo decide quien lee (falso negativo es mas caro)

    segmentos = [s.strip() for s in _SEPARADORES.split(texto) if s.strip()]

    if any(contiene(s, lugar) for s in segmentos for lugar in u.fuerte):
        return "fuerte"

    quitar = sorted(u.remoto + u.region_permitida, key=len, reverse=True)
    for s in segmentos:
        resto = f" {s} "
        for palabra in quitar:
            resto = re.sub(rf"\b{re.escape(palabra)}\b", " ", resto)
        palabras = [p for p in _NO_LETRAS.sub(" ", resto).split() if p not in u.relleno]
        es_remoto = any(contiene(s, r) for r in u.remoto + u.region_permitida)
        if es_remoto and not palabras:
            return "remoto"
    return "fuera"


def evaluar_prefiltro(titulo: str, ubicacion: str, cfg: Prefiltro) -> tuple[bool, str]:
    """(pasa, motivo). El motivo siempre explica la decision."""
    tit = titulo_ok(titulo, cfg)
    ubic = clasificar_ubicacion(ubicacion, cfg)
    if not tit:
        return False, "titulo fuera de perfil"
    if ubic == "fuera":
        return False, "ubicacion fuera de Colombia/LATAM/remoto global"
    if ubic == "fuerte":
        return True, "ubicacion compatible"
    return True, "remoto sin pais, confirmar elegibilidad"
