"""Puntaje. Funcion pura: los puntos de un acierto dependen de la racha."""

PUNTOS_ACIERTO = 100
BONUS_POR_RACHA = 10
RACHA_MAXIMA_BONIFICADA = 10


def puntos_por_acierto(racha):
    """Puntos de un acierto que deja la racha en `racha`.

    La bonificacion crece con la racha y se corta en
    RACHA_MAXIMA_BONIFICADA: sin tope, una pista larga tocada bien daria
    numeros enormes y los primeros aciertos dejarian de significar nada.
    """
    bonus = BONUS_POR_RACHA * min(max(racha - 1, 0), RACHA_MAXIMA_BONIFICADA)
    return PUNTOS_ACIERTO + bonus
