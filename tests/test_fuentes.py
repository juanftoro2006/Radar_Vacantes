from radar.fuentes import descargar

from .conftest import FIXTURES


def test_fuente_caida_se_reporta_no_se_calla(empresas):
    _, reportes = descargar(empresas, fixtures=FIXTURES)
    bitso = next(r for r in reportes if r.token == "bitso")
    assert not bitso.ok and bitso.detalle


def test_normaliza_los_tres_ats(empresas):
    vacantes, _ = descargar(empresas, fixtures=FIXTURES)
    fuentes = {v.fuente for v in vacantes}
    assert fuentes == {"greenhouse", "lever", "ashby"}
    for v in vacantes:
        assert v.titulo and v.url and v.id_externo
        assert v.publicada is None or v.publicada[:4] == "2026"   # nunca ""


def test_greenhouse_descripcion_completa_y_limpia(empresas):
    vacantes, _ = descargar(empresas, fixtures=FIXTURES)
    clara = next(v for v in vacantes if v.id_externo == "900001")
    assert "<p>" not in clara.descripcion and "&lt;" not in clara.descripcion
    assert len(clara.descripcion) > 3500 and "n8n" in clara.descripcion


def test_lever_incluye_requisitos_de_lists(empresas):
    vacantes, _ = descargar(empresas, fixtures=FIXTURES)
    yuno = next(v for v in vacantes if v.fuente == "lever")
    assert "LLM APIs" in yuno.descripcion           # vive en 'lists', no en descriptionPlain
    assert yuno.publicada.startswith("2026-09-21")  # epoch ms -> ISO
    assert "Bogota" in yuno.ubicacion and "Colombia" in yuno.ubicacion
