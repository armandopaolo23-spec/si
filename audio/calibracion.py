"""Calibracion de la entrada contra el microfono real.

Los umbrales por defecto del motor estan ajustados contra señales
sintetizadas. Un microfono integrado real tiene otro piso de ruido y otra
ganancia, asi que hay que medirlos antes de creerle a los umbrales.

La idea es simple: medir el nivel y el flujo espectral en dos condiciones
(sala en silencio y guitarra sonando) y comprobar que hay separacion entre
las dos. Si no la hay, ningun umbral funciona y el problema esta en la
entrada de audio, no en el detector.

Todo aqui es funcion pura sobre listas de numeros: la CLI se encarga de
recolectarlos.
"""

from dataclasses import dataclass

import numpy as np

FACTOR_MINIMO = 2.0
FACTOR_MAXIMO = 12.0
SEPARACION_NIVEL_MINIMA = 1.5    # por debajo de esto, la puerta no discrimina
SEPARACION_FLUJO_MINIMA = 4.0    # por debajo de esto, el onset no discrimina


@dataclass(frozen=True)
class Estadisticas:
    mediana: float
    p95: float
    p99: float
    maximo: float


@dataclass(frozen=True)
class Recomendacion:
    umbral: float            # valor sugerido para --umbral
    factor: float            # valor sugerido para el factor del onset
    separacion_nivel: float  # cuantas veces sube el nivel al tocar
    separacion_flujo: float  # cuantas veces sube el flujo en los ataques
    avisos: tuple            # problemas encontrados, en español


def estadisticas(valores):
    """Mediana, percentiles 95 y 99, y maximo de una serie de medidas."""
    arreglo = np.asarray(list(valores), dtype=np.float64)
    if arreglo.size == 0:
        return Estadisticas(0.0, 0.0, 0.0, 0.0)
    return Estadisticas(
        mediana=float(np.median(arreglo)),
        p95=float(np.percentile(arreglo, 95)),
        p99=float(np.percentile(arreglo, 99)),
        maximo=float(np.max(arreglo)),
    )


def recomendar(nivel_silencio, nivel_tocando, flujo_silencio, flujo_tocando):
    """Sugiere puerta de ruido y factor de onset a partir de lo medido.

    nivel_*  son Estadisticas del RMS por ventana.
    flujo_*  son Estadisticas del flujo espectral por ventana.
    """
    avisos = []

    # Puerta de ruido: por encima del ruido de sala y por debajo del nivel
    # al que suena la guitarra. Se apunta al p95 del silencio con margen.
    piso = max(nivel_silencio.p95, 1e-6)
    separacion_nivel = nivel_tocando.mediana / piso
    umbral = piso * 1.5
    techo = nivel_tocando.mediana * 0.7
    if umbral > techo:
        # No cabe el margen de 1.5x: quedarse a medio camino entre el ruido y
        # la guitarra, que en escala de proporciones es la media geometrica.
        umbral = float(np.sqrt(piso * max(nivel_tocando.mediana, 1e-6)))
    # Nunca sugerir una puerta por encima del nivel al que suena la guitarra:
    # dejaria el detector sordo, que es peor que dejarlo disparar de mas. Si
    # se llega aca la separacion es mala y el aviso de abajo lo dice.
    umbral = max(0.0, min(umbral, techo))

    if separacion_nivel < SEPARACION_NIVEL_MINIMA:
        avisos.append(
            f"La guitarra solo sube el nivel {separacion_nivel:.1f}x sobre el "
            f"ruido de sala. Ninguna puerta de ruido va a separar las dos "
            f"cosas: acerca el microfono a la boca de la guitarra, o reduce "
            f"el ruido de ambiente (ventilador, ventana, teclado).")
    elif piso * 1.5 > techo:
        avisos.append(
            f"La separacion de nivel es justa ({separacion_nivel:.1f}x). El "
            f"umbral sugerido queda a medio camino y algun ataque suave se "
            f"puede perder.")

    # Factor del onset: el umbral tiene que caer entre el flujo del ruido y
    # el flujo de los ataques. Se toma la media geometrica de la razon, que
    # es el punto medio natural en una escala de proporciones.
    # Para el flujo se usa el p99 y no el p95: los ataques ocupan una o dos
    # ventanas de cada cien, asi que el p95 cae entero dentro del sostenido y
    # mediria una separacion falsa de ~1x.
    flujo_piso = max(flujo_silencio.mediana, 1e-6)
    separacion_flujo = flujo_tocando.p99 / flujo_piso
    factor = float(np.clip(np.sqrt(separacion_flujo),
                           FACTOR_MINIMO, FACTOR_MAXIMO))
    if separacion_flujo < SEPARACION_FLUJO_MINIMA:
        avisos.append(
            f"Los ataques solo suben el flujo espectral {separacion_flujo:.1f}x "
            f"sobre el ruido. El detector de ataques va a disparar de mas: "
            f"revisa si el microfono tiene supresion de ruido o control "
            f"automatico de ganancia activados.")

    return Recomendacion(
        umbral=float(umbral),
        factor=factor,
        separacion_nivel=float(separacion_nivel),
        separacion_flujo=float(separacion_flujo),
        avisos=tuple(avisos),
    )
