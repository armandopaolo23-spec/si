"""Pruebas del generador de pistas. Funciones puras: diccionarios, sin disco.

La de integracion toca cada pista generada con detecciones perfectas y
comprueba que el evaluador acierte todo: generar algo que el juego no pueda
calificar seria peor que no generarlo.
"""

import pytest

from audio.notas import nombre_a_midi
from juego.geometria import VENTANA_VISTA_S
from nucleo.acordes import ACORDES_ABIERTOS
from nucleo.evaluador import Evaluador
from nucleo.generador import (ESCALAS, a_json, clase_de_tono, escala,
                              progresion)
from nucleo.pista import advertencias_de_ritmo, cargar, desde_dict
from nucleo.simulacion import PERFILES, generar_detecciones, reproducir


def midis(datos):
    return [e["midi"] for e in datos["eventos"]]


# ---------------------------------------------------------------- tonicas

@pytest.mark.parametrize("tono, clase", [
    ("C", 0), ("D", 2), ("E", 4), ("F", 5), ("G", 7), ("A", 9), ("B", 11),
    ("F#", 6), ("Bb", 10), ("c", 0), ("g", 7),
    ("Do", 0), ("Re", 2), ("Mi", 4), ("Fa", 5), ("Sol", 7), ("La", 9),
    ("Si", 11), ("sol", 7), ("Fa#", 6), ("Sib", 10), ("  La ", 9),
])
def test_clase_de_tono_acepta_notacion_inglesa_y_latina(tono, clase):
    assert clase_de_tono(tono) == clase


@pytest.mark.parametrize("tono", ["", "H", "Xa", "Sol##x", None, "#"])
def test_clase_de_tono_rechaza_lo_que_no_entiende(tono):
    with pytest.raises(ValueError):
        clase_de_tono(tono)


# ----------------------------------------------------------------- escalas

def test_do_mayor_sale_igual_al_ejercicio_2_escrito_a_mano():
    """La escala generada coincide nota por nota y pulso por pulso con la
    pista escrita a mano: el generador hace lo mismo que se haria a mano."""
    generada = escala("C", "mayor")
    escrita = cargar("pistas/02_escala_do_mayor.json")
    assert midis(generada) == [e.midi for e in escrita.eventos]
    assert [e["t"] for e in generada["eventos"]] == \
        [e.t for e in escrita.eventos]


@pytest.mark.parametrize("tipo", sorted(ESCALAS))
def test_cada_tipo_de_escala_sube_y_baja(tipo):
    datos = escala("A", tipo)
    notas = midis(datos)
    arriba = notas.index(max(notas))
    assert notas[:arriba + 1] == sorted(notas[:arriba + 1])
    assert notas[arriba:] == sorted(notas[arriba:], reverse=True)
    assert notas[0] == notas[-1]
    assert max(notas) - min(notas) == 12


@pytest.mark.parametrize("tipo, intervalos", sorted(ESCALAS.items()))
def test_los_intervalos_de_cada_escala(tipo, intervalos):
    notas = midis(escala("C", tipo))
    tonica = notas[0]
    subida = notas[:len(intervalos)]
    assert [n - tonica for n in subida] == list(intervalos)


@pytest.mark.parametrize("tono, tonica", [
    ("E", "E2"), ("F", "F2"), ("G", "G2"), ("A", "A2"), ("B", "B2"),
    ("C", "C3"), ("D", "D3"),
])
def test_la_tonica_queda_en_primera_posicion(tono, tonica):
    """Desde la 6a al aire hacia arriba: nada que la guitarra no alcance."""
    assert midis(escala(tono))[0] == nombre_a_midi(tonica)


def test_dos_octavas():
    notas = midis(escala("G", "mayor", octavas=2))
    assert max(notas) - min(notas) == 24
    assert len(notas) == 2 * (7 * 2) + 1


def test_la_nota_de_arriba_deja_aire_y_la_ultima_suena_larga():
    eventos = escala("C")["eventos"]
    arriba = max(range(len(eventos)), key=lambda i: eventos[i]["midi"])
    assert eventos[arriba + 1]["t"] - eventos[arriba]["t"] == 2.0
    assert eventos[-1]["dur"] > eventos[0]["dur"]


def test_el_bpm_escala_los_tiempos():
    lenta = escala("C", bpm=60)["eventos"]
    rapida = escala("C", bpm=120)["eventos"]
    assert [e["t"] / 2 for e in lenta] == [e["t"] for e in rapida]


@pytest.mark.parametrize("argumentos", [
    {"tono": "C", "tipo": "dorica"},
    {"tono": "C", "octavas": 3},
    {"tono": "C", "bpm": 0},
    {"tono": "H"},
])
def test_escala_con_parametros_invalidos(argumentos):
    with pytest.raises(ValueError):
        escala(**argumentos)


# ------------------------------------------------------------- progresiones

def test_progresion_resuelve_en_el_primer_acorde():
    datos = progresion(["G", "D", "Em", "C"])
    nombres = [e["nombre"] for e in datos["eventos"]]
    assert nombres == ["G", "D", "Em", "C", "G"]


def test_progresion_con_vueltas():
    nombres = [e["nombre"] for e in progresion(["Am", "C"], vueltas=3)["eventos"]]
    assert nombres == ["Am", "C"] * 3 + ["Am"]


def test_progresion_usa_las_notas_de_la_plantilla():
    """Las mismas que reconoce el detector: si no, no se podria acertar."""
    for evento in progresion(list(ACORDES_ABIERTOS))["eventos"]:
        assert tuple(evento["notas"]) == ACORDES_ABIERTOS[evento["nombre"]]


def test_progresion_con_acorde_sin_plantilla_dice_cuales_hay():
    with pytest.raises(ValueError) as excepcion:
        progresion(["G", "F", "C"])
    mensaje = str(excepcion.value)
    assert "F" in mensaje
    for nombre in ACORDES_ABIERTOS:
        assert nombre in mensaje


@pytest.mark.parametrize("argumentos", [
    {"acordes": []},
    {"acordes": ["G"], "vueltas": 0},
    {"acordes": ["G"], "pulsos_por_acorde": 1},
    {"acordes": ["G"], "bpm": -60},
])
def test_progresion_con_parametros_invalidos(argumentos):
    with pytest.raises(ValueError):
        progresion(**argumentos)


# ------------------------------------------------------- ritmo y validacion

@pytest.mark.parametrize("datos", [
    escala("C"), escala("G", octavas=2), escala("E", "pentatonica_menor"),
    progresion(["G", "D", "Em", "C"]), progresion(["Am", "C", "G"], vueltas=2),
], ids=["do", "sol-2oct", "mi-penta", "g-d-em-c", "am-c-g-x2"])
def test_con_los_valores_por_defecto_respeta_el_ritmo_para_principiantes(datos):
    pista = desde_dict(datos)
    assert advertencias_de_ritmo(pista, VENTANA_VISTA_S) == []


def test_mas_rapido_sigue_siendo_valida_pero_avisa():
    """Mas rapido es una eleccion, no un error: se genera y se avisa."""
    pista = desde_dict(progresion(["Am", "C"], bpm=90, pulsos_por_acorde=4))
    assert advertencias_de_ritmo(pista, VENTANA_VISTA_S)


def test_un_acorde_seguido_de_otro_no_se_avisa_dos_veces():
    """La regla entre acordes ya cubre el caso y es mas exigente."""
    pista = desde_dict(progresion(["Am", "C"], bpm=90, pulsos_por_acorde=4))
    avisos = advertencias_de_ritmo(pista, VENTANA_VISTA_S)
    assert not any("soltar" in aviso for aviso in avisos)


# ---------------------------------------------------------------- formato

def test_el_json_tiene_un_evento_por_linea_y_vuelve_a_cargar(tmp_path):
    datos = progresion(["Em", "C"])
    texto = a_json(datos)
    lineas_de_eventos = [l for l in texto.splitlines() if '"tipo"' in l]
    assert len(lineas_de_eventos) == len(datos["eventos"])

    ruta = tmp_path / "pista.json"
    ruta.write_text(texto, encoding="utf-8")
    assert len(cargar(ruta).eventos) == len(datos["eventos"])


# ------------------------------------------------------- de punta a punta

@pytest.mark.parametrize("datos", [
    escala("C"), escala("A", "pentatonica_menor", octavas=2),
    progresion(["G", "D", "Em", "C"]), progresion(list(ACORDES_ABIERTOS)),
], ids=["do", "la-penta-2oct", "g-d-em-c", "todos-los-acordes"])
def test_una_pista_generada_tocada_perfecta_acierta_todo(datos):
    pista = desde_dict(datos)
    evaluador = Evaluador(pista)
    detecciones = generar_detecciones(pista, PERFILES["perfecto"])
    reproducir(evaluador, detecciones, pista.duracion)
    resumen = evaluador.resumen
    assert resumen.aciertos == resumen.total
    assert resumen.fallos == 0
    assert resumen.extras == 0
