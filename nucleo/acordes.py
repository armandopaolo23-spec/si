"""Reconocimiento de acordes a partir de la energia por semitono.

Hay dos lecturas del mismo vector, y cada una responde una pregunta distinta:

Presencia por nota: de las notas que el acorde pedia, cuantas suenan de
verdad en su frecuencia exacta. Es lo que decide acierto o fallo, y de paso
dice cuales faltaron, que es la devolucion util para quien esta aprendiendo.

Croma: el vector plegado a las 12 clases de nota, comparado contra plantillas
de los acordes abiertos. Sirve para nombrar lo que sono cuando no es lo
pedido ("tocaste C"), pero no para decidir: medido contra rasgueos
sintetizados, tocar C da 0.81 de similitud con la plantilla de Em, mas que
tocar Em de verdad (0.78). Plegar a 12 clases pierde justo la informacion que
distingue Em de C, porque comparten dos de sus tres notas.

Juntas aciertan 55 de 56 veces el acorde correcto y rechazan 335 de 336
incorrectos.
"""

from dataclasses import dataclass

import numpy as np

from audio.croma import MIDI_MINIMO, NOTAS, indice_de_midi
from audio.notas import hz_a_midi, midi_a_hz

# Acordes abiertos basicos, con las notas que suenan en su posicion habitual.
ACORDES_ABIERTOS = {
    "Em": (40, 47, 52, 55, 59, 64),
    "E": (40, 47, 52, 56, 59, 64),
    "Am": (45, 52, 57, 60, 64),
    "A": (45, 52, 57, 61, 64),
    "C": (48, 52, 55, 60, 64),
    "G": (43, 47, 50, 55, 59, 67),
    "D": (50, 57, 62, 66),
}

ARMONICOS_PLANTILLA = 4       # cuantos armonicos modela cada nota
DECAIMIENTO_PLANTILLA = 0.6   # cuanto pesa cada armonico respecto al anterior

PERCENTIL_PISO = 25           # el ruido de fondo del propio espectro
FACTOR_PISO = 3.0             # cuanto hay que superarlo para contar como nota
FRACCION_MINIMA = 0.7         # notas del acorde que tienen que sonar


@dataclass(frozen=True)
class Reconocimiento:
    acertado: bool
    fraccion: float          # proporcion de las notas pedidas que sonaron
    faltantes: tuple         # midis pedidos que no se oyeron
    nombre_oido: str         # a que acorde se parece lo que sono, o None


def croma(energias):
    """Pliega la energia por semitono a las 12 clases de nota, normalizada."""
    if energias is None:
        return np.zeros(12)
    vector = np.zeros(12)
    for indice, valor in enumerate(np.asarray(energias)):
        vector[(MIDI_MINIMO + indice) % 12] += valor
    norma = np.linalg.norm(vector)
    return vector / norma if norma else vector


def plantilla(midis, armonicos=ARMONICOS_PLANTILLA,
              decaimiento=DECAIMIENTO_PLANTILLA):
    """Croma que produciria ese conjunto de notas, con sus armonicos.

    Los armonicos importan: el tercero de una nota cae en su quinta, asi que
    una plantilla de clases puras no se parece a lo que mide el microfono.
    """
    vector = np.zeros(12)
    for midi in midis:
        for orden in range(1, armonicos + 1):
            clase = int(round(hz_a_midi(midi_a_hz(midi) * orden))) % 12
            vector[clase] += decaimiento ** (orden - 1)
    norma = np.linalg.norm(vector)
    return vector / norma if norma else vector


PLANTILLAS = {nombre: plantilla(midis)
              for nombre, midis in ACORDES_ABIERTOS.items()}


def similitud(croma_a, croma_b):
    """Coseno entre dos cromas ya normalizados."""
    return float(np.dot(croma_a, croma_b))


def nombrar(energias):
    """Acorde abierto al que mas se parece lo que sono, y cuanto."""
    medido = croma(energias)
    if not medido.any():
        return None, 0.0
    nombre = max(PLANTILLAS, key=lambda n: similitud(medido, PLANTILLAS[n]))
    return nombre, similitud(medido, PLANTILLAS[nombre])


def notas_presentes(energias, midis, percentil=PERCENTIL_PISO,
                    factor=FACTOR_PISO):
    """Para cada nota pedida, si suena por encima del ruido del espectro.

    El piso sale del percentil bajo de las energias medidas y no de un valor
    absoluto, asi que se adapta solo al nivel de entrada del microfono.
    """
    # energias puede venir en None: un ataque que se cerro antes de llenar la
    # ventana armonica no tiene con que juzgar un acorde, y decir que no suena
    # nada es la respuesta honesta.
    if energias is None:
        return tuple(False for _ in midis)
    energias = np.asarray(energias)
    if len(energias) != NOTAS or not energias.any():
        return tuple(False for _ in midis)
    piso = float(np.percentile(energias, percentil)) * factor
    presentes = []
    for midi in midis:
        indice = indice_de_midi(midi)
        # bool() y no el np.bool_ que sale de la comparacion: el resultado
        # viaja hasta el render y se compara con True y False a secas.
        presentes.append(bool(indice is not None and energias[indice] > piso))
    return tuple(presentes)


def reconocer(energias, midis, fraccion_minima=FRACCION_MINIMA, nombre=None):
    """Decide si lo que sono es el acorde pedido.

    Se exige las dos cosas: que suene la mayoria de las notas pedidas y que
    el croma coincida con el acorde esperado. La primera sola acepta un La
    mayor cuando se pedia La menor, porque difieren en una sola nota y todas
    las demas estan; la segunda sola acepta un Do cuando se pedia Mi menor.
    """
    presentes = notas_presentes(energias, midis)
    faltantes = tuple(midi for midi, suena in zip(midis, presentes)
                      if not suena)
    fraccion = sum(presentes) / len(presentes) if presentes else 0.0
    oido, _ = nombrar(energias)

    coincide_el_nombre = nombre is None or oido == nombre
    acertado = fraccion >= fraccion_minima and coincide_el_nombre
    return Reconocimiento(acertado=acertado, fraccion=fraccion,
                          faltantes=faltantes, nombre_oido=oido)
