"""Canalizacion de analisis: de bloques de muestras a ataques con nota.

Este modulo es puro: recibe arrays de numpy y devuelve objetos. No importa
sounddevice ni pygame, asi que las pruebas lo alimentan con señales
sintetizadas en el propio test y no hace falta microfono ni ventana.

La decision de diseño que no es obvia: onset y pitch viven en escalas de
tiempo distintas
------------------------------------------------------------------------
Un ataque se puede ubicar en el tiempo con una ventana corta (~23 ms), pero
para saber *que* nota es hace falta una ventana larga (~46 ms) y ademas que
esa ventana ya este llena con la nota nueva, no con la anterior. Si se usara
la misma ventana para las dos cosas habria que elegir entre un timestamp
impreciso o un pitch inestable.

La solucion es separarlas: cuando el flujo espectral marca un ataque se
anota el instante y se deja el evento "pendiente"; el pitch se mide unos
saltos despues, cuando la ventana de analisis ya solo contiene la nota nueva,
y el ataque se emite con el timestamp temprano y el pitch tardio. El retraso
entre el golpe real y la emision es de unos 70 ms, pero el timestamp que
recibe el juego no arrastra ese retraso, que es lo que importa para calificar
el ritmo.
"""

from dataclasses import dataclass, field

import numpy as np

from audio.notas import Nota, hz_a_nota
from audio.onset import DetectorOnset
from audio.yin import FMAX, FMIN, yin

SR = 44100
MARCO = 2048            # ventana de analisis para YIN (~46 ms)
SALTO = 512             # avance entre ventanas (~11.6 ms)
UMBRAL_RUIDO = 0.003    # puerta de ruido sobre el RMS de la ventana
CONF_MINIMA = 0.5       # confianza YIN por debajo de la cual se ignora la lectura
SALTOS_ESPERA = 3       # saltos a esperar tras el ataque antes de medir pitch
SALTOS_PITCH = 3        # lecturas de pitch a promediar (mediana)
SALTOS_VIDA = 9         # si en tantos saltos no hubo pitch valido, se descarta
REFRACTARIO_S = 0.08    # minimo entre dos ataques emitidos
# Corrimiento del timestamp del ataque: el flujo espectral cruza el umbral
# algo despues del golpe real porque la ventana de Hann atenua justo las
# muestras recien llegadas. Medido con pulsaciones sintetizadas (ver
# tests/test_analizador.py), el sesgo es de poco mas de un salto.
RETARDO_ONSET_S = 0.014


@dataclass(frozen=True)
class Ataque:
    """Un golpe detectado, ya resuelto a nota."""

    t: float            # segundos desde el inicio del stream, instante del golpe
    nota: Nota
    f0: float
    confianza: float
    nivel: float        # RMS de la ventana en el momento del ataque


@dataclass(frozen=True)
class MarcoAnalizado:
    """Estado de una sola ventana. Lo consume el modo afinador de la CLI."""

    t: float
    nivel: float
    f0: float
    confianza: float
    flujo: float


@dataclass
class _Pendiente:
    """Ataque detectado al que todavia le falta decidir la nota."""

    t: float
    nivel: float
    espera: int
    vida: int = 0
    lecturas: list = field(default_factory=list)


class Analizador:
    """Alimentar con procesar(bloque); devuelve la lista de ataques nuevos."""

    def __init__(self, sr=SR, marco=MARCO, salto=SALTO,
                 umbral_ruido=UMBRAL_RUIDO, conf_minima=CONF_MINIMA,
                 saltos_espera=SALTOS_ESPERA, saltos_pitch=SALTOS_PITCH,
                 saltos_vida=SALTOS_VIDA, refractario_s=REFRACTARIO_S,
                 retardo_onset_s=RETARDO_ONSET_S, fmin=FMIN, fmax=FMAX):
        self.sr = sr
        self.marco = marco
        self.salto = salto
        self.umbral_ruido = umbral_ruido
        self.conf_minima = conf_minima
        self.saltos_espera = saltos_espera
        self.saltos_pitch = saltos_pitch
        self.saltos_vida = saltos_vida
        self.refractario_s = refractario_s
        self.retardo_onset_s = retardo_onset_s
        self.fmin = fmin
        self.fmax = fmax

        self._onset = DetectorOnset(sr)
        self._buffer = np.zeros(marco, dtype=np.float64)
        self._cola = np.zeros(0, dtype=np.float64)
        self._muestras = 0
        self._pendiente = None
        self._t_ultimo_disparo = -1e9

        # Diagnostico, se muestra al salir de la CLI.
        self.ultimo_marco = None
        self.pico_nivel = 0.0
        self.descartados = 0

    # ------------------------------------------------------------------ API

    def procesar(self, bloque):
        """Consume un bloque de muestras mono y devuelve los ataques nuevos.

        El bloque puede tener cualquier longitud: se acumula y se analiza en
        saltos de tamaño fijo, de modo que el reloj del analizador es el conteo
        de muestras y no el reloj de pared. Asi un tiron del hilo de render no
        desplaza los timestamps.
        """
        ataques = []
        self._cola = np.concatenate((self._cola, np.asarray(bloque, dtype=np.float64)))
        while len(self._cola) >= self.salto:
            salto, self._cola = self._cola[: self.salto], self._cola[self.salto:]
            self._buffer = np.roll(self._buffer, -self.salto)
            self._buffer[-self.salto:] = salto
            self._muestras += self.salto
            ataques.extend(self._analizar_ventana())
        return ataques

    @property
    def t_actual(self):
        """Segundos de audio consumidos."""
        return self._muestras / self.sr

    # -------------------------------------------------------------- interno

    def _analizar_ventana(self):
        ataques = []
        t_fin = self._muestras / self.sr
        nivel = float(np.sqrt(np.mean(self._buffer ** 2)))
        self.pico_nivel = max(self.pico_nivel, nivel)

        if nivel < self.umbral_ruido:
            # En silencio no se gasta CPU en YIN ni en la FFT del onset, pero
            # si queda un ataque pendiente hay que cerrarlo con lo que haya.
            ataques.extend(self._cerrar_pendiente())
            self.ultimo_marco = MarcoAnalizado(t_fin, nivel, 0.0, 0.0, 0.0)
            return ataques

        flujo, supera_umbral = self._onset.procesar(self._buffer)
        # Un mismo golpe supera el umbral en dos o tres ventanas seguidas; el
        # refractario deja pasar solo la primera, que es la que tiene el
        # timestamp correcto.
        hubo_onset = (supera_umbral
                      and t_fin - self._t_ultimo_disparo >= self.refractario_s)
        f0, confianza = yin(self._buffer, self.sr, self.fmin, self.fmax)
        valida = f0 is not None and confianza >= self.conf_minima
        self.ultimo_marco = MarcoAnalizado(t_fin, nivel, f0 or 0.0, confianza, flujo)

        if hubo_onset:
            # Un ataque nuevo cancela la espera del anterior: se emite ya con
            # las lecturas que alcanzo a juntar.
            ataques.extend(self._cerrar_pendiente())
            self._t_ultimo_disparo = t_fin
            self._pendiente = _Pendiente(
                t=max(0.0, t_fin - self.retardo_onset_s),
                nivel=nivel,
                espera=self.saltos_espera,
            )
        elif self._pendiente is not None:
            pendiente = self._pendiente
            pendiente.vida += 1
            if pendiente.espera > 0:
                pendiente.espera -= 1
            if pendiente.espera == 0 and valida:
                pendiente.lecturas.append((f0, confianza))
            if (len(pendiente.lecturas) >= self.saltos_pitch
                    or pendiente.vida >= self.saltos_vida):
                ataques.extend(self._cerrar_pendiente())

        return ataques

    def _cerrar_pendiente(self):
        """Emite el ataque pendiente, o lo descarta si nunca dio pitch."""
        pendiente, self._pendiente = self._pendiente, None
        if pendiente is None:
            return []
        if not pendiente.lecturas:
            self.descartados += 1
            return []
        # Mediana y no promedio: un solo salto de octava en las lecturas no
        # mueve la mediana, pero si arruinaria el promedio.
        f0 = float(np.median([f for f, _ in pendiente.lecturas]))
        confianza = float(np.median([c for _, c in pendiente.lecturas]))
        return [Ataque(t=pendiente.t, nota=hz_a_nota(f0), f0=f0,
                       confianza=confianza, nivel=pendiente.nivel)]
