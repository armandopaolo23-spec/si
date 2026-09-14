"""Conversion entre frecuencia, numero MIDI y nombre de nota.

Todo aqui es funcion pura: no toca audio ni pantalla, asi que se prueba
directamente con pytest.
"""

from dataclasses import dataclass

import numpy as np

LA4_HZ = 440.0
LA4_MIDI = 69

NOMBRES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ESPANOL = ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#",
           "La", "La#", "Si"]

# Cuerdas al aire en afinacion estandar, de la 6a a la 1a, en numero MIDI.
# Se guardan como MIDI y no como Hz para que no haya constantes duplicadas:
# la frecuencia sale de midi_a_hz().
CUERDAS_ESTANDAR = (40, 45, 50, 55, 59, 64)


@dataclass(frozen=True)
class Nota:
    """Nota mas cercana a una frecuencia, con su desviacion en cents."""

    midi: int
    nombre: str       # notacion inglesa con octava, p.ej. "E2"
    nombre_es: str    # notacion latina con octava, p.ej. "Mi2"
    cents: float      # desviacion respecto al midi exacto, en [-50, 50)


def hz_a_midi(f0):
    """Numero MIDI fraccionario de una frecuencia en Hz."""
    return LA4_MIDI + 12.0 * np.log2(f0 / LA4_HZ)


def midi_a_hz(midi):
    """Frecuencia en Hz de un numero MIDI (acepta fraccionarios)."""
    return LA4_HZ * 2.0 ** ((midi - LA4_MIDI) / 12.0)


def nombre_midi(midi_entero):
    """Nombre ingles con octava de un MIDI entero. MIDI 40 -> 'E2'."""
    return f"{NOMBRES[midi_entero % 12]}{midi_entero // 12 - 1}"


def desde_midi(midi):
    """Construye una Nota a partir de un MIDI fraccionario."""
    cercano = int(round(midi))
    return Nota(
        midi=cercano,
        nombre=nombre_midi(cercano),
        nombre_es=f"{ESPANOL[cercano % 12]}{cercano // 12 - 1}",
        cents=float((midi - cercano) * 100.0),
    )


def hz_a_nota(f0):
    """Nota mas cercana a una frecuencia en Hz."""
    return desde_midi(hz_a_midi(f0))


def cents_entre(f_medida, f_referencia):
    """Diferencia en cents entre dos frecuencias (positivo = mas aguda)."""
    return float(1200.0 * np.log2(f_medida / f_referencia))
