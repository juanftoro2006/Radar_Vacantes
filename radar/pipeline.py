"""Orquestacion de una corrida del radar.

  comandos de Telegram -> descargar -> marcar cerradas -> nuevas por clave
  -> prefiltro + puntaje -> candidatas (ventana + huella) -> avisar -> guardar

Una corrida es idempotente: si se corta a mitad, la siguiente retoma sin
duplicar avisos (lo avisado queda marcado en 'notificada' solo si el envio
funciono).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Config
from .fuentes import descargar
from .modelos import Empresa, ReporteFuente
from .puntuar import puntuar
from .registro import guardar_estado, guardar_registro, leer_estado, leer_registro
from .telegram import ErrorTelegram, Telegram, esc, interpretar
from .texto import norm

log = logging.getLogger(__name__)
BOGOTA = ZoneInfo("America/Bogota")


def huella(token: str, titulo: str) -> str:
    """Dedup 2: misma empresa + mismo titulo normalizado."""
    return f"{token}:{''.join(c for c in norm(titulo) if c.isalnum())}"


def _fecha(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=BOGOTA)


def _edad_dias(fila: dict, ahora: datetime) -> float | None:
    """Edad desde la publicacion; si el ATS no la dio, desde que la descubrimos."""
    ref = _fecha(fila.get("publicada")) or _fecha(fila.get("descubierta"))
    return None if ref is None else (ahora - ref).total_seconds() / 86400


def _puntaje(fila: dict) -> float | None:
    try:
        return float(fila["puntaje"]) if fila.get("puntaje") not in (None, "") else None
    except ValueError:
        return None


def es_candidata(fila: dict, cfg: Config, ahora: datetime) -> bool:
    """La regla completa, en un solo lugar."""
    p = _puntaje(fila)
    edad = _edad_dias(fila, ahora)
    return (
        fila.get("prefiltro") == "si"
        and p is not None and p >= cfg.puntaje.umbral
        and "KNOCKOUT" not in (fila.get("banderas") or "")
        and not fila.get("cerrada")
        and fila.get("estado") == "nueva"
        and edad is not None and edad <= cfg.candidatas.ventana_dias
    )


@dataclass
class Resultado:
    revisadas: int = 0
    nuevas: int = 0
    pasan_prefiltro: int = 0
    avisadas: list[dict] = field(default_factory=list)
    duplicadas: int = 0
    cerradas: int = 0
    comandos: list[str] = field(default_factory=list)
    reportes: list[ReporteFuente] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


# --- Mensajes -------------------------------------------------------------

_DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_corta(dt: datetime) -> str:
    """'lun 22 sep, 06:17' sin depender del idioma del servidor."""
    return f"{_DIAS[dt.weekday()]} {dt.day} {_MESES[dt.month - 1]}, {dt:%H:%M}"


def _linea_candidata(f: dict, ahora: datetime) -> str:
    edad = _edad_dias(f, ahora)
    cuando = "hoy" if edad is not None and edad < 1 else f"hace {int(edad)} d" if edad is not None else "fecha desconocida"
    banderas = [b for b in (f.get("banderas") or "").split(" || ") if b]
    partes = [
        f"<b>#{f['n']} · {_puntaje(f):.1f}</b> — {esc(f['titulo'])}",
        f"{esc(f['empresa'])} · {esc(f['ubicacion'])} · publicada {cuando}",
        f"<i>{esc(f['desglose'])}</i>",
    ]
    partes += [f"⚠️ {esc(b)}" for b in banderas]
    partes.append(esc(f["url"]))
    return "\n".join(partes)


def mensaje_alerta(filas: list[dict], ahora: datetime) -> str:
    titulo = "🟢 <b>Nueva candidata</b>" if len(filas) == 1 else f"🟢 <b>{len(filas)} nuevas candidatas</b>"
    cuerpo = "\n\n".join(_linea_candidata(f, ahora) for f in filas)
    numeros = " ".join(f["n"] for f in filas)
    return f"{titulo}\n\n{cuerpo}\n\nCuando la revises: /visto {numeros}"


def mensaje_resumen(res: Resultado, pendientes: list[dict], estado: dict, ahora: datetime) -> str:
    ok = [r for r in res.reportes if r.ok]
    caidas = [r for r in res.reportes if not r.ok]
    vacias = [r for r in ok if r.vacantes == 0]
    lineas = [
        f"📡 <b>Radar</b> — {fecha_corta(ahora)}",
        f"{res.revisadas} vacantes revisadas · {res.nuevas} nuevas · {res.pasan_prefiltro} pasan prefiltro",
        f"Fuentes: {len(ok)}/{len(res.reportes)} OK",
    ]
    for r in caidas:
        desde = (estado["fuentes"].get(r.token) or {}).get("desde", "")[:10]
        lineas.append(f"  ❌ {esc(r.empresa)}: {esc(r.detalle)}" + (f" (desde {desde})" if desde else ""))
    if vacias:
        lineas.append("  Sin vacantes hoy: " + ", ".join(esc(r.empresa) for r in vacias))
    lineas.append("")
    if pendientes:
        lineas.append(f"<b>Pendientes por revisar ({len(pendientes)})</b>")
        for f in pendientes:
            edad = _edad_dias(f, ahora)
            lineas.append(
                f"#{f['n']} · {_puntaje(f):.1f} — {esc(f['titulo'])} · {esc(f['empresa'])}"
                f" · {int(edad) if edad is not None else '?'} d\n{esc(f['url'])}"
            )
        lineas.append("\n/visto N para sacarla de la lista")
    else:
        lineas.append("Sin candidatas pendientes.")
    return "\n".join(lineas)


# --- Corrida --------------------------------------------------------------

def correr(
    cfg: Config,
    empresas: list[Empresa],
    ruta_registro: Path,
    ruta_estado: Path,
    telegram: Telegram | None,
    ahora: datetime | None = None,
    fixtures: Path | None = None,
    guardar: bool = True,
    forzar_resumen: bool = False,
) -> Resultado:
    ahora = ahora or datetime.now(BOGOTA)
    hoy = ahora.date().isoformat()
    res = Resultado()
    registro = leer_registro(ruta_registro)
    estado = leer_estado(ruta_estado)
    por_n = {f["n"]: f for f in registro}

    # 1) Comandos pendientes en Telegram
    pedir_resumen = forzar_resumen
    if telegram:
        try:
            textos, estado["telegram_offset"] = telegram.leer_mensajes(estado["telegram_offset"])
        except (ErrorTelegram, OSError) as e:
            res.errores.append(f"no se pudieron leer comandos: {e}")
            textos = []
        for texto in textos:
            orden = interpretar(texto)
            if not orden:
                continue
            comando, numeros = orden
            if comando == "pendientes":
                pedir_resumen = True
            for num in numeros:
                fila = por_n.get(str(num))
                if fila and fila["estado"] == "nueva":
                    fila["estado"] = "vista"
                    res.comandos.append(f"#{num} marcada como vista")
                elif fila:
                    res.comandos.append(f"#{num} ya estaba {fila['estado']}")
                else:
                    res.comandos.append(f"#{num} no existe")

    # 2) Descargar
    vacantes, res.reportes = descargar(empresas, fixtures=fixtures)
    res.revisadas = len(vacantes)
    for r in res.reportes:
        previo = estado["fuentes"].get(r.token) or {}
        cambio = previo.get("ok") != r.ok
        estado["fuentes"][r.token] = {
            "ok": r.ok, "detalle": r.detalle,
            "desde": ahora.isoformat() if cambio or not previo else previo.get("desde", ahora.isoformat()),
        }

    # 3) Cerradas: estaban en el registro, su fuente respondio y ya no aparecen
    tokens_ok = {r.token for r in res.reportes if r.ok}
    vivas = {v.clave for v in vacantes}
    for fila in registro:
        if fila["token"] in tokens_ok:
            if fila["clave"] not in vivas and not fila["cerrada"]:
                fila["cerrada"] = hoy
                res.cerradas += 1
            elif fila["clave"] in vivas and fila["cerrada"]:
                fila["cerrada"] = ""  # reabierta

    # 4) Nuevas por clave + evaluacion
    claves = {f["clave"] for f in registro}
    siguiente = max((int(f["n"]) for f in registro), default=0) + 1
    for v in vacantes:
        if v.clave in claves:
            continue
        claves.add(v.clave)
        ev = puntuar(v, cfg)
        res.nuevas += 1
        res.pasan_prefiltro += ev.prefiltro == "si"
        fila = {
            "n": str(siguiente), "clave": v.clave, "huella": huella(v.token, v.titulo),
            "empresa": v.empresa, "fuente": v.fuente, "token": v.token,
            "id_externo": v.id_externo, "titulo": v.titulo, "ubicacion": v.ubicacion,
            "url": v.url, "publicada": v.publicada or "", "descubierta": ahora.isoformat(timespec="seconds"),
            "cerrada": "", "prefiltro": ev.prefiltro, "motivo": ev.motivo, "tipo_rol": ev.tipo_rol,
            "puntaje": "" if ev.puntaje is None else f"{ev.puntaje:g}",
            "desglose": ev.desglose, "banderas": " || ".join(ev.banderas),
            "estado": "nueva", "notificada": "",
        }
        registro.append(fila)
        por_n[fila["n"]] = fila
        siguiente += 1

    # 5) Candidatas por avisar (incluye las que un envio fallido dejo pendientes)
    por_avisar = [f for f in registro if es_candidata(f, cfg, ahora) and not f["notificada"]]
    # La mejor de cada huella primero: si la misma vacante sale en 3 ciudades, gana la de mejor puntaje
    por_avisar.sort(key=lambda f: (-(_puntaje(f) or 0), f["ubicacion"]))
    limite_huella = ahora - timedelta(days=cfg.candidatas.huella_dias)
    avisadas_por_huella = {
        f["huella"]: f for f in registro
        if f["notificada"] and (_fecha(f["notificada"]) or ahora) >= limite_huella
    }
    for f in por_avisar:
        previa = avisadas_por_huella.get(f["huella"])
        if previa and previa is not f:
            f["estado"] = "duplicada"
            f["motivo"] = f"{f['motivo']}; misma vacante que #{previa['n']}"
            res.duplicadas += 1
        else:
            res.avisadas.append(f)
            avisadas_por_huella[f["huella"]] = f

    # 6) Avisar
    if telegram and res.avisadas:
        try:
            telegram.enviar(mensaje_alerta(res.avisadas, ahora))
            for f in res.avisadas:
                f["notificada"] = ahora.isoformat(timespec="seconds")
        except (ErrorTelegram, OSError) as e:
            # No se marcan como notificadas: la siguiente corrida reintenta.
            res.errores.append(f"no se pudo enviar la alerta: {e}")
    elif not telegram:
        for f in res.avisadas:
            log.info("CANDIDATA (modo seco): #%s %s — %s", f["n"], f["puntaje"], f["titulo"])

    # 7) Resumen diario: primera corrida de cada dia (hora Bogota) o si lo pediste
    # Mas reciente primero: dentro de la ventana, lo que decide es llegar antes que la cola.
    pendientes = sorted(
        (f for f in registro if f["notificada"] and es_candidata(f, cfg, ahora)),
        key=lambda f: _edad_dias(f, ahora) or 0,
    )
    if res.comandos and telegram:
        try:
            telegram.enviar("✔️ " + "\n✔️ ".join(esc(c) for c in res.comandos))
        except (ErrorTelegram, OSError) as e:
            res.errores.append(f"no se pudo confirmar comandos: {e}")
    if telegram and (pedir_resumen or estado["ultimo_resumen"] != hoy):
        try:
            telegram.enviar(mensaje_resumen(res, pendientes, estado, ahora))
            estado["ultimo_resumen"] = hoy
        except (ErrorTelegram, OSError) as e:
            res.errores.append(f"no se pudo enviar el resumen: {e}")

    # 8) Guardar
    estado["ultima_corrida"] = ahora.isoformat(timespec="seconds")
    if guardar:
        guardar_registro(ruta_registro, registro)
        guardar_estado(ruta_estado, estado)
    return res
