"""Como se muestra cada nota en la guitarra: carril, altura y digitacion.

Geometria pura, sin pygame: se prueba sin abrir ventana. El render toma de
aqui las posiciones y solo dibuja.

El carril es el numero de cuerda del formato de pista (1 = la mas aguda,
6 = la mas grave). En pantalla la 6a va a la izquierda, como en una tablatura
mirada de frente.
"""

from nucleo.pista import CUERDAS, TRASTE_MAXIMO

VENTANA_VISTA_S = 3.0    # segundos de pista visibles por encima de la linea
MARGEN_SALIDA_S = 0.5    # cuanto sigue bajando una nota ya pasada


def posicion_relativa(restante, ventana_vista=VENTANA_VISTA_S):
    """0.0 arriba de la pantalla, 1.0 sobre la linea de golpe, >1 pasada."""
    return 1.0 - restante / ventana_vista


def en_vista(restante, ventana_vista=VENTANA_VISTA_S,
             margen_salida=MARGEN_SALIDA_S):
    """True si la nota tiene que dibujarse en este cuadro."""
    return -margen_salida <= restante <= ventana_vista


def carril_de_nota(midi, afinacion, cuerda=None):
    """Carril 1..6 donde mostrar una nota. Respeta la sugerencia si la hay.

    Sin sugerencia se elige la cuerda que llegue a esa nota con el traste mas
    bajo, que es la posicion que tocaria alguien que recien empieza. Devuelve
    None si ninguna cuerda de esta afinacion la alcanza.
    """
    if cuerda is not None:
        return cuerda
    mejor, mejor_traste = None, None
    for indice, nota_cuerda in enumerate(afinacion):
        traste = midi - nota_cuerda
        if not 0 <= traste <= TRASTE_MAXIMO:
            continue
        if mejor_traste is None or traste < mejor_traste:
            mejor, mejor_traste = CUERDAS - indice, traste
    return mejor


def digitacion_de_nota(midi, afinacion, cuerda=None, traste=None):
    """Devuelve (cuerda, traste) para tocar una nota, o None si no se alcanza.

    Respeta lo que indique la pista. Si falta el traste pero hay cuerda, lo
    calcula sobre esa cuerda; si no hay nada, elige la posicion del traste
    mas bajo, igual que carril_de_nota.
    """
    if cuerda is not None:
        if traste is None:
            traste = midi - afinacion[CUERDAS - cuerda]
        if not 0 <= traste <= TRASTE_MAXIMO:
            return None
        return cuerda, traste
    elegida = carril_de_nota(midi, afinacion)
    if elegida is None:
        return None
    return elegida, midi - afinacion[CUERDAS - elegida]


def digitacion_de_acorde(notas, afinacion):
    """Traste por cuerda para un acorde, de la 6a a la 1a. None = no se toca.

    Cada nota se asigna a la cuerda libre que la alcance con el traste mas
    bajo, recorriendo de la mas grave a la mas aguda. Con los acordes
    abiertos basicos esto reproduce las digitaciones de siempre: Em sale
    022000, Am sale x02210, C sale x32010 y G sale 320003.
    """
    trastes = [None] * CUERDAS          # indice 0 = 6a cuerda
    for midi in sorted(notas):
        candidatas = []
        for indice, nota_cuerda in enumerate(afinacion):
            if trastes[indice] is not None:
                continue
            traste = midi - nota_cuerda
            if 0 <= traste <= TRASTE_MAXIMO:
                candidatas.append((traste, indice))
        if candidatas:
            traste, indice = min(candidatas)
            trastes[indice] = traste
    return tuple(trastes)


def tablatura(trastes):
    """Texto de una digitacion de acorde: 022000, x32010.

    Las cuerdas que no suenan van con x, como en cualquier cancionero.
    """
    return "".join("x" if t is None else
                   (str(t) if t < 10 else chr(ord("a") + t - 10))
                   for t in trastes)


def carriles_de_evento(evento, afinacion):
    """Carriles que ocupa un evento. Un acorde ocupa varios."""
    if evento.tipo == "nota":
        carril = carril_de_nota(evento.midi, afinacion, evento.cuerda)
        return () if carril is None else (carril,)
    carriles = {carril_de_nota(midi, afinacion) for midi in evento.midis}
    return tuple(sorted(c for c in carriles if c is not None))


def indice_carril(carril):
    """Columna en pantalla, 0 a la izquierda. La 6a cuerda va primera."""
    return CUERDAS - carril
