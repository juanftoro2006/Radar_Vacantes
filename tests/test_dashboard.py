import json
import re

from radar.dashboard import construir_datos, generar_html, seleccionar, url_segura
from radar.pipeline import correr
from radar.registro import leer_estado, leer_registro

from .conftest import AHORA, FIXTURES, TelegramFalso


def _fila(**extra):
    base = dict(n="1", clave="greenhouse:x:1", huella="x:automationengineer", empresa="X",
                titulo="Automation Engineer", ubicacion="Colombia", url="https://ejemplo.com/1",
                publicada="2026-09-20T10:00:00-05:00", descubierta="2026-09-20T11:00:00-05:00",
                cerrada="", prefiltro="si", motivo="", tipo_rol="automatizacion", puntaje="7",
                desglose="stack 7", banderas="", estado="nueva", notificada="")
    return {**base, **extra}


def test_seleccion_respeta_umbral_knockout_y_cerradas(cfg):
    filas = [
        _fila(n="1"),
        _fila(n="2", clave="c2", huella="h2", puntaje="4.9"),
        _fila(n="3", clave="c3", huella="h3", banderas="KNOCKOUT: algo"),
        _fila(n="4", clave="c4", huella="h4", cerrada="2026-09-21"),
        _fila(n="5", clave="c5", huella="h5", prefiltro="no", puntaje=""),
        _fila(n="6", clave="c6", huella="h6", estado="vista"),   # vista si se muestra
    ]
    assert [v["n"] for v in seleccionar(filas, cfg)] == ["1", "6"]


def test_misma_huella_se_agrupa_con_la_mejor(cfg):
    filas = [_fila(n="1", ubicacion="Bogota", puntaje="6"),
             _fila(n="2", clave="c2", ubicacion="Latin America", puntaje="7")]
    [v] = seleccionar(filas, cfg)
    assert v["n"] == "2" and v["otras"] == ["Bogota"]


def test_url_no_http_se_descarta():
    assert url_segura("javascript:alert(1)") == ""
    assert url_segura("https://jobs.lever.co/x") == "https://jobs.lever.co/x"


def test_titulo_malicioso_no_cierra_el_script(cfg):
    # Los titulos vienen de feeds de terceros: entrada no confiable.
    fila = _fila(titulo="</script><script>alert(1)</script>")
    html = generar_html(construir_datos([fila], {"fuentes": {}}, cfg))
    bloque = re.search(r'<script id="datos" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert "</script>" not in bloque
    assert json.loads(bloque)["vacantes"][0]["titulo"] == fila["titulo"]


def test_banderas_legadas_salen_con_tildes(cfg):
    [v] = seleccionar([_fila(banderas="BRECHA: piden 5+ anos de experiencia || RIESGO: exigen ingles alto")], cfg)
    assert v["banderas"] == ["BRECHA: piden 5+ años de experiencia", "RIESGO: exigen inglés alto"]


def test_desde_una_corrida_real(cfg, empresas, tmp_path):
    correr(cfg, empresas, tmp_path / "vacantes.csv", tmp_path / "estado.json",
           TelegramFalso(), ahora=AHORA, fixtures=FIXTURES)
    datos = construir_datos(leer_registro(tmp_path / "vacantes.csv"), leer_estado(tmp_path / "estado.json"), cfg)
    titulos = {v["titulo"] for v in datos["vacantes"]}
    # El inventario incluye lo viejo que Telegram ya no avisa (Backblaze, julio).
    assert "AI Workflow Engineer | LATAM" in titulos
    assert datos["fuentes_total"] == 11 and len(datos["caidas"]) == 1
