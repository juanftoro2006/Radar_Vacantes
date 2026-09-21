"""Piezas compartidas por las pruebas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from radar.config import cargar_config
from radar.modelos import Empresa, Vacante

FIXTURES = Path(__file__).parent / "fixtures"
# Hora fija: las pruebas no pueden depender del dia en que se corren.
AHORA = datetime(2026, 9, 22, 6, 17, tzinfo=ZoneInfo("America/Bogota"))


@pytest.fixture(scope="session")
def cfg():
    # Se prueba contra la configuracion REAL: si alguien edita radar.json y
    # rompe un caso conocido, la prueba lo dice.
    return cargar_config()


@pytest.fixture
def empresas() -> list[Empresa]:
    datos = [
        ("Clara", "greenhouse", "clara"), ("Sezzle", "greenhouse", "sezzle"),
        ("Backblaze", "greenhouse", "backblaze"), ("Remote.com", "greenhouse", "remotecom"),
        ("Twilio", "greenhouse", "twilio"), ("GitLab", "greenhouse", "gitlab"),
        ("NinjaTrader", "greenhouse", "ninjatrader"), ("Addi", "ashby", "addi"),
        ("Mural", "ashby", "mural"), ("Yuno", "lever", "yuno"),
        ("Bitso", "greenhouse", "bitso"),  # sin fixture: simula una fuente caida
    ]
    return [Empresa(empresa=e, fuente=f, token=t) for e, f, t in datos]


def vacante(titulo: str, descripcion: str = "", ubicacion: str = "Colombia", **extra) -> Vacante:
    """Atajo para construir vacantes en pruebas unitarias."""
    base = dict(fuente="greenhouse", token="prueba", empresa="Prueba", id_externo="1",
                titulo=titulo, ubicacion=ubicacion, descripcion=descripcion)
    return Vacante(**{**base, **extra})


class TelegramFalso:
    """Registra lo que se enviaria y entrega mensajes simulados."""

    def __init__(self, entrada: list[str] | None = None, falla_envio: bool = False):
        self.entrada = entrada or []
        self.enviados: list[str] = []
        self.falla_envio = falla_envio

    def leer_mensajes(self, offset: int):
        return self.entrada, offset + len(self.entrada)

    def enviar(self, texto: str) -> None:
        from radar.telegram import ErrorTelegram
        if self.falla_envio:
            raise ErrorTelegram("sendMessage: HTTP 502")
        self.enviados.append(texto)
