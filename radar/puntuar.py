"""Puntaje determinista (capa 2a). Todo lo que se puede medir buscando texto se mide aqui.

Tres dimensiones: stack (lo que sabes hacer), seniority (distancia contra tu
nivel real) y contexto (sectores donde tus 25 anos pesan). Y tres tipos de
senal, tratadas distinto:
  KNOCKOUT -> puntaje 0
  BRECHA   -> marca, no descarta (negociable con evidencia)
  RIESGO   -> marca, no descarta (confirmar leyendo)
"""

from __future__ import annotations

import re

from .config import Config, Escala, Nivel
from .modelos import Evaluacion, Vacante
from .prefiltro import evaluar_prefiltro
from .texto import contiene, norm, terminos_presentes

# Estructura, no configuracion: como se reconoce cada nivel en un titulo.
# El ORDEN importa: se evalua de lo mas alto a lo mas bajo. "Sr. Engineer II"
# tiene dos marcas y debe ganar la mas alta; "Semi-Senior" es mid, no senior.
_NIVELES: list[tuple[str, re.Pattern[str]]] = [
    ("top", re.compile(r"\b(staff|principal|head of|director|vp|vice president|chief|cto)\b")),
    ("lead", re.compile(r"\b(lead|manager|gerente|lider|architect|arquitecto)\b")),
    ("mid", re.compile(r"\b(semi[- ]?senior|ssr|mid|mid[- ]level|intermediate)\b")),
    ("senior", re.compile(r"\b(senior|sr|iii|iv|l4|l5)\b")),
    ("mid", re.compile(r"\b(ii|l3)\b")),
    ("intern", re.compile(r"\b(intern|internship|practicante|pasante)\b")),
    ("junior", re.compile(r"\b(junior|jr|entry[- ]level|trainee|associate|early career)\b")),
]

# "2-4 years" pide 2 (el minimo del rango), no 4.
_ANOS = re.compile(
    r"(\d{1,2})(?:\s*(?:-|–|to|a)\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?|anos)\b"
    r"(?![^.]{0,40}\b(?:in business|of history|founded)\b)"
)
_INGLES = re.compile(
    r"fluent english|advanced english|english.{0,10}c[12]\b|native english|"
    r"excellent (?:written and )?(?:verbal )?english|fluency in english|"
    r"strong (?:written and verbal )?(?:communication )?(?:skills )?in english|business[- ]level english"
)
# Solo autorizacion en OTRO pais. "Authorized to work in Colombia" no es knockout.
_AUTORIZACION = re.compile(
    r"\b(?:authorized|eligible|legally able) to work in the (?:united states|us|u\.s\.|uk|united kingdom|european union|eu)\b|"
    r"\bmust be (?:a )?(?:us|u\.s\.) (?:citizen|resident|person)\b|"
    r"\bmust (?:reside|live) in the (?:united states|us|u\.s\.|uk)\b|"
    r"\bsecurity clearance\b"
)
_COMISION = re.compile(r"\b(?:commission[- ]only|solo comision)\b")
_REMOTO_EXPLICITO = re.compile(
    r"\b(?:fully remote|100% remote|remote[- ]first|work from anywhere|fully distributed)\b"
)
_PRESENCIAL_DURO = re.compile(
    r"\b(?:\d+ days? (?:per|a) week (?:in|at) the office|must (?:be able to )?relocate|"
    r"required to work on[- ]?site|on[- ]?site position|"
    r"this is (?:a |an )?(?:hybrid|on[- ]?site) (?:role|position))\b"
)
_PRESENCIAL_BLANDO = re.compile(r"\b(?:on[- ]?site|in[- ]?office|hybrid|hibrido|presencial|relocation)\b")


def nivel_del_titulo(titulo_norm: str) -> str:
    for nombre, patron in _NIVELES:
        if patron.search(titulo_norm):
            return nombre
    return "sin_marca"


def tipo_de_rol(titulo_norm: str, cfg: Config) -> str:
    terminos = cfg.puntaje.tipo_rol.automatizacion
    es_auto = any(contiene(titulo_norm, t, "plural") for t in terminos)
    return "automatizacion" if es_auto else "desarrollo"


def _stack(texto: str, cfg: Config) -> tuple[float, float]:
    """(stack 0-10, bruto). Un solo pase sobre todos los terminos: sin doble conteo entre grupos."""
    grupos = cfg.puntaje.stack
    peso_de = {}
    for grupo in (grupos.basico, grupos.solido, grupos.fuerte):  # si se repite, gana el mas fuerte
        for t in grupo.terminos:
            peso_de[t] = grupo.peso
    bruto = sum(peso_de[t] for t in terminos_presentes(texto, list(peso_de)))
    stack = min(10.0, round(bruto / cfg.puntaje.bruto_de_referencia * 10, 1))
    return stack, bruto


def puntuar(v: Vacante, cfg: Config) -> Evaluacion:
    """Evalua una vacante completa: prefiltro y, si pasa, puntaje."""
    pasa, motivo = evaluar_prefiltro(v.titulo, v.ubicacion, cfg.prefiltro)
    titulo = norm(v.titulo)
    tipo = tipo_de_rol(titulo, cfg)
    if not pasa:
        # Celda vacia no es cero: lo que no paso el prefiltro NO se puntua.
        return Evaluacion(prefiltro="no", motivo=motivo, tipo_rol=tipo)

    texto = norm(f"{v.titulo} {v.descripcion}")
    banderas: list[str] = []
    p = cfg.puntaje

    # --- STACK ---
    stack, bruto = _stack(texto, cfg)
    if stack < p.piso_stack:
        banderas.append(f"KNOCKOUT: stack {stack:.1f} bajo el piso de {p.piso_stack:.1f}")

    # --- SENIORITY: la escala depende del tipo de rol ---
    escala: Escala = getattr(p.seniority, tipo)
    nivel_nombre = nivel_del_titulo(titulo)
    nivel: Nivel = getattr(escala, nivel_nombre)
    seniority = nivel.puntos
    if nivel.knockout:
        seniority = 0
        banderas.append(f"KNOCKOUT: seniority '{nivel_nombre}' fuera de alcance en rol de {tipo}")
    elif nivel.brecha:
        banderas.append(f"BRECHA: titulo '{nivel_nombre}' en rol de {tipo}")

    # --- CONTEXTO DE NEGOCIO ---
    sectores = terminos_presentes(texto, p.sectores)
    contexto = min(10.0, len(sectores) * p.puntos_por_sector)

    # --- ANOS PEDIDOS: el minimo de todas las apariciones ---
    pedidos = [int(n) for n in _ANOS.findall(texto) if 0 < int(n) <= 20]
    if pedidos and min(pedidos) > cfg.perfil.anos_dev:
        banderas.append(f"BRECHA: piden {min(pedidos)}+ anos de experiencia")

    # --- INGLES: riesgo de entrevista, nunca descarta ---
    if _INGLES.search(texto):
        banderas.append("RIESGO: exigen ingles alto")

    # --- KNOCKOUTS DUROS ---
    if _AUTORIZACION.search(texto):
        banderas.append("KNOCKOUT: exige autorizacion laboral en otro pais")
    if _COMISION.search(texto):
        banderas.append("KNOCKOUT: pago solo por comision")

    # --- PRESENCIALIDAD ---
    en_mi_ciudad = contiene(norm(v.ubicacion), cfg.perfil.ciudad_base)
    remoto = bool(_REMOTO_EXPLICITO.search(texto))
    if not en_mi_ciudad and not remoto:
        if _PRESENCIAL_DURO.search(texto):
            banderas.append("KNOCKOUT: presencial o hibrido exigido")
        elif _PRESENCIAL_BLANDO.search(texto):
            banderas.append("RIESGO: menciona presencial/hibrido, confirmar")

    knockout = any(b.startswith("KNOCKOUT") for b in banderas)
    puntaje = 0.0 if knockout else round(
        stack * p.pesos.stack + seniority * p.pesos.seniority + contexto * p.pesos.contexto, 1
    )
    return Evaluacion(
        prefiltro="si",
        motivo=motivo,
        tipo_rol=tipo,
        puntaje=puntaje,
        desglose=(
            f"stack {stack:.1f} (bruto {bruto:g}) | seniority {seniority:g} "
            f"({nivel_nombre}, {tipo}) | contexto {contexto:g}"
        ),
        banderas=banderas,
    )
