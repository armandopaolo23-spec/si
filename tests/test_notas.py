"""Pruebas de la conversion frecuencia <-> nota. Todo funcion pura."""

import numpy as np
import pytest

from audio.notas import (CUERDAS_ESTANDAR, cents_entre, hz_a_midi, hz_a_nota,
                         midi_a_hz, nombre_midi)


def test_la4_es_la_referencia():
    nota = hz_a_nota(440.0)
    assert nota.nombre == "A4"
    assert nota.nombre_es == "La4"
    assert nota.midi == 69
    assert nota.cents == pytest.approx(0.0, abs=1e-9)


def test_nombres_de_las_cuerdas_al_aire():
    assert [nombre_midi(m) for m in CUERDAS_ESTANDAR] == \
        ["E2", "A2", "D3", "G3", "B3", "E4"]


def test_frecuencias_de_las_cuerdas_al_aire():
    # Valores de tabla de afinacion estandar, redondeados a 2 decimales.
    esperadas = [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
    assert [round(midi_a_hz(m), 2) for m in CUERDAS_ESTANDAR] == esperadas


def test_ida_y_vuelta_midi():
    for midi in range(28, 96):
        assert hz_a_midi(midi_a_hz(midi)) == pytest.approx(midi, abs=1e-9)


def test_cents_tienen_signo():
    # Un semitono arriba de A4 esta a medio camino: se redondea a A#4.
    assert hz_a_nota(440.0 * 2 ** (0.25 / 12)).cents == pytest.approx(25.0, abs=0.01)
    assert hz_a_nota(440.0 * 2 ** (-0.25 / 12)).cents == pytest.approx(-25.0, abs=0.01)


def test_cents_siempre_en_media_banda():
    for f in np.geomspace(70.0, 1300.0, 400):
        assert -50.0 <= hz_a_nota(f).cents <= 50.0


def test_cents_entre():
    assert cents_entre(440.0, 440.0) == pytest.approx(0.0)
    assert cents_entre(880.0, 440.0) == pytest.approx(1200.0)
    assert cents_entre(440.0 * 2 ** (1 / 1200), 440.0) == pytest.approx(1.0)


def test_octavas_bajas_no_se_desbordan():
    # MIDI 0 es C-1; el operador // en Python redondea hacia abajo, que es lo
    # que queremos para octavas negativas.
    assert nombre_midi(0) == "C-1"
    assert nombre_midi(12) == "C0"
