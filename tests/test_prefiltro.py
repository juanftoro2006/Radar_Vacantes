import pytest

from radar.prefiltro import clasificar_ubicacion, evaluar_prefiltro


@pytest.mark.parametrize("ubicacion, esperado", [
    ("Bogota D.C. / DC / Colombia", "fuerte"),
    ("Remote - Argentina; Remote - Colombia ; Remote - Mexico", "fuerte"),
    ("LATAM (Remote), US (Remote)", "fuerte"),
    ("Latin America", "fuerte"),
    ("Medellín, Antioquia", "fuerte"),
    ("Remote", "remoto"),
    ("Remote, Global", "remoto"),
    ("Remote-AMER", "remoto"),
    ("Home Based - Americas", "remoto"),
    ("Home based - Worldwide", "remoto"),
    ("sin especificar", "remoto"),
    # Los agujeros de la lista negra de la v1: todos pasaban como "remoto sin pais".
    ("Sweden (Remote)", "fuera"),
    ("Remote, Singapore", "fuera"),
    ("Remote, APAC", "fuera"),
    ("Remote North America", "fuera"),
    ("Chicago or Remote*", "fuera"),
    ("Remote or Hybrid UK", "fuera"),
    ("Argentina Remote", "fuera"),
    ("Remote - US", "fuera"),
    ("Mexico City / CDMX / Mexico", "fuera"),
])
def test_clasificar_ubicacion(cfg, ubicacion, esperado):
    assert clasificar_ubicacion(ubicacion, cfg.prefiltro) == esperado


def test_titulo_fuera_de_perfil(cfg):
    pasa, motivo = evaluar_prefiltro("Payroll Specialist", "Colombia", cfg.prefiltro)
    assert not pasa and motivo == "titulo fuera de perfil"


def test_motivo_siempre_explica(cfg):
    pasa, motivo = evaluar_prefiltro("Backend Engineer", "Remote", cfg.prefiltro)
    assert pasa and "remoto sin pais" in motivo
