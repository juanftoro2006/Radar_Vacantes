import pytest

from radar.puntuar import nivel_del_titulo, puntuar, tipo_de_rol
from radar.texto import norm

from .conftest import vacante

STACK_BUENO = (
    "n8n, Zapier, Python, JavaScript, REST APIs, webhooks, LLM APIs (OpenAI, Anthropic), "
    "prompt engineering, ETL and agents. "
)


@pytest.mark.parametrize("titulo, nivel", [
    ("Sr. Software Engineer II", "senior"),      # v1 lo daba como mid por el orden del else-if
    ("Software Engineer II", "mid"),
    ("Semi-Senior Python Developer", "mid"),     # contiene 'senior' pero no lo es
    ("Staff Engineer", "top"),
    ("Engineering Manager", "lead"),
    ("Solutions Architect", "lead"),
    ("Junior Data Engineer", "junior"),
    ("Security Engineer (Early Career)", "junior"),
    ("Data Engineering Intern", "intern"),
    ("Automation Engineer", "sin_marca"),
])
def test_nivel_del_titulo(titulo, nivel):
    assert nivel_del_titulo(norm(titulo)) == nivel


@pytest.mark.parametrize("titulo, tipo", [
    ("Automation Engineer", "automatizacion"),
    ("Integrations Engineer", "automatizacion"),
    ("HR AI & Automation Operations Lead", "automatizacion"),
    ("Backend Engineer", "desarrollo"),
    ("DevOps Engineer", "desarrollo"),   # 'ops' suelto si, 'devops' no
])
def test_tipo_de_rol(cfg, titulo, tipo):
    assert tipo_de_rol(norm(titulo), cfg) == tipo


def test_senior_en_automatizacion_compite(cfg):
    ev = puntuar(vacante("Senior Automation Engineer", STACK_BUENO), cfg)
    assert not ev.knockout and ev.puntaje >= cfg.puntaje.umbral
    assert "BRECHA" not in " ".join(ev.banderas)


def test_senior_en_desarrollo_es_brecha_no_knockout(cfg):
    ev = puntuar(vacante("Senior Backend Engineer", STACK_BUENO), cfg)
    assert not ev.knockout
    assert any(b.startswith("BRECHA: titulo 'senior'") for b in ev.banderas)


def test_lead_en_desarrollo_es_knockout(cfg):
    ev = puntuar(vacante("Engineering Lead", STACK_BUENO), cfg)
    assert ev.knockout and ev.puntaje == 0


def test_lead_en_automatizacion_es_brecha(cfg):
    ev = puntuar(vacante("Automation Operations Lead", STACK_BUENO), cfg)
    assert not ev.knockout
    assert any("BRECHA: titulo 'lead'" in b for b in ev.banderas)


def test_piso_de_stack_deja_bandera(cfg):
    ev = puntuar(vacante("Junior Data Scientist", "scikit-learn, tensorflow, fintech payments"), cfg)
    assert ev.knockout and ev.puntaje == 0
    assert any("bajo el piso" in b for b in ev.banderas)


def test_descripcion_larga_si_se_lee_completa(cfg):
    # Regresion del bug de 3500 caracteres: los requisitos van al final.
    relleno = "About us: we are a great company with great values. " * 90   # ~4800 caracteres
    ev = puntuar(vacante("Automation Engineer", relleno + STACK_BUENO), cfg)
    assert ev.puntaje >= cfg.puntaje.umbral


def test_autorizacion_en_colombia_no_es_knockout(cfg):
    ev = puntuar(vacante("Integration Developer",
                         STACK_BUENO + "You must be authorized to work in Colombia."), cfg)
    assert not ev.knockout


def test_autorizacion_en_eeuu_si_es_knockout(cfg):
    ev = puntuar(vacante("Integration Developer",
                         STACK_BUENO + "Must be authorized to work in the United States."), cfg)
    assert ev.knockout


def test_rango_de_anos_toma_el_minimo(cfg):
    ev = puntuar(vacante("Automation Engineer", STACK_BUENO + "2-4 years of experience."), cfg)
    assert not any(b.startswith("BRECHA: piden") for b in ev.banderas)


def test_hibrido_en_mi_ciudad_no_marca(cfg):
    texto = STACK_BUENO + "This is a hybrid role."
    en_medellin = puntuar(vacante("Automation Engineer", texto, ubicacion="Medellin, Colombia"), cfg)
    en_bogota = puntuar(vacante("Automation Engineer", texto, ubicacion="Bogota, Colombia"), cfg)
    assert not en_medellin.knockout
    assert en_bogota.knockout


def test_lo_que_no_pasa_el_prefiltro_no_se_puntua(cfg):
    ev = puntuar(vacante("Payroll Specialist", STACK_BUENO), cfg)
    assert ev.prefiltro == "no" and ev.puntaje is None   # vacio, no cero
