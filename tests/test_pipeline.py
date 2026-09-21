"""Pruebas de punta a punta: fixtures -> registro -> avisos, sin red."""

from datetime import timedelta

from radar.pipeline import correr
from radar.registro import leer_estado, leer_registro
from radar.telegram import interpretar

from .conftest import AHORA, FIXTURES, TelegramFalso


def _correr(cfg, empresas, tmp_path, tg, ahora=AHORA, fixtures=FIXTURES):
    return correr(cfg, empresas, tmp_path / "vacantes.csv", tmp_path / "estado.json",
                  tg, ahora=ahora, fixtures=fixtures)


def test_primera_corrida_avisa_solo_lo_fresco(cfg, empresas, tmp_path):
    tg = TelegramFalso()
    res = _correr(cfg, empresas, tmp_path, tg)
    titulos = {f["titulo"] for f in res.avisadas}
    assert "AI Growth Automation Engineer - Bogotá (Hybrid)" in titulos
    # Backblaze se publico en julio: se registra, pero no se avisa (ventana de 7 dias).
    assert "AI Workflow Engineer | LATAM" not in titulos
    registro = leer_registro(tmp_path / "vacantes.csv")
    assert any(f["titulo"] == "AI Workflow Engineer | LATAM" for f in registro)


def test_se_guarda_todo_incluso_lo_descartado(cfg, empresas, tmp_path):
    res = _correr(cfg, empresas, tmp_path, TelegramFalso())
    registro = leer_registro(tmp_path / "vacantes.csv")
    assert len(registro) == res.revisadas
    fuera = [f for f in registro if f["prefiltro"] == "no"]
    assert fuera and all(f["motivo"] and f["puntaje"] == "" for f in fuera)


def test_misma_vacante_en_dos_ciudades_avisa_una(cfg, empresas, tmp_path):
    res = _correr(cfg, empresas, tmp_path, TelegramFalso())
    fraude = [f for f in res.avisadas if f["titulo"] == "Fraud Automation Analyst"]
    assert len(fraude) == 1 and res.duplicadas == 1


def test_segunda_corrida_no_repite_avisos(cfg, empresas, tmp_path):
    _correr(cfg, empresas, tmp_path, TelegramFalso())
    res = _correr(cfg, empresas, tmp_path, TelegramFalso(), ahora=AHORA + timedelta(hours=5))
    assert res.nuevas == 0 and res.avisadas == []


def test_envio_fallido_se_reintenta(cfg, empresas, tmp_path):
    res1 = _correr(cfg, empresas, tmp_path, TelegramFalso(falla_envio=True))
    assert res1.errores and res1.avisadas
    res2 = _correr(cfg, empresas, tmp_path, TelegramFalso(), ahora=AHORA + timedelta(hours=5))
    assert {f["clave"] for f in res2.avisadas} == {f["clave"] for f in res1.avisadas}


def test_visto_saca_de_pendientes(cfg, empresas, tmp_path):
    res1 = _correr(cfg, empresas, tmp_path, TelegramFalso())
    n = res1.avisadas[0]["n"]
    tg = TelegramFalso(entrada=[f"/visto {n}", "/pendientes"])
    res2 = _correr(cfg, empresas, tmp_path, tg, ahora=AHORA + timedelta(hours=5))
    assert f"#{n} marcada como vista" in res2.comandos
    resumen = tg.enviados[-1]
    assert f"#{n} ·" not in resumen


def test_resumen_una_vez_al_dia_y_reporta_caidas(cfg, empresas, tmp_path):
    tg1 = TelegramFalso()
    _correr(cfg, empresas, tmp_path, tg1)
    assert any("Radar" in m and "Bitso" in m for m in tg1.enviados)
    tg2 = TelegramFalso()
    _correr(cfg, empresas, tmp_path, tg2, ahora=AHORA + timedelta(hours=5))
    assert not any("Radar" in m for m in tg2.enviados)       # mismo dia: no repite
    assert leer_estado(tmp_path / "estado.json")["fuentes"]["bitso"]["ok"] is False


def test_vacante_que_desaparece_se_marca_cerrada(cfg, empresas, tmp_path):
    _correr(cfg, empresas, tmp_path, TelegramFalso())
    solo_clara = tmp_path / "fx"
    solo_clara.mkdir()
    datos = (FIXTURES / "greenhouse_clara.json").read_text(encoding="utf-8")
    import json
    d = json.loads(datos)
    d["jobs"] = d["jobs"][:1]                    # la segunda vacante de Clara ya no esta
    (solo_clara / "greenhouse_clara.json").write_text(json.dumps(d), encoding="utf-8")
    clara = [e for e in empresas if e.token == "clara"]
    res = _correr(cfg, clara, tmp_path, TelegramFalso(), ahora=AHORA + timedelta(days=1), fixtures=solo_clara)
    assert res.cerradas == 1
    registro = leer_registro(tmp_path / "vacantes.csv")
    # Solo se cierran vacantes de fuentes que respondieron: Sezzle no se consulto.
    assert all(not f["cerrada"] for f in registro if f["token"] == "sezzle")


def test_sin_telegram_no_marca_notificada(cfg, empresas, tmp_path):
    res = _correr(cfg, empresas, tmp_path, None)
    assert res.avisadas
    assert all(not f["notificada"] for f in leer_registro(tmp_path / "vacantes.csv"))


def test_interpretar_comandos():
    assert interpretar("/visto 12, 15 20") == ("visto", [12, 15, 20])
    assert interpretar("/pendientes") == ("pendientes", [])
    assert interpretar("hola") is None
