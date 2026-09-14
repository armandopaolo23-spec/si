"""Pruebas de la disposicion del highway. Geometria pura, sin ventana."""

import pytest

from audio.notas import CUERDAS_ESTANDAR, nombre_a_midi
from juego.geometria import (MARGEN_SALIDA_S, VENTANA_VISTA_S,
                             carril_de_nota, carriles_de_evento, en_vista,
                             indice_carril, posicion_relativa)
from nucleo.pista import desde_dict


def test_posicion_relativa_en_los_extremos():
    assert posicion_relativa(VENTANA_VISTA_S) == pytest.approx(0.0)
    assert posicion_relativa(0.0) == pytest.approx(1.0)
    assert posicion_relativa(VENTANA_VISTA_S / 2) == pytest.approx(0.5)


def test_posicion_relativa_pasada_la_linea():
    assert posicion_relativa(-0.3) > 1.0


def test_posicion_relativa_es_monotona():
    """Una nota que se acerca en el tiempo tiene que bajar en pantalla."""
    posiciones = [posicion_relativa(r) for r in (3.0, 2.0, 1.0, 0.5, 0.0, -0.4)]
    assert posiciones == sorted(posiciones)


@pytest.mark.parametrize("restante, esperado", [
    (VENTANA_VISTA_S + 0.01, False),   # todavia no entro
    (VENTANA_VISTA_S, True),
    (0.0, True),
    (-MARGEN_SALIDA_S, True),
    (-MARGEN_SALIDA_S - 0.01, False),  # ya salio
])
def test_en_vista(restante, esperado):
    assert en_vista(restante) is esperado


def test_se_respeta_la_digitacion_sugerida():
    """Si la pista sugiere una cuerda, el highway la usa aunque haya otra."""
    assert carril_de_nota(64, CUERDAS_ESTANDAR, cuerda=2) == 2


@pytest.mark.parametrize("nombre, cuerda, traste", [
    ("E2", 6, 0), ("A2", 5, 0), ("D3", 4, 0),
    ("G3", 3, 0), ("B3", 2, 0), ("E4", 1, 0),
    ("C3", 5, 3), ("E3", 4, 2), ("G4", 1, 3),
])
def test_sin_sugerencia_elige_el_traste_mas_bajo(nombre, cuerda, traste):
    """Es la posicion que tocaria alguien que recien empieza."""
    midi = nombre_a_midi(nombre)
    assert carril_de_nota(midi, CUERDAS_ESTANDAR) == cuerda
    assert midi - CUERDAS_ESTANDAR[6 - cuerda] == traste


def test_una_nota_que_ninguna_cuerda_alcanza_no_tiene_carril():
    # C1 esta muy por debajo de la 6a cuerda.
    assert carril_de_nota(24, CUERDAS_ESTANDAR) is None


def test_la_afinacion_cambia_el_carril():
    """En drop D la 6a cuerda baja a D2 y pasa a alcanzar notas que antes no.

    En afinacion estandar el D2 queda por debajo de todas las cuerdas: la mas
    grave es E2, dos semitonos mas arriba.
    """
    drop_d = (nombre_a_midi("D2"),) + CUERDAS_ESTANDAR[1:]
    assert carril_de_nota(nombre_a_midi("D2"), CUERDAS_ESTANDAR) is None
    assert carril_de_nota(nombre_a_midi("D2"), drop_d) == 6
    # Y una nota que antes salia en la 6a ahora necesita dos trastes mas.
    assert carril_de_nota(nombre_a_midi("E2"), drop_d) == 6


def test_un_acorde_ocupa_los_carriles_de_sus_notas():
    pista = desde_dict({"titulo": "x", "bpm": 60, "eventos": [
        {"t": 0.0, "dur": 1.0, "tipo": "acorde", "nombre": "Em",
         "notas": [40, 47, 52, 55, 59, 64]}]})
    assert carriles_de_evento(pista.eventos[0], pista.afinacion) == \
        (1, 2, 3, 4, 5, 6)


def test_una_nota_ocupa_un_solo_carril():
    pista = desde_dict({"titulo": "x", "bpm": 60, "eventos": [
        {"t": 0.0, "dur": 1.0, "tipo": "nota", "midi": 40,
         "cuerda": 6, "traste": 0}]})
    assert carriles_de_evento(pista.eventos[0], pista.afinacion) == (6,)


def test_la_sexta_cuerda_va_a_la_izquierda():
    """Como en una tablatura mirada de frente."""
    assert indice_carril(6) == 0
    assert indice_carril(1) == 5
    assert [indice_carril(c) for c in (6, 5, 4, 3, 2, 1)] == [0, 1, 2, 3, 4, 5]
