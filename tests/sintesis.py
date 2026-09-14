"""Sintesis de señales de guitarra para las pruebas.

Las pruebas nunca usan audio grabado ni el microfono: todo se genera aqui,
asi que son deterministas y corren en CI sin tarjeta de sonido.
"""

import numpy as np

SR = 44100


def pulsacion(f0, dur, sr=SR, amplitud=0.15, armonicos=7, decaimiento=3.0,
              recorte_graves=0.0, semilla=None):
    """Una pulsacion de cuerda: armonicos que decaen mas el ruido de la pua.

    recorte_graves atenua el fundamental y el segundo armonico para imitar el
    filtro paso-alto del microfono integrado de una laptop: 0.0 es sin
    recorte, 1.0 elimina el fundamental por completo.
    """
    rng = np.random.default_rng(semilla)
    n = int(dur * sr)
    t = np.arange(n) / sr
    x = np.zeros(n)
    for k in range(1, armonicos + 1):
        peso = 0.85 ** (k - 1)
        if k == 1:
            peso *= 1.0 - recorte_graves
        elif k == 2:
            peso *= 1.0 - 0.6 * recorte_graves
        # Los armonicos altos se apagan antes que el fundamental.
        env = np.exp(-decaimiento * (1.0 + 0.35 * (k - 1)) * t)
        x += peso * env * np.sin(2.0 * np.pi * f0 * k * t + rng.uniform(0, 2 * np.pi))

    # Transitorio de la pua: ruido corto y ancho al inicio del golpe.
    largo = min(n, int(0.004 * sr))
    ataque = rng.normal(0.0, 0.5, largo) * np.exp(-np.linspace(0, 6, largo))
    x[:largo] += ataque

    x *= amplitud / max(np.max(np.abs(x)), 1e-12)
    return x


def secuencia(notas, dur_total, sr=SR, piso_ruido=0.0012, semilla=7, **kwargs):
    """Coloca pulsaciones en una linea de tiempo.

    notas es una lista de (t_segundos, frecuencia_hz, duracion_segundos).
    Devuelve el array de audio y la lista de tiempos de ataque reales.
    """
    rng = np.random.default_rng(semilla)
    x = rng.normal(0.0, piso_ruido, int(dur_total * sr))
    tiempos = []
    for i, (t0, f0, dur) in enumerate(notas):
        golpe = pulsacion(f0, dur, sr=sr, semilla=semilla + i, **kwargs)
        ini = int(t0 * sr)
        fin = min(len(x), ini + len(golpe))
        x[ini:fin] += golpe[: fin - ini]
        tiempos.append(t0)
    return x.astype(np.float32), tiempos
