"""Canal de salida y de entrada: Telegram.

Salida: alertas de candidatas y resumen diario.
Entrada: comandos que escribes al bot (/visto 12). No hay servidor escuchando:
cada corrida lee los mensajes pendientes con getUpdates. Por eso un /visto
se aplica en la siguiente corrida, no al instante.

Telegram guarda los mensajes pendientes 24 horas. Con 4 corridas al dia
sobra margen.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{metodo}"
LIMITE = 4000  # Telegram corta en 4096; se deja margen para el HTML


class ErrorTelegram(RuntimeError):
    pass


def esc(texto: object) -> str:
    """Escapa para parse_mode=HTML: un '<' en un titulo rompe el mensaje entero."""
    return html.escape(str(texto), quote=False)


def _trozos(texto: str) -> list[str]:
    """Parte un mensaje largo por lineas, sin cortar una linea a la mitad."""
    trozos, actual = [], ""
    for linea in texto.split("\n"):
        if len(actual) + len(linea) + 1 > LIMITE and actual:
            trozos.append(actual)
            actual = ""
        actual += linea + "\n"
    if actual.strip():
        trozos.append(actual)
    return trozos


@dataclass
class Telegram:
    token: str
    chat_id: str

    def _llamar(self, metodo: str, **params) -> dict:
        r = requests.post(API.format(token=self.token, metodo=metodo), json=params, timeout=20)
        datos = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or not datos.get("ok"):
            # Nunca se loguea la URL: lleva el token.
            raise ErrorTelegram(f"{metodo}: HTTP {r.status_code} {datos.get('description', '')}")
        return datos

    def enviar(self, texto: str) -> None:
        for trozo in _trozos(texto):
            self._llamar(
                "sendMessage", chat_id=self.chat_id, text=trozo,
                parse_mode="HTML", disable_web_page_preview=True,
            )

    def leer_mensajes(self, offset: int) -> tuple[list[str], int]:
        """Mensajes nuevos de TU chat y el offset actualizado.

        Solo se aceptan mensajes de chat_id: cualquiera puede encontrar el bot
        y escribirle, y no debe poder cambiar tu registro.
        """
        datos = self._llamar("getUpdates", offset=offset + 1 if offset else 0, timeout=0,
                             allowed_updates=["message"])
        textos, ultimo = [], offset
        for upd in datos.get("result", []):
            ultimo = max(ultimo, upd["update_id"])
            msg = upd.get("message") or {}
            if str((msg.get("chat") or {}).get("id")) == str(self.chat_id) and msg.get("text"):
                textos.append(msg["text"])
        return textos, ultimo


_COMANDO = re.compile(r"^/(visto|vista|vistos|pendientes)\b(.*)$", re.IGNORECASE)


def interpretar(texto: str) -> tuple[str, list[int]] | None:
    """'/visto 12, 15 20' -> ('visto', [12, 15, 20]). None si no es un comando."""
    m = _COMANDO.match(texto.strip())
    if not m:
        return None
    comando = "pendientes" if m.group(1).lower() == "pendientes" else "visto"
    numeros = [int(x) for x in re.findall(r"\d+", m.group(2))]
    return comando, numeros


def descubrir_chats(token: str) -> list[tuple[str, str]]:
    """Ayuda de configuracion: lista (chat_id, nombre) de quien le ha escrito al bot."""
    r = requests.get(API.format(token=token, metodo="getUpdates"), timeout=20)
    r.raise_for_status()
    vistos = {}
    for upd in r.json().get("result", []):
        chat = (upd.get("message") or {}).get("chat") or {}
        if "id" in chat:
            vistos[str(chat["id"])] = chat.get("first_name") or chat.get("title") or ""
    return list(vistos.items())
