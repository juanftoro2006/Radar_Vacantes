"""
verificar_tokens.py  (v2)
Recibe URLs completas de ATS, extrae fuente y token, verifica el feed publico
y genera empresas.csv listo para importar al Sheet.

Uso:  python verificar_tokens.py
"""

import csv
import time
from urllib.parse import urlparse

import requests

# ---------------------------------------------------------------------------
# EDITA SOLO ESTA LISTA. Pega la URL COMPLETA, tal cual la copiaste del navegador.
# No importa si trae /jobs/4521 al final ni parametros: el script lo limpia.
# ---------------------------------------------------------------------------
URLS_CANDIDATAS = [
    "https://job-boards.greenhouse.io/sezzle/jobs/6546183003",
    "https://job-boards.greenhouse.io/nimblegravity/jobs/4563403005",
    "https://job-boards.greenhouse.io/backblaze/jobs/4740803008",
    "https://job-boards.greenhouse.io/ninjatrader",
]

# Mismo patron de siempre: toda la diferencia entre proveedores vive en un mapa.
# host del ATS -> (nombre de la fuente, plantilla de la URL de API)
PROVEEDORES = {
    "boards.greenhouse.io": (
        "greenhouse",
        "https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true",
    ),
    "job-boards.greenhouse.io": (
        "greenhouse",
        "https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true",
    ),
    "jobs.lever.co": (
        "lever",
        "https://api.lever.co/v0/postings/{t}?mode=json",
    ),
    "jobs.ashbyhq.com": (
        "ashby",
        "https://api.ashbyhq.com/posting-api/job-board/{t}",
    ),
}


def extraer(url: str) -> tuple | None:
    """
    De una URL completa saca (fuente, token, plantilla_url).
    Devuelve None si el host no es un ATS conocido.
    """
    partes = urlparse(url.strip())
    host = partes.netloc.lower().replace("www.", "")

    if host not in PROVEEDORES:
        return None

    # El token siempre es el primer segmento de la ruta:
    #   /deel/jobs/4521  ->  ["deel", "jobs", "4521"]  ->  "deel"
    segmentos = [s for s in partes.path.split("/") if s]
    if not segmentos:
        return None

    fuente, plantilla = PROVEEDORES[host]
    return fuente, segmentos[0], plantilla


def verificar(plantilla: str, token: str) -> dict:
    """Consulta el feed publico y reporta si el token es valido."""
    try:
        # timeout obligatorio: sin el, un servidor lento cuelga el script entero
        respuesta = requests.get(plantilla.format(t=token), timeout=10)
    except requests.RequestException as error:
        return {"ok": False, "vacantes": 0, "detalle": f"sin conexion: {error}"}

    if respuesta.status_code != 200:
        return {"ok": False, "vacantes": 0, "detalle": f"HTTP {respuesta.status_code}"}

    datos = respuesta.json()
    # Greenhouse devuelve {"jobs": [...]}, Lever y Ashby varian en su forma.
    vacantes = datos.get("jobs", datos) if isinstance(datos, dict) else datos

    return {"ok": True, "vacantes": len(vacantes), "detalle": "valido"}


def main() -> None:
    validos = []
    ya_procesados = set()  # evita verificar dos veces la misma empresa

    print(f"\n{'':<3}{'FUENTE':<12}{'TOKEN':<22}{'VACANTES':>9}  DETALLE")
    print("-" * 66)

    for url in URLS_CANDIDATAS:
        datos = extraer(url)

        if datos is None:
            print(f"XX {'?':<12}{url[:22]:<22}{0:>9}  host no reconocido")
            continue

        fuente, token, plantilla = datos

        if (fuente, token) in ya_procesados:
            continue
        ya_procesados.add((fuente, token))

        resultado = verificar(plantilla, token)
        marca = "OK " if resultado["ok"] else "XX "
        print(
            f"{marca}{fuente:<12}{token:<22}"
            f"{resultado['vacantes']:>9}  {resultado['detalle']}"
        )

        if resultado["ok"]:
            validos.append([token.capitalize(), fuente, token, plantilla])

        time.sleep(0.4)  # no martillees el servidor de nadie

    with open("empresas.csv", "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["empresa", "fuente", "token", "plantilla_url"])
        escritor.writerows(validos)

    print("-" * 66)
    print(f"\n{len(validos)} validos -> empresas.csv (4 columnas, listo para el Sheet)\n")


if __name__ == "__main__":
    main()