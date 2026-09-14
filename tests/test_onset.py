"""Pruebas del flujo espectral, el detector de ataques de bajo nivel."""

import numpy as np

from audio.analizador import MARCO, SALTO
from audio.notas import midi_a_hz
from audio.onset import DetectorOnset
from tests.sintesis import SR, pulsacion


def recorrer(x, detector=None, marco=MARCO, salto=SALTO):
    """Devuelve la lista de (t, flujo, supera, umbral) de recorrer la señal."""
    detector = detector or DetectorOnset(SR)
    buffer = np.zeros(marco)
    filas = []
    for inicio in range(0, len(x) - salto + 1, salto):
        buffer = np.roll(buffer, -salto)
        buffer[-salto:] = x[inicio:inicio + salto]
        flujo, supera, umbral = detector.procesar(buffer)
        filas.append(((inicio + salto) / SR, flujo, supera, umbral))
    return filas


def test_primera_ventana_no_dispara():
    """Sin espectro anterior no hay diferencia que medir."""
    detector = DetectorOnset(SR)
    flujo, supera, umbral = detector.procesar(np.zeros(MARCO))
    assert (flujo, supera) == (0.0, False)
    assert umbral > 0.0


def test_el_ataque_destaca_sobre_el_sostenido():
    """Es la propiedad de la que depende todo el umbral adaptativo."""
    x = np.concatenate([
        np.zeros(int(0.2 * SR)),
        pulsacion(midi_a_hz(45), 1.0, decaimiento=1.2, semilla=1),
    ])
    filas = recorrer(x)
    flujo_ataque = max(f for t, f, _, _ in filas if 0.19 < t < 0.25)
    flujo_sostenido = max(f for t, f, _, _ in filas if 0.35 < t < 1.0)
    assert flujo_ataque > 5.0 * flujo_sostenido


def test_el_ruido_de_ambiente_no_supera_el_umbral_ya_calibrado():
    """El flujo mide cambio *relativo*, no nivel absoluto.

    Con el umbral ya calibrado (pasadas las primeras ventanas, mientras la
    historia todavia esta vacia) el ruido de ambiente no dispara. Rechazar el
    silencio en terminos absolutos no es tarea de este detector sino de la
    puerta de ruido RMS del Analizador, y eso se comprueba en
    test_analizador.test_solo_ruido_no_produce_ataques.
    """
    rng = np.random.default_rng(2)
    x = rng.normal(0, 0.0015, int(3 * SR))
    filas = recorrer(x)
    calibrado = [supera for t, _, supera, _ in filas if t > 0.25]
    assert filas[-1][0] > 2.0          # la señal era lo bastante larga
    assert not any(calibrado)


def test_el_piso_decae_y_deja_pasar_la_pulsacion_siguiente():
    """Tras un ataque el umbral queda alto, pero debe bajar en ~150 ms."""
    detector = DetectorOnset(SR)
    x = np.concatenate([
        np.zeros(int(0.2 * SR)),
        pulsacion(midi_a_hz(45), 0.15, decaimiento=1.2, semilla=1),
        pulsacion(midi_a_hz(45), 0.6, decaimiento=1.2, semilla=2),
    ])
    disparos = [t for t, _, supera, _ in recorrer(x, detector) if supera]
    assert len(disparos) == 2
    assert disparos[0] < 0.24
    assert 0.34 < disparos[1] < 0.40


def test_el_umbral_devuelto_explica_la_decision():
    """El umbral sale del detector para poder mostrarlo en el diagnostico.

    Sin esto no hay forma de distinguir "disparo de mas" de "toque de mas"
    mirando la salida.
    """
    x = np.concatenate([
        np.zeros(int(0.2 * SR)),
        pulsacion(midi_a_hz(45), 1.0, decaimiento=1.2, semilla=1),
    ])
    filas = recorrer(x)
    for _, flujo, supera, umbral in filas:
        assert umbral > 0.0
        if supera:
            assert flujo > umbral
