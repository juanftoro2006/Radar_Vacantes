"""Dashboard estatico: data/vacantes.csv -> site/index.html

Uso:
  python -m radar.dashboard                 genera site/index.html desde data/
  python -m radar.dashboard --salida X      en otra carpeta

En GitHub Actions se publica con GitHub Pages despues de cada corrida.
Localmente: generas y abres site/index.html en el navegador.

Reparto de papeles:
  Telegram  -> lo urgente (publicado hace <= 7 dias)
  Dashboard -> el inventario: todo lo abierto con puntaje >= umbral

Seguridad: titulos, ubicaciones y URLs vienen de feeds de terceros. Son
ENTRADA NO CONFIABLE: se escapan al incrustarse y solo se aceptan URLs
http(s). Un titulo con </script> o una url 'javascript:' no ejecutan nada.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import RAIZ, Config, cargar_config, cargar_empresas
from .pipeline import BOGOTA, _puntaje
from .registro import leer_estado, leer_registro


def url_segura(url: str) -> str:
    """Solo http(s). Cualquier otra cosa (javascript:, data:...) se descarta."""
    try:
        return url if urlparse(url).scheme in ("http", "https") else ""
    except ValueError:
        return ""


# Filas escritas antes del 21-sep-2026 tienen banderas sin tildes ("anos", "ingles").
# El registro no se repuntua, asi que se corrigen al mostrar. Borrar este mapa
# cuando no quede ninguna vacante abierta anterior a esa fecha.
_TEXTO_LEGADO = {
    " anos ": " años ", "ingles": "inglés", "hibrido": "híbrido",
    "titulo '": "título '", "autorizacion": "autorización", " pais": " país", "comision": "comisión",
}


def _corregir_legado(texto: str) -> str:
    for viejo, nuevo in _TEXTO_LEGADO.items():
        texto = texto.replace(viejo, nuevo)
    return texto


def seleccionar(registro: list[dict], cfg: Config) -> list[dict[str, Any]]:
    """Abiertas con puntaje >= umbral y sin knockout, una por huella.

    Si la misma vacante esta publicada en varias ciudades, se muestra la de
    mejor puntaje y las demas ubicaciones se listan debajo.
    """
    aptas = [
        f for f in registro
        if f["prefiltro"] == "si"
        and (_puntaje(f) or 0) >= cfg.puntaje.umbral
        and "KNOCKOUT" not in (f["banderas"] or "")
        and not f["cerrada"]
    ]
    por_huella: dict[str, dict[str, Any]] = {}
    for f in sorted(aptas, key=lambda f: -(_puntaje(f) or 0)):
        if f["huella"] in por_huella:
            por_huella[f["huella"]]["otras"].append(f["ubicacion"])
            continue
        por_huella[f["huella"]] = {
            "n": f["n"],
            "clave": f["clave"],
            "puntaje": _puntaje(f),
            "titulo": f["titulo"],
            "empresa": f["empresa"],
            "ubicacion": f["ubicacion"],
            "otras": [],
            "url": url_segura(f["url"]),
            "publicada": f["publicada"] or f["descubierta"],
            "desglose": f["desglose"],
            "banderas": [_corregir_legado(b) for b in (f["banderas"] or "").split(" || ") if b],
            "tipo_rol": f["tipo_rol"],
            "vista": f["estado"] == "vista",
        }
    return list(por_huella.values())


def construir_datos(registro: list[dict], estado: dict, cfg: Config) -> dict[str, Any]:
    nombres = {e.token: e.empresa for e in cargar_empresas(solo_activas=False)}
    fuentes = estado.get("fuentes") or {}
    caidas = [
        {"empresa": nombres.get(t, t), "detalle": f.get("detalle", ""), "desde": (f.get("desde") or "")[:10]}
        for t, f in sorted(fuentes.items()) if not f.get("ok")
    ]
    return {
        "generado": datetime.now(BOGOTA).isoformat(timespec="seconds"),
        "ultima_corrida": estado.get("ultima_corrida", ""),
        "umbral": cfg.puntaje.umbral,
        "ventana_alerta": cfg.candidatas.ventana_dias,
        "total_registro": len(registro),
        "fuentes_ok": sum(1 for f in fuentes.values() if f.get("ok")),
        "fuentes_total": len(fuentes),
        "caidas": caidas,
        "vacantes": seleccionar(registro, cfg),
    }


def _json_para_script(datos: dict) -> str:
    """JSON seguro dentro de <script>: '<' escapado evita cerrar la etiqueta desde un titulo."""
    return (
        json.dumps(datos, ensure_ascii=False)
        .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )


def generar_html(datos: dict) -> str:
    return PLANTILLA.replace("__DATOS__", _json_para_script(datos))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar.dashboard")
    ap.add_argument("--datos", type=Path, default=RAIZ / "data")
    ap.add_argument("--salida", type=Path, default=RAIZ / "site")
    args = ap.parse_args(argv)

    cfg = cargar_config()
    datos = construir_datos(
        leer_registro(args.datos / "vacantes.csv"), leer_estado(args.datos / "estado.json"), cfg
    )
    args.salida.mkdir(parents=True, exist_ok=True)
    destino = args.salida / "index.html"
    destino.write_text(generar_html(datos), encoding="utf-8")
    # .nojekyll: GitHub Pages sirve el HTML tal cual, sin procesarlo con Jekyll
    (args.salida / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Dashboard: {len(datos['vacantes'])} vacantes -> {destino}")
    return 0


PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Radar de Vacantes</title>
<style>
:root {
  --fondo: #f6f7f9; --panel: #ffffff; --texto: #1b1f24; --suave: #5b6470; --borde: #e3e6ea;
  --acento: #1f6feb; --acento-texto: #ffffff; --ok: #1a7f37; --brecha: #9a6700; --brecha-fondo: #fff4d6;
  --riesgo: #5b6470; --riesgo-fondo: #eef0f3; --nuevo: #1a7f37; --nuevo-fondo: #dafbe1; --postulada: #8250df;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fondo: #0d1117; --panel: #161b22; --texto: #e6edf3; --suave: #9198a1; --borde: #30363d;
    --acento: #2f81f7; --ok: #3fb950; --brecha: #d29922; --brecha-fondo: #2d2412;
    --riesgo: #9198a1; --riesgo-fondo: #21262d; --nuevo: #3fb950; --nuevo-fondo: #12261a; --postulada: #a371f7;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--fondo); color: var(--texto);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.envoltura { max-width: 880px; margin: 0 auto; padding: 20px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: var(--suave); font-size: 13px; }
.meta .mal { color: var(--brecha); }
.barra { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 18px 0 14px; }
.barra input[type=search] { flex: 1 1 220px; min-width: 0; padding: 8px 10px; border: 1px solid var(--borde);
  border-radius: 8px; background: var(--panel); color: var(--texto); font: inherit; }
.barra select, .barra label { font-size: 14px; }
.barra select { padding: 7px 8px; border: 1px solid var(--borde); border-radius: 8px;
  background: var(--panel); color: var(--texto); font: inherit; }
.barra label { display: flex; gap: 6px; align-items: center; color: var(--suave); }
.conteo { color: var(--suave); font-size: 13px; margin-bottom: 10px; }
.tarjeta { background: var(--panel); border: 1px solid var(--borde); border-radius: 10px;
  padding: 14px 16px; margin-bottom: 10px; display: grid; grid-template-columns: 52px 1fr; gap: 12px; }
.tarjeta.postulada { opacity: .6; }
.nota { font-weight: 700; font-size: 20px; text-align: center; line-height: 1; padding-top: 2px; }
.nota small { display: block; font-size: 11px; font-weight: 500; color: var(--suave); margin-top: 4px; }
.titulo { font-weight: 600; font-size: 16px; margin: 0; overflow-wrap: anywhere; }
.sub { color: var(--suave); font-size: 13px; margin: 2px 0 6px; overflow-wrap: anywhere; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.chip { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--riesgo-fondo); color: var(--riesgo); }
.chip.brecha { background: var(--brecha-fondo); color: var(--brecha); }
.chip.nuevo { background: var(--nuevo-fondo); color: var(--nuevo); font-weight: 600; }
.chip.postulada { color: var(--postulada); }
.desglose { font-size: 12px; color: var(--suave); }
.acciones { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.boton { font: inherit; font-size: 14px; padding: 7px 14px; border-radius: 8px; cursor: pointer;
  text-decoration: none; border: 1px solid var(--borde); background: var(--panel); color: var(--texto); }
.boton.principal { background: var(--acento); border-color: var(--acento); color: var(--acento-texto); font-weight: 600; }
.boton[aria-pressed=true] { border-color: var(--postulada); color: var(--postulada); }
.vacio { text-align: center; color: var(--suave); padding: 40px 0; }
footer { margin-top: 28px; font-size: 12px; color: var(--suave); }
@media (max-width: 480px) { .tarjeta { grid-template-columns: 1fr; } .nota { text-align: left; } .nota small { display: inline; margin-left: 6px; } }
</style>
</head>
<body>
<div class="envoltura">
  <h1>Radar de Vacantes</h1>
  <div class="meta" id="meta"></div>

  <div class="barra">
    <input type="search" id="buscar" placeholder="Buscar título, empresa, ubicación…" aria-label="Buscar">
    <select id="edad" aria-label="Antigüedad">
      <option value="0">Cualquier antigüedad</option>
      <option value="7">Últimos 7 días</option>
      <option value="30">Últimos 30 días</option>
    </select>
    <label><input type="checkbox" id="ocultar"> Ocultar postuladas</label>
  </div>
  <div class="conteo" id="conteo"></div>
  <div id="lista"></div>
  <footer id="pie"></footer>
</div>

<script id="datos" type="application/json">__DATOS__</script>
<script>
(function () {
  "use strict";
  const D = JSON.parse(document.getElementById("datos").textContent);
  const CLAVE = "radar.postuladas";
  const DIA = 86400000;

  // El estado "postule" vive solo en este navegador: el repo es publico.
  function leerPostuladas() {
    try { return JSON.parse(localStorage.getItem(CLAVE) || "{}"); } catch (e) { return {}; }
  }
  function guardarPostuladas(p) {
    try { localStorage.setItem(CLAVE, JSON.stringify(p)); } catch (e) { /* modo privado: no persiste */ }
  }
  let postuladas = leerPostuladas();

  function dias(iso) {
    const t = Date.parse(iso);
    return isNaN(t) ? null : Math.max(0, Math.floor((Date.now() - t) / DIA));
  }
  function textoDias(d) {
    return d === null ? "fecha desconocida" : d === 0 ? "hoy" : d === 1 ? "hace 1 día" : "hace " + d + " días";
  }
  function fechaCorta(iso) {
    const t = new Date(iso);
    return isNaN(t) ? "" : t.toLocaleString("es-CO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }
  // Todo el texto entra con textContent: nada de lo que venga de un feed se interpreta como HTML.
  function el(tag, clase, texto) {
    const n = document.createElement(tag);
    if (clase) n.className = clase;
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  function pintarMeta() {
    const meta = document.getElementById("meta");
    const partes = [];
    partes.push("Fuentes " + D.fuentes_ok + "/" + D.fuentes_total + " OK");
    if (D.ultima_corrida) partes.push("última corrida " + fechaCorta(D.ultima_corrida));
    partes.push(D.total_registro + " vacantes en el registro");
    meta.textContent = partes.join(" · ");
    D.caidas.forEach(function (c) {
      const s = el("div", "mal", "Caída: " + c.empresa + " (" + c.detalle + ")" + (c.desde ? " desde " + c.desde : ""));
      meta.appendChild(s);
    });
    document.getElementById("pie").textContent =
      "Abiertas con puntaje ≥ " + D.umbral + " y sin knockout. Telegram avisa solo lo publicado hace ≤ " +
      D.ventana_alerta + " días. Generado " + fechaCorta(D.generado) + ". “Postulé” se guarda solo en este navegador.";
  }

  function tarjeta(v) {
    const d = dias(v.publicada);
    const hecha = Boolean(postuladas[v.clave]);
    const t = el("article", "tarjeta" + (hecha ? " postulada" : ""));

    const nota = el("div", "nota", v.puntaje.toFixed(1));
    nota.appendChild(el("small", "", "#" + v.n));
    t.appendChild(nota);

    const cuerpo = el("div");
    cuerpo.appendChild(el("p", "titulo", v.titulo));
    const ubic = v.ubicacion + (v.otras.length ? "  (+" + v.otras.length + " ubicación" + (v.otras.length > 1 ? "es" : "") + ")" : "");
    cuerpo.appendChild(el("p", "sub", v.empresa + " · " + ubic + " · " + textoDias(d)));

    const chips = el("div", "chips");
    if (d !== null && d <= D.ventana_alerta) chips.appendChild(el("span", "chip nuevo", "Nueva"));
    if (v.vista) chips.appendChild(el("span", "chip", "Vista en Telegram"));
    if (hecha) chips.appendChild(el("span", "chip postulada", "Postulada el " + new Date(postuladas[v.clave]).toLocaleDateString("es-CO", { day: "numeric", month: "short" })));
    v.banderas.forEach(function (b) {
      chips.appendChild(el("span", "chip" + (b.indexOf("BRECHA") === 0 ? " brecha" : ""), b));
    });
    if (chips.childNodes.length) cuerpo.appendChild(chips);
    cuerpo.appendChild(el("div", "desglose", v.desglose));

    const acciones = el("div", "acciones");
    if (v.url) {
      const a = el("a", "boton principal", "Aplicar ↗");
      a.href = v.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      acciones.appendChild(a);
    }
    const b = el("button", "boton", hecha ? "✓ Postulé" : "Postulé");
    b.type = "button";
    b.setAttribute("aria-pressed", String(hecha));
    b.addEventListener("click", function () {
      if (postuladas[v.clave]) delete postuladas[v.clave]; else postuladas[v.clave] = new Date().toISOString();
      guardarPostuladas(postuladas);
      pintarLista();
    });
    acciones.appendChild(b);
    cuerpo.appendChild(acciones);

    t.appendChild(cuerpo);
    return t;
  }

  function pintarLista() {
    const q = document.getElementById("buscar").value.trim().toLowerCase();
    const maxEdad = Number(document.getElementById("edad").value);
    const ocultar = document.getElementById("ocultar").checked;

    const visibles = D.vacantes.filter(function (v) {
      if (ocultar && postuladas[v.clave]) return false;
      const d = dias(v.publicada);
      if (maxEdad && (d === null || d > maxEdad)) return false;
      if (!q) return true;
      return (v.titulo + " " + v.empresa + " " + v.ubicacion + " " + v.otras.join(" ")).toLowerCase().indexOf(q) !== -1;
    }).sort(function (a, b) {
      // Mas reciente primero: la ventaja del radar es llegar antes que la cola.
      return (Date.parse(b.publicada) || 0) - (Date.parse(a.publicada) || 0);
    });

    const lista = document.getElementById("lista");
    lista.replaceChildren();
    if (!visibles.length) {
      lista.appendChild(el("div", "vacio", D.vacantes.length ? "Nada con estos filtros." : "Todavía no hay vacantes sobre el umbral."));
    } else {
      visibles.forEach(function (v) { lista.appendChild(tarjeta(v)); });
    }
    const n = Object.keys(postuladas).length;
    document.getElementById("conteo").textContent =
      visibles.length + " de " + D.vacantes.length + " vacantes" + (n ? " · " + n + " postulada" + (n > 1 ? "s" : "") : "");
  }

  ["buscar", "edad", "ocultar"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", pintarLista);
  });
  pintarMeta();
  pintarLista();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
