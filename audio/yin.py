"""Deteccion de frecuencia fundamental con el algoritmo YIN, solo con numpy.

Como funciona, en corto
----------------------
YIN busca el desplazamiento tau que hace minima la diferencia entre la señal
y su copia retrasada tau muestras: si la señal es periodica, ese tau es el
periodo. El paso que no es obvio es la "diferencia media normalizada
acumulada" (cmnd): sin ella el minimo global tiende a caer en un multiplo
del periodo real y el detector reporta una octava por debajo. La cmnd divide
cada diferencia por el promedio de las diferencias anteriores, lo que castiga
a los tau grandes y deja el primer minimo verdadero como el mas barato.

Por que YIN y no el pico de la FFT
----------------------------------
El microfono integrado de una laptop recorta por debajo de ~150 Hz, asi que
el fundamental de la 6a cuerda (E2, 82 Hz) puede llegar casi ausente. La
forma de onda sigue siendo periodica a 82 Hz porque los armonicos sobreviven,
y YIN mide esa periodicidad en el tiempo, no la energia de una banda: acierta
aunque falte el fundamental. Un detector de pico espectral reportaria 164 Hz,
el segundo armonico. Ese es el motivo principal de usarlo aqui.
"""

import numpy as np

FMIN = 70.0        # por debajo del E2 (82.41 Hz)
FMAX = 1200.0      # cubre hasta el traste 12 de la primera cuerda
UMBRAL = 0.15      # mas bajo = mas exigente para aceptar un minimo


def yin(marco, sr, fmin=FMIN, fmax=FMAX, umbral=UMBRAL):
    """Devuelve (frecuencia_hz, confianza) o (None, 0.0) si no hay tono claro.

    La confianza es 1 - cmnd en el minimo elegido: 1.0 seria periodicidad
    perfecta, y en la practica una nota de guitarra limpia da 0.8-0.99.
    """
    n = len(marco)
    tau_min = max(2, int(sr / fmax))
    tau_max = min(int(sr / fmin), n // 2)
    if tau_max <= tau_min:
        return None, 0.0

    x = np.asarray(marco, dtype=np.float64)
    x = x - x.mean()
    ventana = n - tau_max      # muestras sobre las que se integra la diferencia

    # d(tau) = e0 + e_tau - 2*acf(tau). Se calcula con FFT para que el costo
    # sea O(n log n) en vez de O(n * tau_max), que no aguantaria tiempo real.
    acumulada = np.concatenate(([0.0], np.cumsum(x ** 2)))
    e0 = acumulada[ventana] - acumulada[0]
    if e0 <= 1e-20:
        return None, 0.0
    indices = np.arange(tau_max + 1)
    e_tau = acumulada[ventana + indices] - acumulada[indices]

    tamano = 1 << int(np.ceil(np.log2(2 * n)))
    a = np.fft.rfft(x[:ventana], tamano)
    b = np.fft.rfft(x, tamano)
    acf = np.fft.irfft(np.conj(a) * b, tamano)[: tau_max + 1]

    d = e0 + e_tau - 2.0 * acf
    np.maximum(d, 0.0, out=d)

    cmnd = np.ones(tau_max + 1)
    suma = np.cumsum(d[1:])
    cmnd[1:] = d[1:] * np.arange(1, tau_max + 1) / np.maximum(suma, 1e-12)

    # Primer minimo local por debajo del umbral: tomar el primero y no el
    # global es lo que evita saltar a un submultiplo del periodo.
    tau = -1
    t = tau_min
    while t < tau_max:
        if cmnd[t] < umbral:
            while t + 1 < tau_max and cmnd[t + 1] < cmnd[t]:
                t += 1
            tau = t
            break
        t += 1
    if tau == -1:
        # Ningun minimo cruzo el umbral: se acepta el global solo si es bueno.
        tau = tau_min + int(np.argmin(cmnd[tau_min:tau_max]))
        if cmnd[tau] > 0.5:
            return None, 0.0

    tau_entero = tau
    # Un minimo pegado al borde del rango de busqueda no es un minimo: es que
    # YIN no encontro ninguno y se quedo con el extremo. Se reconoce porque
    # devuelve una frecuencia clavada en fmin o en fmax. Medido con el
    # microfono real, ese caso aparecia como notas de 70.00 Hz exactos, que
    # no existen en una guitarra afinada ni en drop D.
    if tau_entero <= tau_min or tau_entero >= tau_max - 1:
        return None, 0.0

    confianza = float(np.clip(1.0 - cmnd[tau_entero], 0.0, 1.0))

    # Interpolacion parabolica: sin esto la resolucion en frecuencia es la del
    # periodo en muestras enteras, que en el registro agudo son varios cents.
    tau_fino = float(tau_entero)
    if 0 < tau_entero < tau_max:
        y0, y1, y2 = cmnd[tau_entero - 1], cmnd[tau_entero], cmnd[tau_entero + 1]
        denominador = 2.0 * (2.0 * y1 - y0 - y2)
        if abs(denominador) > 1e-12:
            # El ajuste real cae en +-0.5 muestras; se recorta por seguridad
            # porque un denominador casi nulo puede dar un salto absurdo.
            tau_fino += float(np.clip((y2 - y0) / denominador, -1.0, 1.0))

    if tau_fino <= 0.0:
        return None, 0.0
    f0 = sr / tau_fino
    if not (fmin <= f0 <= fmax):
        return None, 0.0
    return float(f0), confianza
