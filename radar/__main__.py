"""Punto de entrada: python -m radar

Uso:
  python -m radar                    corrida normal (Telegram si hay credenciales)
  python -m radar --seco             no envia nada a Telegram; imprime
  python -m radar --seco --no-guardar --fixtures tests/fixtures
                                     prueba completa sin red y sin tocar data/
  python -m radar --resumen          fuerza el resumen diario
  python -m radar --descubrir-chat   ayuda de configuracion: muestra tu chat_id

Credenciales por variables de entorno (en GitHub: Settings > Secrets):
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import RAIZ, cargar_config, cargar_empresas
from .pipeline import correr
from .telegram import Telegram, descubrir_chats

log = logging.getLogger("radar")


def _resumen_consola(res) -> str:
    ok = sum(r.ok for r in res.reportes)
    lineas = [
        f"Fuentes OK: {ok}/{len(res.reportes)}",
        f"Revisadas: {res.revisadas} | nuevas: {res.nuevas} | pasan prefiltro: {res.pasan_prefiltro}",
        f"Candidatas avisadas: {len(res.avisadas)} | duplicadas: {res.duplicadas} | cerradas: {res.cerradas}",
    ]
    lineas += [f"  CAIDA {r.empresa} ({r.fuente}/{r.token}): {r.detalle}" for r in res.reportes if not r.ok]
    lineas += [f"  -> #{f['n']} {f['puntaje']} {f['titulo']} | {f['empresa']} | {f['url']}" for f in res.avisadas]
    lineas += [f"  COMANDO {c}" for c in res.comandos]
    lineas += [f"  ERROR {e}" for e in res.errores]
    return "\n".join(lineas)


def _resumen_github(res) -> None:
    """Si corre en GitHub Actions, deja una tabla en la pagina de la ejecucion."""
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if not ruta:
        return
    filas = ["| Fuente | Estado | Vacantes |", "|---|---|---|"]
    filas += [
        f"| {r.empresa} | {'OK' if r.ok else 'CAIDA: ' + r.detalle} | {r.vacantes} |"
        for r in res.reportes
    ]
    cand = [f"- #{f['n']} **{f['puntaje']}** {f['titulo']} — {f['empresa']}" for f in res.avisadas]
    with open(ruta, "a", encoding="utf-8") as f:
        f.write("## Radar de vacantes\n\n")
        f.write(f"Revisadas {res.revisadas} · nuevas {res.nuevas} · candidatas {len(res.avisadas)}\n\n")
        f.write("\n".join(cand or ["Sin candidatas nuevas."]) + "\n\n" + "\n".join(filas) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar", description="Radar de vacantes")
    ap.add_argument("--seco", action="store_true", help="no envia a Telegram")
    ap.add_argument("--no-guardar", action="store_true", help="no escribe data/")
    ap.add_argument("--fixtures", type=Path, help="lee feeds desde JSON locales")
    ap.add_argument("--resumen", action="store_true", help="fuerza el resumen diario")
    ap.add_argument("--descubrir-chat", action="store_true", help="muestra el chat_id de quien le escribio al bot")
    ap.add_argument("--datos", type=Path, default=RAIZ / "data", help="carpeta del registro")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if args.descubrir_chat:
        if not token:
            print("Falta TELEGRAM_TOKEN.")
            return 2
        chats = descubrir_chats(token)
        if not chats:
            print("Nadie le ha escrito al bot. Mandale cualquier mensaje y vuelve a correr esto.")
        for cid, nombre in chats:
            print(f"chat_id={cid}  ({nombre})")
        return 0

    telegram = None
    if not args.seco:
        if token and chat_id:
            telegram = Telegram(token, chat_id)
        else:
            # Aviso visible en Actions (::warning::), no un fallo: el registro
            # igual se construye y las candidatas quedan pendientes de aviso.
            print("::warning::Sin TELEGRAM_TOKEN/TELEGRAM_CHAT_ID: corriendo en modo seco.")

    res = correr(
        cfg=cargar_config(),
        empresas=cargar_empresas(),
        ruta_registro=args.datos / "vacantes.csv",
        ruta_estado=args.datos / "estado.json",
        telegram=telegram,
        fixtures=args.fixtures,
        guardar=not args.no_guardar,
        forzar_resumen=args.resumen,
    )
    print(_resumen_consola(res))
    _resumen_github(res)

    # Codigo de salida != 0 => la ejecucion sale en rojo en GitHub y te llega un correo.
    if res.reportes and not any(r.ok for r in res.reportes):
        print("::error::Todas las fuentes fallaron.")
        return 1
    if res.errores:
        print("::error::" + " | ".join(res.errores))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
