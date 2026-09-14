"""Pruebas de YIN con señales sintetizadas en el propio test."""

import numpy as np
import pytest

from audio.notas import CUERDAS_ESTANDAR, cents_entre, hz_a_nota, midi_a_hz
from audio.yin import FMAX, FMIN, yin
from tests.sintesis import SR

MARCO = 2048


def seno(f0, n=MARCO, sr=SR, amplitud=0.1, fase=0.0):
    t = np.arange(n) / sr
    return (amplitud * np.sin(2 * np.pi * f0 * t + fase)).astype(np.float32)


def armonicos(f0, pesos, n=MARCO, sr=SR, amplitud=0.1, semilla=0):
    """Suma de armonicos con fases aleatorias, como una cuerda real."""
    rng = np.random.default_rng(semilla)
    t = np.arange(n) / sr
    x = np.zeros(n)
    for k, peso in enumerate(pesos, start=1):
        x += peso * np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, 2 * np.pi))
    x *= amplitud / max(np.max(np.abs(x)), 1e-12)
    return x.astype(np.float32)


@pytest.mark.parametrize("midi", CUERDAS_ESTANDAR)
def test_cuerdas_al_aire_con_armonicos(midi):
    """El requisito del proyecto: menos de 0.2 cents en las seis cuerdas."""
    esperada = midi_a_hz(midi)
    f0, confianza = yin(armonicos(esperada, [0.8 ** k for k in range(6)]), SR)
    assert f0 is not None
    assert abs(cents_entre(f0, esperada)) < 0.2
    assert confianza > 0.9


@pytest.mark.parametrize("f0_real", [80.0, 110.0, 220.0, 440.0, 660.0, 1000.0])
def test_seno_puro(f0_real):
    f0, confianza = yin(seno(f0_real), SR)
    assert f0 is not None
    assert abs(cents_entre(f0, f0_real)) < 1.0
    assert confianza > 0.9


def test_fundamental_ausente_no_produce_error_de_octava():
    """El caso del microfono de laptop: el fundamental del E2 casi no llega.

    Es la razon de usar YIN y no el pico del espectro. Se comprueba de paso
    que un detector espectral fallaria aqui, para que la prueba documente
    por que existe esta decision.
    """
    esperada = midi_a_hz(40)  # E2, 82.41 Hz
    # Sin fundamental, con el segundo armonico atenuado.
    x = armonicos(esperada, [0.0, 0.15, 0.6, 0.5, 0.35, 0.25], semilla=3)

    f0, confianza = yin(x, SR)
    assert f0 is not None
    assert hz_a_nota(f0).nombre == "E2"
    assert abs(cents_entre(f0, esperada)) < 1.0
    assert confianza > 0.8

    pico = int(np.argmax(np.abs(np.fft.rfft(x * np.hanning(len(x)))))) * SR / len(x)
    assert abs(cents_entre(pico, esperada)) > 1000.0


def test_es_independiente_de_la_amplitud():
    esperada = midi_a_hz(45)
    lecturas = [yin(armonicos(esperada, [0.8 ** k for k in range(6)], amplitud=a), SR)[0]
                for a in (0.4, 0.05, 0.005, 0.0005)]
    for f0 in lecturas:
        assert f0 is not None
        assert abs(cents_entre(f0, esperada)) < 0.5


def test_aguanta_ruido_de_ambiente():
    esperada = midi_a_hz(40)
    rng = np.random.default_rng(11)
    x = armonicos(esperada, [0.1, 0.6, 0.5, 0.35], amplitud=0.02, semilla=4)
    x = x + rng.normal(0, 0.002, len(x)).astype(np.float32)
    f0, confianza = yin(x, SR)
    assert f0 is not None
    assert abs(cents_entre(f0, esperada)) < 5.0
    assert confianza > 0.5


def test_ruido_blanco_no_da_tono():
    rng = np.random.default_rng(5)
    for semilla in range(5):
        x = rng.normal(0, 0.1, MARCO).astype(np.float32)
        f0, confianza = yin(x, SR)
        assert f0 is None or confianza < 0.5


def test_silencio_no_da_tono():
    assert yin(np.zeros(MARCO, dtype=np.float32), SR) == (None, 0.0)


def test_constante_no_da_tono():
    assert yin(np.full(MARCO, 0.3, dtype=np.float32), SR) == (None, 0.0)


def test_fuera_de_rango_se_rechaza():
    assert yin(seno(FMIN / 2), SR)[0] is None
    assert yin(seno(FMAX * 2), SR)[0] is None


def test_marco_demasiado_corto():
    assert yin(seno(220.0, n=64), SR) == (None, 0.0)
