from radar.texto import contiene_titulo, limpiar_html, norm, terminos_presentes


def test_norm_quita_tildes_y_mayusculas():
    assert norm("Medellín BOGOTÁ") == "medellin bogota"


def test_limpiar_html_desescapa_doble_como_greenhouse():
    crudo = "&lt;p&gt;Python &amp;amp; APIs&amp;nbsp;&lt;/p&gt;"
    assert limpiar_html(crudo) == "Python & APIs"


def test_limpiar_html_no_recorta():
    # Bug raiz de la v1: se cortaba a 3500 caracteres antes de puntuar.
    largo = "<p>" + "relleno " * 1000 + "n8n</p>"
    assert limpiar_html(largo).endswith("n8n")


def test_siglas_estrictas_en_titulos():
    assert contiene_titulo("ai engineer", "ai")
    assert not contiene_titulo("chair designer", "ai")
    assert not contiene_titulo("html developer", "ml")


def test_raices_abiertas_en_titulos():
    # Con limite estricto 'engineer' no pegaba en 'Engineering'.
    assert contiene_titulo("data engineering lead", "engineer")
    assert contiene_titulo("integrations specialist", "integration")


def test_sin_doble_conteo():
    texto = norm("We use REST API design and Node.js services")
    encontrados = terminos_presentes(texto, ["rest api", "api", "node.js", "node"])
    assert sorted(encontrados) == ["node.js", "rest api"]


def test_api_independiente_si_cuenta():
    texto = norm("REST API design. Also public APIs for partners.")
    assert sorted(terminos_presentes(texto, ["rest api", "api"])) == ["api", "rest api"]


def test_plurales_cuentan():
    assert terminos_presentes("we build webhooks and integrations", ["webhook", "integration"]) == [
        "integration", "webhook",
    ]


def test_api_no_pega_en_therapist():
    assert terminos_presentes("physical therapist", ["api"]) == []
