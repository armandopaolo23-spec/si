"""Deteccion de ataques (onsets) por flujo espectral con umbral adaptativo.

Para que sirve
--------------
El detector de pitch dice que nota suena, pero no cuando empezo: si una nota
se sostiene medio segundo, YIN la reporta unas 40 veces seguidas. El juego
necesita un solo evento por pulsacion, y ahi entra el onset.

Por que flujo espectral y no envolvente RMS
-------------------------------------------
El RMS solo ve el volumen total, asi que se pierde el caso comun de repicar
la misma cuerda sin dejarla apagar: el nivel casi no baja entre pulsaciones y
el ataque pasa desapercibido. El flujo espectral mide cuanta energia *nueva*
aparece por banda de frecuencia, y una pulsacion siempre trae energia nueva
en los agudos (el ruido de la uña o la pua) aunque el volumen no suba.

El umbral es adaptativo (mediana de la historia reciente por un factor) en
vez de fijo porque el nivel del microfono de laptop cambia con la distancia
y con el ruido de la habitacion; un umbral fijo o dispara con todo o con nada.
"""

import numpy as np

VENTANA = 1024         # ~23 ms: suficientemente corta para no borronear el ataque
BANDA = (70.0, 4000.0)  # fuera de aqui solo hay zumbido de red y siseo del micro
# El flujo de un ataque queda ~30 veces por encima del flujo del sostenido
# (medido con pulsaciones sintetizadas), asi que conviene un umbral exigente:
# con factores cercanos a 1 las fluctuaciones del decaimiento disparan solas.
FACTOR = 6.0           # cuantas veces la mediana reciente hay que superar
MARGEN = 1.0           # piso absoluto, para que el siseo del micro no dispare
HISTORIA = 20          # ~0.23 s de flujo para calcular la mediana
COMPRESION = 1000.0    # lambda de log(1 + lambda*mag)
DECAIMIENTO = 0.85     # cuanto cae por salto el piso que deja un ataque


class DetectorOnset:
    """Mantiene el espectro anterior y decide, salto a salto, si hubo ataque."""

    def __init__(self, sr, ventana=VENTANA, banda=BANDA, factor=FACTOR,
                 margen=MARGEN, historia=HISTORIA, decaimiento=DECAIMIENTO):
        self._ventana = ventana
        self._factor = factor
        self._margen = margen
        self._decaimiento = decaimiento
        self._hann = np.hanning(ventana)
        resolucion = sr / ventana
        self._bin_ini = max(1, int(banda[0] / resolucion))
        self._bin_fin = min(ventana // 2 + 1, int(banda[1] / resolucion) + 1)
        self._mag_previa = None
        self._historia = np.zeros(historia)
        self._n_historia = 0
        self._piso = 0.0

    def _magnitud(self, marco):
        x = marco[-self._ventana:] * self._hann
        mag = np.abs(np.fft.rfft(x)) / self._ventana
        # La compresion logaritmica evita que una pulsacion fuerte fije una
        # mediana altisima que luego se coma los ataques suaves siguientes.
        return np.log1p(COMPRESION * mag[self._bin_ini:self._bin_fin])

    def procesar(self, marco):
        """Devuelve (flujo, supera_umbral, umbral) para la ventana mas reciente.

        No aplica periodo refractario: un mismo golpe puede superar el umbral
        en dos o tres ventanas seguidas. Agrupar eso en un solo ataque es
        tarea del Analizador, que es quien tambien decide sobre los ataques
        por cambio de pitch y necesita un unico refractario para los dos.
        """
        mag = self._magnitud(marco)
        if self._mag_previa is None:
            self._mag_previa = mag
            return 0.0, False, self._margen

        # Solo las diferencias positivas: la energia que se apaga no es ataque.
        flujo = float(np.sum(np.maximum(mag - self._mag_previa, 0.0)))
        self._mag_previa = mag

        umbral = self._margen
        if self._n_historia > 0:
            mediana = float(np.median(self._historia[: self._n_historia]))
            umbral = max(umbral, mediana * self._factor + self._margen)

        # Piso que decae: un ataque fuerte deja el umbral alto y lo va
        # bajando. Sin esto, el decaimiento de una nota grave produce bultos
        # de flujo unos 90 ms despues del golpe que la mediana todavia no
        # alcanzo a subir, y se cuentan como una segunda pulsacion.
        efectivo = max(umbral, self._piso)
        supera = flujo > efectivo
        self._piso = max(self._piso * self._decaimiento, flujo if supera else 0.0)

        self._historia = np.roll(self._historia, -1)
        self._historia[-1] = flujo
        self._n_historia = min(self._n_historia + 1, len(self._historia))
        return flujo, supera, efectivo
