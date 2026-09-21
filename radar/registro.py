"""Persistencia: data/vacantes.csv (registro) y data/estado.json (estado del bot).

Por que CSV en el repo y no una base de datos: son unas miles de filas, un
solo escritor (el workflow) y cada cambio queda versionado en git. El
historial del repo ES la auditoria: ves que entro y cuando.

Por que csv de la stdlib y no pandas: aqui no hay analisis, solo leer y
escribir filas. pandas agrega ~30 MB de dependencias y convierte tipos solo
(un id "0123" se vuelve 123). Para analizar el registro, pandas si: se lee
este mismo CSV.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any

COLUMNAS = [
    "n", "clave", "huella", "empresa", "fuente", "token", "id_externo",
    "titulo", "ubicacion", "url", "publicada", "descubierta", "cerrada",
    "prefiltro", "motivo", "tipo_rol", "puntaje", "desglose", "banderas",
    "estado", "notificada",
]

# estado: nueva | vista | duplicada
#   nueva     -> no la has revisado
#   vista     -> la marcaste con /visto desde Telegram
#   duplicada -> misma empresa y titulo que otra ya avisada (ventana de huella)


def _escribir_atomico(ruta: Path, escribir) -> None:
    """Escribe a un temporal y lo renombra: una corrida que muere a mitad
    no deja el registro medio escrito."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            escribir(f)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def leer_registro(ruta: Path) -> list[dict[str, str]]:
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        faltan = set(COLUMNAS) - set(lector.fieldnames or [])
        if faltan:
            raise ValueError(f"{ruta.name}: faltan columnas {sorted(faltan)}")
        return [dict(fila) for fila in lector]


def guardar_registro(ruta: Path, filas: list[dict[str, Any]]) -> None:
    def escribir(f):
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="raise")
        w.writeheader()
        for fila in filas:
            w.writerow({c: ("" if fila.get(c) is None else fila.get(c)) for c in COLUMNAS})
    _escribir_atomico(ruta, escribir)


ESTADO_INICIAL: dict[str, Any] = {
    "telegram_offset": 0,     # ultimo update de Telegram ya procesado
    "ultimo_resumen": "",     # fecha (Bogota) del ultimo resumen diario
    "ultima_corrida": "",
    "fuentes": {},            # token -> {"ok": bool, "detalle": str, "desde": iso}
}


def leer_estado(ruta: Path) -> dict[str, Any]:
    if not ruta.exists():
        return json.loads(json.dumps(ESTADO_INICIAL))
    with open(ruta, encoding="utf-8") as f:
        return {**ESTADO_INICIAL, **json.load(f)}


def guardar_estado(ruta: Path, estado: dict[str, Any]) -> None:
    _escribir_atomico(ruta, lambda f: json.dump(estado, f, ensure_ascii=False, indent=2))
