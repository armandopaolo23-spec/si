"""Pruebas del puntaje. Funcion pura."""

from nucleo.puntaje import (PUNTOS_ACIERTO, RACHA_MAXIMA_BONIFICADA,
                            puntos_por_acierto)


def test_el_primer_acierto_no_lleva_bonificacion():
    assert puntos_por_acierto(1) == PUNTOS_ACIERTO


def test_la_bonificacion_crece_con_la_racha():
    puntos = [puntos_por_acierto(r) for r in range(1, 8)]
    assert puntos == sorted(puntos)
    assert len(set(puntos)) == len(puntos)


def test_la_bonificacion_tiene_tope():
    """Sin tope, una pista larga daria numeros enormes y los primeros
    aciertos dejarian de significar algo."""
    tope = puntos_por_acierto(RACHA_MAXIMA_BONIFICADA + 1)
    assert puntos_por_acierto(50) == tope
    assert puntos_por_acierto(500) == tope


def test_una_racha_en_cero_no_da_puntos_negativos():
    assert puntos_por_acierto(0) == PUNTOS_ACIERTO
