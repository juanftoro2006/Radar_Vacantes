"""Modelos de datos del radar (pydantic).

Por que pydantic y no dicts: un dict mal escrito ('titlo') falla tarde y en
silencio; un modelo falla al cargar, con el nombre del campo. En un pipeline
que corre solo en la nube, fallar temprano y con mensaje es lo que te deja
diagnosticar desde el celular.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Fuente = Literal["greenhouse", "lever", "ashby"]


class Empresa(BaseModel):
    empresa: str
    fuente: Fuente
    token: str
    activa: bool = True
    nota: str = ""


class Vacante(BaseModel):
    """Una vacante normalizada: el mismo esquema para los tres ATS."""

    fuente: Fuente
    token: str
    empresa: str
    id_externo: str
    titulo: str
    ubicacion: str = "sin especificar"
    url: str = ""
    publicada: str | None = None  # ISO 8601 o None. Nunca "" : vacio no es fecha.
    descripcion: str = ""         # texto completo; NO se guarda en el registro

    @property
    def clave(self) -> str:
        """Dedup 1: identifica la vacante exacta en el ATS."""
        return f"{self.fuente}:{self.token}:{self.id_externo}"


class ReporteFuente(BaseModel):
    """Lo que paso con cada fuente en la corrida. Ninguna caida es silenciosa."""

    empresa: str
    fuente: Fuente
    token: str
    ok: bool
    vacantes: int = 0
    omitidas: int = 0
    detalle: str = ""


class Evaluacion(BaseModel):
    prefiltro: Literal["si", "no"]
    motivo: str
    tipo_rol: str = ""
    puntaje: float | None = None  # None = no se evaluo. 0 = se evaluo y quedo fuera.
    desglose: str = ""
    banderas: list[str] = Field(default_factory=list)

    @property
    def knockout(self) -> bool:
        return any(b.startswith("KNOCKOUT") for b in self.banderas)
