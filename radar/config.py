"""Carga y valida la configuracion: config/radar.json y config/empresas.csv.

Las claves que empiezan con '_' en el JSON son comentarios para humanos y se
ignoran al validar.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from .modelos import Empresa

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_DIR = RAIZ / "config"


class _Base(BaseModel):
    # extra="ignore": los comentarios "_nota", "_regla"... no rompen la carga.
    model_config = ConfigDict(extra="ignore", frozen=True)


class Perfil(_Base):
    anos_dev: int
    ciudad_base: str


class Ubicacion(_Base):
    fuerte: list[str]
    remoto: list[str]
    region_permitida: list[str]
    relleno: list[str]


class Prefiltro(_Base):
    titulo_incluye: list[str]
    ubicacion: Ubicacion


class Nivel(_Base):
    puntos: float = 0
    knockout: bool = False
    brecha: bool = False


class Escala(_Base):
    top: Nivel
    lead: Nivel
    senior: Nivel
    mid: Nivel
    junior: Nivel
    intern: Nivel
    sin_marca: Nivel


class Seniority(_Base):
    desarrollo: Escala
    automatizacion: Escala


class GrupoStack(_Base):
    peso: float
    terminos: list[str]


class Stack(_Base):
    fuerte: GrupoStack
    solido: GrupoStack
    basico: GrupoStack


class TipoRol(_Base):
    automatizacion: list[str]


class Pesos(_Base):
    stack: float
    seniority: float
    contexto: float

    @model_validator(mode="after")
    def _suman_uno(self) -> "Pesos":
        total = self.stack + self.seniority + self.contexto
        if abs(total - 1) > 1e-6:
            raise ValueError(f"los pesos deben sumar 1, suman {total}")
        return self


class Puntaje(_Base):
    pesos: Pesos
    bruto_de_referencia: float
    piso_stack: float
    umbral: float
    puntos_por_sector: float
    stack: Stack
    sectores: list[str]
    tipo_rol: TipoRol
    seniority: Seniority


class Candidatas(_Base):
    ventana_dias: int
    huella_dias: int


class Config(_Base):
    perfil: Perfil
    prefiltro: Prefiltro
    puntaje: Puntaje
    candidatas: Candidatas


def cargar_config(ruta: Path | None = None) -> Config:
    ruta = ruta or CONFIG_DIR / "radar.json"
    with open(ruta, encoding="utf-8") as f:
        return Config.model_validate(json.load(f))


def cargar_empresas(ruta: Path | None = None, solo_activas: bool = True) -> list[Empresa]:
    ruta = ruta or CONFIG_DIR / "empresas.csv"
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    empresas = [
        Empresa(
            empresa=fila["empresa"].strip(),
            fuente=fila["fuente"].strip(),
            token=fila["token"].strip(),
            activa=fila.get("activa", "si").strip().lower() in ("si", "sí", "true", "1"),
            nota=(fila.get("nota") or "").strip(),
        )
        for fila in filas
        if fila.get("token", "").strip()
    ]
    return [e for e in empresas if e.activa] if solo_activas else empresas
