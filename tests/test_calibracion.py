"""Pruebas de la recomendacion de umbrales. Funciones puras sobre numeros."""

import pytest

from audio.calibracion import (SEPARACION_FLUJO_MINIMA, Estadisticas,
                               estadisticas, recomendar)

# Medidas tipicas de un microfono que separa bien la guitarra del ruido.
SANO = dict(
    nivel_silencio=Estadisticas(0.0012, 0.0018, 0.0020, 0.0030),
    nivel_tocando=Estadisticas(0.0450, 0.0700, 0.0800, 0.0900),
    flujo_silencio=Estadisticas(0.5, 1.1, 1.3, 1.6),
    flujo_tocando=Estadisticas(0.5, 1.3, 28.0, 56.0),
)


def test_estadisticas_de_serie_vacia():
    assert estadisticas([]) == Estadisticas(0.0, 0.0, 0.0, 0.0)


def test_estadisticas_basicas():
    e = estadisticas([1.0, 2.0, 3.0, 4.0, 100.0])
    assert e.mediana == 3.0
    assert e.maximo == 100.0
    assert e.mediana < e.p95 < e.p99 < e.maximo


def test_el_flujo_se_mide_con_p99_porque_los_ataques_son_escasos():
    """Los ataques ocupan ~1 de cada 100 ventanas: el p95 no los ve.

    Serie que imita una sesion real: sostenido en 0.5 y unos pocos picos de
    ataque en 30. El p95 cae en el sostenido y el p99 captura los picos.
    """
    serie = [0.5] * 97 + [30.0] * 3
    e = estadisticas(serie)
    assert e.p95 == pytest.approx(0.5, abs=0.1)
    assert e.p99 == pytest.approx(30.0, abs=0.1)


def test_microfono_sano_no_genera_avisos():
    r = recomendar(**SANO)
    assert r.avisos == ()
    assert r.separacion_nivel > 10.0
    # El umbral tiene que caer entre el ruido y la guitarra.
    assert SANO["nivel_silencio"].p95 < r.umbral < SANO["nivel_tocando"].mediana


def test_el_umbral_nunca_queda_por_encima_del_nivel_de_la_guitarra():
    """Un umbral asi dejaria el detector sordo, que es el peor resultado."""
    for nivel_tocando in (Estadisticas(0.032, 0.05, 0.06, 0.07),
                          Estadisticas(0.0020, 0.003, 0.0035, 0.004),
                          Estadisticas(0.0013, 0.002, 0.0025, 0.003)):
        r = recomendar(nivel_silencio=Estadisticas(0.018, 0.030, 0.036, 0.042),
                       nivel_tocando=nivel_tocando,
                       flujo_silencio=SANO["flujo_silencio"],
                       flujo_tocando=SANO["flujo_tocando"])
        assert r.umbral < nivel_tocando.mediana


def test_avisa_cuando_el_ruido_de_sala_tapa_la_guitarra():
    r = recomendar(nivel_silencio=Estadisticas(0.018, 0.030, 0.036, 0.042),
                   nivel_tocando=Estadisticas(0.032, 0.05, 0.06, 0.07),
                   flujo_silencio=SANO["flujo_silencio"],
                   flujo_tocando=SANO["flujo_tocando"])
    assert r.separacion_nivel < 1.5
    assert any("ruido de sala" in aviso for aviso in r.avisos)


def test_avisa_cuando_el_flujo_no_separa_los_ataques():
    r = recomendar(nivel_silencio=SANO["nivel_silencio"],
                   nivel_tocando=SANO["nivel_tocando"],
                   flujo_silencio=Estadisticas(2.4, 8.9, 11.0, 14.2),
                   flujo_tocando=Estadisticas(3.1, 7.0, 8.0, 20.0))
    assert r.separacion_flujo < SEPARACION_FLUJO_MINIMA
    assert any("flujo espectral" in aviso for aviso in r.avisos)


def test_el_factor_sugerido_queda_en_rango_usable():
    for flujo_tocando in (Estadisticas(1.0, 2.0, 2.5, 3.0),
                          Estadisticas(0.5, 1.3, 28.0, 48.0),
                          Estadisticas(50.0, 900.0, 9000.0, 12000.0)):
        r = recomendar(nivel_silencio=SANO["nivel_silencio"],
                       nivel_tocando=SANO["nivel_tocando"],
                       flujo_silencio=SANO["flujo_silencio"],
                       flujo_tocando=flujo_tocando)
        assert 2.0 <= r.factor <= 12.0


def test_no_divide_por_cero_con_medidas_en_cero():
    cero = Estadisticas(0.0, 0.0, 0.0, 0.0)
    r = recomendar(cero, cero, cero, cero)
    assert r.umbral >= 0.0
    assert 2.0 <= r.factor <= 12.0
    assert r.avisos  # tiene que quejarse, no devolver numeros como si nada
