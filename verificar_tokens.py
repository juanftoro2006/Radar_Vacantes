"""
verificar_tokens.py  (v3)
Recibe URLs completas de ATS, extrae fuente y token, verifica el feed publico
y AGREGA las validas a config/empresas.csv (no borra ni duplica las que ya estan).

Uso:
  1. Pega URLs en config/urls_candidatas.txt (una por linea; # para comentarios)
  2. python verificar_tokens.py
  3. Revisa el diff de config/empresas.csv (git diff) y corrige el nombre legible si hace falta

Cambio frente a v2: las URLs ya no viven dentro del codigo, y la salida ya no
pisa empresas.csv. Configuracion fuera del codigo; el humano revisa con git diff.
"""

import csv
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

RAIZ = Path(__file__).resolve().parent
ENTRADA = RAIZ / "config" / "urls_candidatas.txt"
SALIDA = RAIZ / "config" / "empresas.csv"
COLUMNAS = ["empresa", "fuente", "token", "activa", "nota"]

# host del ATS -> (nombre de la fuente, URL del feed). Misma idea de siempre:
# toda la diferencia entre proveedores vive en un mapa.
PROVEEDORES = {
    "boards.greenhouse.io": ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{t}/jobs"),
    "job-boards.greenhouse.io": ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{t}/jobs"),
    "jobs.lever.co": ("lever", "https://api.lever.co/v0/postings/{t}?mode=json"),
    "jobs.ashbyhq.com": ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{t}"),
}


def leer_urls() -> list[str]:
    if not ENTRADA.exists():
        return []
    lineas = ENTRADA.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lineas if l.strip() and not l.strip().startswith("#")]


def extraer(url: str) -> tuple | None:
    """De una URL completa saca (fuente, token, url_feed). None si el host no es un ATS conocido."""
    partes = urlparse(url.strip())
    host = partes.netloc.lower().replace("www.", "")
    if host not in PROVEEDORES:
        return None
    # El token siempre es el primer segmento de la ruta: /deel/jobs/4521 -> "deel"
    segmentos = [s for s in partes.path.split("/") if s]
    if not segmentos:
        return None
    fuente, plantilla = PROVEEDORES[host]
    return fuente, segmentos[0], plantilla


def verificar(plantilla: str, token: str) -> dict:
    """Consulta el feed publico y reporta si el token es valido."""
    try:
        # timeout obligatorio: sin el, un servidor lento cuelga el script entero
        respuesta = requests.get(plantilla.format(t=token), timeout=15)
    except requests.RequestException as error:
        return {"ok": False, "vacantes": 0, "detalle": f"sin conexion: {error}"}
    if respuesta.status_code != 200:
        return {"ok": False, "vacantes": 0, "detalle": f"HTTP {respuesta.status_code}"}
    datos = respuesta.json()
    # Greenhouse y Ashby devuelven {"jobs": [...]}; Lever, la lista directa.
    vacantes = datos.get("jobs", []) if isinstance(datos, dict) else datos
    detalle = "valido" if vacantes else "valido pero SIN vacantes hoy (revisa si es el token correcto)"
    return {"ok": True, "vacantes": len(vacantes), "detalle": detalle}


def leer_existentes() -> list[dict]:
    if not SALIDA.exists():
        return []
    with open(SALIDA, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    existentes = leer_existentes()
    ya = {(e["fuente"], e["token"]) for e in existentes}
    nuevas = []

    print(f"\n{'':<3}{'FUENTE':<12}{'TOKEN':<22}{'VACANTES':>9}  DETALLE")
    print("-" * 70)
    for url in leer_urls():
        datos = extraer(url)
        if datos is None:
            print(f"XX {'?':<12}{url[:22]:<22}{0:>9}  host no reconocido")
            continue
        fuente, token, plantilla = datos
        if (fuente, token) in ya:
            print(f"-- {fuente:<12}{token:<22}{'':>9}  ya estaba en empresas.csv")
            continue
        ya.add((fuente, token))

        resultado = verificar(plantilla, token)
        marca = "OK " if resultado["ok"] else "XX "
        print(f"{marca}{fuente:<12}{token:<22}{resultado['vacantes']:>9}  {resultado['detalle']}")
        if resultado["ok"]:
            nuevas.append({"empresa": token.capitalize(), "fuente": fuente, "token": token,
                           "activa": "si", "nota": "agregada por verificar_tokens.py"})
        time.sleep(0.4)  # no martillees el servidor de nadie

    if nuevas:
        with open(SALIDA, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
            w.writeheader()
            w.writerows(existentes + nuevas)
    print("-" * 70)
    print(f"\n{len(nuevas)} nuevas agregadas a config/empresas.csv. Revisa con: git diff config/empresas.csv\n")


if __name__ == "__main__":
    main()
