"""Pruebas de la disposicion del highway. Geometria pura, sin ventana."""

import pytest

from audio.notas import CUERDAS_ESTANDAR, nombre_a_midi
from juego.geometria import (MARGEN_SALIDA_S, VENTANA_VISTA_S,
                             carril_de_nota, carriles_de_evento,
                             digitacion_de_acorde, digitacion_de_nota,
                             en_vista, indice_carril, posicion_relativa,
                             tablatura)
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


# ----------------------------------------------------------- digitacion

@pytest.mark.parametrize("nombre, cuerda, traste", [
    ("E2", 6, 0), ("A2", 5, 0), ("D3", 4, 0),
    ("G3", 3, 0), ("B3", 2, 0), ("E4", 1, 0),
    ("C3", 5, 3), ("E3", 4, 2), ("C4", 2, 1), ("G4", 1, 3),
])
def test_digitacion_de_nota_sin_sugerencia(nombre, cuerda, traste):
    midi = nombre_a_midi(nombre)
    assert digitacion_de_nota(midi, CUERDAS_ESTANDAR) == (cuerda, traste)


def test_digitacion_respeta_la_cuerda_que_indique_la_pista():
    """E4 en la 2a cuerda es el traste 5, no la 1a al aire."""
    midi = nombre_a_midi("E4")
    assert digitacion_de_nota(midi, CUERDAS_ESTANDAR, cuerda=2) == (2, 5)
    assert digitacion_de_nota(midi, CUERDAS_ESTANDAR, cuerda=1) == (1, 0)


def test_digitacion_respeta_cuerda_y_traste_juntos():
    midi = nombre_a_midi("E4")
    assert digitacion_de_nota(midi, CUERDAS_ESTANDAR, cuerda=2,
                              traste=5) == (2, 5)


def test_una_nota_inalcanzable_no_tiene_digitacion():
    assert digitacion_de_nota(24, CUERDAS_ESTANDAR) is None
    # Y en una cuerda que no llega tampoco.
    assert digitacion_de_nota(nombre_a_midi("E2"), CUERDAS_ESTANDAR,
                              cuerda=1) is None


@pytest.mark.parametrize("nombre, notas, esperado", [
    ("Em", [40, 47, 52, 55, 59, 64], "022000"),
    ("Am", [45, 52, 57, 60, 64], "x02210"),
    ("C", [48, 52, 55, 60, 64], "x32010"),
    ("G", [43, 47, 50, 55, 59, 67], "320003"),
    ("D", [50, 57, 62, 66], "xx0232"),
    ("A", [45, 52, 57, 61, 64], "x02220"),
    ("E", [40, 47, 52, 56, 59, 64], "022100"),
])
def test_digitacion_de_acordes_abiertos(nombre, notas, esperado):
    """Asignar cada nota a la cuerda libre de traste mas bajo reproduce las
    digitaciones de siempre. Si alguna sale distinta, la heuristica cambio."""
    assert tablatura(digitacion_de_acorde(notas, CUERDAS_ESTANDAR)) == esperado


@pytest.mark.parametrize("nombre, notas, esperado", [
    ("F", [41, 48, 53, 57, 60, 65], "133211"),
    ("Bm", [47, 54, 59, 62, 66], "x24432"),
    ("B", [47, 54, 59, 63, 66], "x24442"),
])
def test_digitacion_de_acordes_con_cejilla(nombre, notas, esperado):
    """Donde fallaba la version anterior.

    Asignar cada nota a la cuerda libre mas comoda, sin exigir que el orden
    de las cuerdas siga al de las notas, daba posiciones imposibles: un Bm
    salia con la 3a cuerda en el traste 16 y la 4a en el 24.
    """
    assert tablatura(digitacion_de_acorde(notas, CUERDAS_ESTANDAR)) == esperado


def test_las_cuerdas_que_suenan_van_en_orden_de_altura():
    """Es la restriccion que hace tocable una digitacion: la nota mas grave
    en la cuerda mas grave de las que suenan, y de ahi hacia arriba."""
    for notas in ([40, 47, 52, 55, 59, 64], [45, 52, 57, 60, 64],
                  [41, 48, 53, 57, 60, 65], [50, 57, 62, 66]):
        trastes = digitacion_de_acorde(notas, CUERDAS_ESTANDAR)
        sonando = [CUERDAS_ESTANDAR[i] + t
                   for i, t in enumerate(trastes) if t is not None]
        assert sonando == sorted(sonando)
        assert sonando == sorted(notas)


def test_un_acorde_con_mas_notas_que_cuerdas_no_tiene_digitacion():
    """Mejor decir que no se puede que inventar una posicion."""
    trastes = digitacion_de_acorde([40, 42, 44, 46, 48, 50, 52],
                                   CUERDAS_ESTANDAR)
    assert trastes == (None,) * 6


def test_se_prefiere_la_posicion_mas_compacta():
    """Entre varias asignaciones validas gana la que menos trastes abarca.

    El Am entra en las cuerdas 5 a 1 con los dedos entre los trastes 1 y 2,
    o en la 6 a la 1 salteando, con el indice en el traste 5. Tiene que
    elegir la primera.
    """
    trastes = digitacion_de_acorde([45, 52, 57, 60, 64], CUERDAS_ESTANDAR)
    pisados = [t for t in trastes if t]
    assert max(pisados) - min(pisados) == 1
    assert max(pisados) == 2


def test_cada_cuerda_se_usa_una_sola_vez():
    trastes = digitacion_de_acorde([40, 47, 52, 55, 59, 64], CUERDAS_ESTANDAR)
    assert len(trastes) == 6
    assert all(t is not None for t in trastes)


def test_la_tablatura_marca_con_x_las_cuerdas_que_no_suenan():
    assert tablatura((None, 0, 2, 2, 1, 0)) == "x02210"
    assert tablatura((None, None, 0, 2, 3, 2)) == "xx0232"


def test_la_tablatura_usa_letras_pasado_el_traste_9():
    """Como en cualquier cancionero: 10 es 'a', para que cada cuerda ocupe
    un solo caracter y la digitacion se lea alineada."""
    assert tablatura((10, 11, 12, None, None, None)) == "abcxxx"
