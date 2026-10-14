"""Medida armonica del espectro: cuanta energia hay en cada semitono.

Es la entrada del detector de acordes. YIN no sirve para rasgueos porque mide
periodicidad y un acorde no es periodico: con una rasgueada sintetizada su
confianza se queda en 0.54-0.67, por debajo del minimo, y el ataque se
descarta. Hace falta mirar el espectro.

Lo que se mide aqui es deliberadamente crudo: la energia maxima en una banda
de medio semitono alrededor de cada nota de la guitarra. De ese vector salen
despues las dos lecturas que hace nucleo/acordes.py -que notas suenan y a que
acorde se parece el conjunto- sin repetir el analisis espectral.

Por que la ventana es tan larga
-------------------------------
Son 8192 muestras, 186 ms. Medido contra rasgueos sintetizados, con 4096 el
reconocimiento cae de 55/56 a 25/56: a esa resolucion el lobulo de la ventana
no separa dos semitonos vecinos en el registro grave, y un La mayor pasa por
La menor porque difieren en un solo semitono. No es un parametro a gusto,
es el ancho que hace falta para distinguirlos.
"""

import math

import numpy as np

from audio.notas import hz_a_midi, midi_a_hz
from audio.yin import FMAX, FMIN

MARCO_ACORDE = 8192           # 186 ms a 44100 Hz
ANCHO_BANDA = 0.5             # semitonos a cada lado de la nota

# Mismo rango que acepta el validador de pistas, por el mismo motivo: se
# deriva de los limites del detector para que no puedan desincronizarse.
MIDI_MINIMO = math.ceil(hz_a_midi(FMIN))
MIDI_MAXIMO = math.floor(hz_a_midi(FMAX))
NOTAS = MIDI_MAXIMO - MIDI_MINIMO + 1


class MedidorArmonico:
    """Calcula la energia por semitono. Precalcula las bandas una sola vez."""

    def __init__(self, sr, marco=MARCO_ACORDE, ancho_banda=ANCHO_BANDA):
        self.sr = sr
        self.marco = marco
        self._ventana = np.hanning(marco)
        frecuencias = np.fft.rfftfreq(marco, 1.0 / sr)
        self._bandas = []
        for midi in range(MIDI_MINIMO, MIDI_MAXIMO + 1):
            centro = midi_a_hz(midi)
            dentro = np.where(
                (frecuencias >= centro * 2.0 ** (-ancho_banda / 12.0))
                & (frecuencias <= centro * 2.0 ** (ancho_banda / 12.0)))[0]
            self._bandas.append(dentro)

    def energia_por_nota(self, muestras):
        """Vector de NOTAS valores: energia en cada semitono, de MIDI_MINIMO
        a MIDI_MAXIMO. Espera al menos `marco` muestras y usa las ultimas."""
        if len(muestras) < self.marco:
            return np.zeros(NOTAS)
        marco = np.asarray(muestras[-self.marco:], dtype=np.float64)
        magnitud = np.abs(np.fft.rfft(marco * self._ventana))
        return np.array([magnitud[banda].max() if len(banda) else 0.0
                         for banda in self._bandas])


def indice_de_midi(midi):
    """Posicion de una nota en el vector de energias, o None si esta fuera."""
    if not MIDI_MINIMO <= midi <= MIDI_MAXIMO:
        return None
    return midi - MIDI_MINIMO
