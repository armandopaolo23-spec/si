"""Pruebas del modelo de pista. Todo con diccionarios, sin tocar disco.

La excepcion es test_las_pistas_de_ejemplo_son_validas, que carga los .json
que se entregan: si alguno se rompe al editarlo, la prueba lo dice.
"""

import glob
import json

import pytest

from audio.notas import CUERDAS_ESTANDAR, nombre_midi
from nucleo.pista import (MIDI_MAXIMO, MIDI_MINIMO, EventoAcorde, EventoNota,
                          Pista, PistaInvalida, cargar, desde_dict)


def pista_minima(**cambios):
    """Una pista valida a la que cada prueba le rompe una sola cosa."""
    datos = {
        "titulo": "prueba",
        "bpm": 60,
        "afinacion": ["E2", "A2", "D3", "G3", "B3", "E4"],
        "eventos": [
            {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 40,
             "cuerda": 6, "traste": 0},
        ],
    }
    datos.update(cambios)
    return datos


def errores_de(datos):
    with pytest.raises(PistaInvalida) as excepcion:
        desde_dict(datos)
    return excepcion.value.errores


# --------------------------------------------------------------- lo que pasa

def test_pista_minima_valida():
    pista = desde_dict(pista_minima())
    assert pista.titulo == "prueba"
    assert pista.bpm == 60.0
    assert pista.afinacion == CUERDAS_ESTANDAR
    assert pista.eventos == (
        EventoNota(t=0.0, dur=1.0, midi=40, cuerda=6, traste=0),)


def test_afinacion_por_defecto_es_la_estandar():
    datos = pista_minima()
    del datos["afinacion"]
    assert desde_dict(datos).afinacion == CUERDAS_ESTANDAR


def test_digitacion_es_opcional():
    pista = desde_dict(pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 40}]))
    evento = pista.eventos[0]
    assert (evento.cuerda, evento.traste) == (None, None)


def test_acorde_se_ordena_y_se_quitan_repetidas():
    """Para acertar un acorde importa el conjunto de pitches, no el orden.

    La misma nota puede caer en dos cuerdas distintas, y eso no la hace una
    exigencia doble.
    """
    pista = desde_dict(pista_minima(eventos=[
        {"t": 0.0, "dur": 2.0, "tipo": "acorde", "nombre": "Em",
         "notas": [64, 40, 52, 40, 47]}]))
    assert pista.eventos[0] == EventoAcorde(
        t=0.0, dur=2.0, nombre="Em", notas=(40, 47, 52, 64))


def test_midis_unifica_notas_y_acordes():
    """Es lo que va a consumir el evaluador de la fase 3."""
    nota, acorde = desde_dict(pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 40},
        {"t": 1.0, "dur": 1.0, "tipo": "acorde", "nombre": "Em",
         "notas": [40, 47]},
    ])).eventos
    assert nota.midis == (40,)
    assert acorde.midis == (40, 47)


def test_duracion_y_pulso():
    pista = desde_dict(pista_minima(bpm=120, eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 40},
        {"t": 3.0, "dur": 0.5, "tipo": "nota", "midi": 45},
    ]))
    assert pista.duracion == 3.5
    assert pista.pulso(0.0) == 0.0
    assert pista.pulso(2.0) == 4.0     # a 120 bpm, 2 s son 4 pulsos


def test_la_duracion_puede_pisar_el_evento_siguiente():
    """Una cuerda sigue sonando mientras se toca la que viene: es valido."""
    pista = desde_dict(pista_minima(eventos=[
        {"t": 0.0, "dur": 4.0, "tipo": "nota", "midi": 40},
        {"t": 0.5, "dur": 4.0, "tipo": "nota", "midi": 45},
    ]))
    assert len(pista.eventos) == 2


def test_afinacion_no_estandar_cambia_la_coherencia_de_digitacion():
    """Con la 6a en D2 (drop D), traste 0 de la 6a ya no es E2."""
    datos = pista_minima(
        afinacion=["D2", "A2", "D3", "G3", "B3", "E4"],
        eventos=[{"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 38,
                  "cuerda": 6, "traste": 0}])
    assert desde_dict(datos).eventos[0].midi == 38
    # El mismo evento con midi 40 ahora es incoherente.
    datos["eventos"][0]["midi"] = 40
    assert any("digitacion sugerida" in e for e in errores_de(datos))


# ------------------------------------------------------------ lo que falla

@pytest.mark.parametrize("titulo", [None, "", "   ", 42, []])
def test_titulo_invalido(titulo):
    assert any("titulo" in e for e in errores_de(pista_minima(titulo=titulo)))


@pytest.mark.parametrize("bpm", [None, 0, -60, "60", True, []])
def test_bpm_invalido(bpm):
    assert any("bpm" in e for e in errores_de(pista_minima(bpm=bpm)))


def test_eventos_vacios_o_ausentes():
    assert any("eventos" in e for e in errores_de(pista_minima(eventos=[])))
    datos = pista_minima()
    del datos["eventos"]
    assert any("eventos" in e for e in errores_de(datos))


@pytest.mark.parametrize("afinacion", [
    ["E2", "A2"],                                    # faltan cuerdas
    ["E2", "A2", "D3", "G3", "B3", "E4", "A4"],      # sobra una
    ["E2", "A2", "D3", "G3", "B3", "H4"],            # nombre inventado
    "E2 A2 D3 G3 B3 E4",                             # no es lista
])
def test_afinacion_invalida(afinacion):
    assert any("afinacion" in e
               for e in errores_de(pista_minima(afinacion=afinacion)))


@pytest.mark.parametrize("tipo", [None, "silencio", "NOTA", 1])
def test_tipo_de_evento_invalido(tipo):
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": tipo, "midi": 40}])
    assert any("tipo" in e for e in errores_de(datos))


@pytest.mark.parametrize("t", [None, -1.0, "0", True])
def test_t_invalido(t):
    datos = pista_minima(eventos=[
        {"t": t, "dur": 1.0, "tipo": "nota", "midi": 40}])
    assert any("'t'" in e for e in errores_de(datos))


@pytest.mark.parametrize("dur", [None, 0, -1.0, "1", True])
def test_dur_invalido(dur):
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": dur, "tipo": "nota", "midi": 40}])
    assert any("'dur'" in e for e in errores_de(datos))


@pytest.mark.parametrize("midi", [None, "64", 64.5, True, []])
def test_midi_no_entero(midi):
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": midi}])
    assert any("MIDI entero" in e for e in errores_de(datos))


@pytest.mark.parametrize("midi", [MIDI_MINIMO - 1, MIDI_MAXIMO + 1, 0, 127])
def test_midi_fuera_del_alcance_del_detector(midi):
    """Una nota que el detector no puede oir haria la pista imposible."""
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": midi}])
    assert any("fuera de lo que el detector puede oir" in e
               for e in errores_de(datos))


@pytest.mark.parametrize("midi", [MIDI_MINIMO, MIDI_MAXIMO])
def test_los_extremos_del_rango_si_se_aceptan(midi):
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": midi}])
    assert desde_dict(datos).eventos[0].midi == midi


@pytest.mark.parametrize("cuerda", [0, 7, -1, 1.5, "1"])
def test_cuerda_invalida(cuerda):
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 40, "cuerda": cuerda}])
    assert any("cuerda" in e for e in errores_de(datos))


@pytest.mark.parametrize("traste", [-1, 25, 1.5, "0"])
def test_traste_invalido(traste):
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 40, "traste": traste}])
    assert any("traste" in e for e in errores_de(datos))


def test_digitacion_que_no_da_el_pitch_pedido():
    datos = pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 64,
         "cuerda": 1, "traste": 5}])
    errores = errores_de(datos)
    assert any("digitacion sugerida" in e for e in errores)
    assert any("A4" in e and "E4" in e for e in errores)


def test_acorde_sin_nombre_o_con_muy_pocas_notas():
    assert any("nombre" in e for e in errores_de(pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "acorde", "notas": [40, 47]}])))
    assert any("al menos" in e for e in errores_de(pista_minima(eventos=[
        {"t": 0.0, "dur": 1.0, "tipo": "acorde", "nombre": "E", "notas": [40]}])))


def test_dos_eventos_en_el_mismo_instante():
    datos = pista_minima(eventos=[
        {"t": 1.0, "dur": 1.0, "tipo": "nota", "midi": 40},
        {"t": 1.0, "dur": 1.0, "tipo": "nota", "midi": 47},
    ])
    assert any("son un acorde" in e for e in errores_de(datos))


def test_eventos_desordenados():
    datos = pista_minima(eventos=[
        {"t": 2.0, "dur": 1.0, "tipo": "nota", "midi": 40},
        {"t": 1.0, "dur": 1.0, "tipo": "nota", "midi": 47},
    ])
    assert any("ordenados" in e for e in errores_de(datos))


def test_la_pista_no_es_un_objeto():
    for datos in ([], "hola", 42, None):
        assert any("objeto JSON" in e for e in errores_de(datos))


def test_informa_todos_los_errores_de_una_vez():
    """Corregir de uno en uno es lo que hace odiosa una validacion."""
    datos = {
        "titulo": "",
        "bpm": -1,
        "afinacion": ["E2", "A2"],
        "eventos": [
            {"t": -1.0, "dur": 0, "tipo": "nota", "midi": 999},
            {"t": 0.0, "dur": 1.0, "tipo": "acorde", "notas": []},
        ],
    }
    errores = errores_de(datos)
    assert len(errores) >= 6, errores


# ------------------------------------------------------------------ archivos

def test_json_mal_formado_dice_donde():
    with pytest.raises(PistaInvalida) as excepcion:
        cargar(__file__)     # un .py no es JSON valido
    assert any("linea" in e for e in excepcion.value.errores)


def test_archivo_que_no_existe():
    with pytest.raises(PistaInvalida) as excepcion:
        cargar("pistas/no_existe_esta_pista.json")
    assert any("no se pudo leer" in e for e in excepcion.value.errores)


@pytest.mark.parametrize("ruta", sorted(glob.glob("pistas/*.json")))
def test_las_pistas_de_ejemplo_son_validas(ruta):
    pista = cargar(ruta)
    assert pista.eventos
    assert pista.duracion > 0


def test_hay_tres_pistas_de_ejemplo_de_dificultad_creciente():
    rutas = sorted(glob.glob("pistas/*.json"))
    assert len(rutas) == 3
    pistas = [cargar(ruta) for ruta in rutas]
    # Mas bpm y mas eventos a medida que avanzan.
    assert [p.bpm for p in pistas] == sorted(p.bpm for p in pistas)
    assert [len(p.eventos) for p in pistas] == \
        sorted(len(p.eventos) for p in pistas)
    # Solo la ultima tiene acordes.
    con_acordes = [any(e.tipo == "acorde" for e in p.eventos) for p in pistas]
    assert con_acordes == [False, False, True]


def test_una_afinacion_invalida_no_inventa_errores_de_digitacion():
    """Con la afinacion rota se usa la estandar de respaldo.

    Comparar la digitacion contra ese respaldo reportaria errores que la
    pista no tiene, y taparia el error real, que es la afinacion.
    """
    datos = pista_minima(
        afinacion=["E2", "A2"],
        eventos=[{"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 64,
                  "cuerda": 1, "traste": 7}])
    errores = errores_de(datos)
    assert any("afinacion" in e for e in errores)
    assert not any("digitacion sugerida" in e for e in errores)
