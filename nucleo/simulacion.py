"""Toca una pista con detecciones inventadas, para probar el evaluador.

Sirve para dos cosas: ver el evaluador funcionando sin microfono, y validar
de punta a punta que un bucle de 60 fps con el retardo real del motor no
inventa fallos cuando se toca bien.

Es logica pura y determinista: la unica fuente de azar es la semilla.
"""

import random
from dataclasses import dataclass

from audio.notas import midi_a_hz
from nucleo.evaluador import RETARDO_MOTOR_S, Deteccion


@dataclass(frozen=True)
class Perfil:
    """Como se toca la pista en la simulacion."""

    descripcion: str
    desfase_s: float = 0.0       # corrimiento sistematico; positivo = tarde
    jitter_s: float = 0.0        # variacion aleatoria del instante
    desviacion_cents: float = 0.0  # desafinacion sistematica
    jitter_cents: float = 0.0
    probabilidad_salto: float = 0.0   # notas que no se tocan
    notas_de_mas: int = 0             # detecciones sin evento que las pida


PERFILES = {
    "perfecto": Perfil("cada nota en su instante y afinada"),
    "tarde": Perfil("bien tocada pero 80 ms tarde de forma sistematica",
                    desfase_s=0.080),
    "desafinado": Perfil("a tiempo, pero 25 cents baja como la 4a cuerda real",
                         desviacion_cents=-25.0),
    # El jitter va a proposito por encima de las tolerancias por defecto
    # (120 ms y 35 cents) para que algunas notas caigan afuera y se vea que
    # las ventanas hacen algo.
    "desprolijo": Perfil("jitter de 160 ms y 45 cents, con notas salteadas "
                         "y de mas",
                         jitter_s=0.160, jitter_cents=45.0,
                         probabilidad_salto=0.15, notas_de_mas=3),
}


def generar_detecciones(pista, perfil, semilla=1):
    """Detecciones que produciria alguien tocando la pista con ese perfil."""
    azar = random.Random(semilla)
    detecciones = []
    for evento in pista.eventos:
        if azar.random() < perfil.probabilidad_salto:
            continue
        # De un acorde suena una sola lectura de pitch: la que gane en
        # periodicidad. Se elige una al azar entre sus notas.
        midi = azar.choice(evento.midis)
        t = evento.t + perfil.desfase_s + azar.uniform(-perfil.jitter_s,
                                                       perfil.jitter_s)
        cents = perfil.desviacion_cents + azar.uniform(-perfil.jitter_cents,
                                                       perfil.jitter_cents)
        detecciones.append(Deteccion(t=max(0.0, t),
                                     f0=midi_a_hz(midi) * 2.0 ** (cents / 1200.0)))

    for _ in range(perfil.notas_de_mas):
        detecciones.append(Deteccion(
            t=azar.uniform(0.0, max(pista.duracion, 0.1)),
            f0=midi_a_hz(azar.randint(40, 64))))

    return sorted(detecciones, key=lambda d: d.t)


def reproducir(evaluador, detecciones, duracion, fps=60,
               retardo_s=RETARDO_MOTOR_S):
    """Corre el evaluador como lo hara el juego y devuelve los resultados.

    Cada deteccion se entrega recien cuando el motor la habria emitido, es
    decir retardo_s despues de su timestamp. Es la parte que importa: si el
    evaluador cerrara las ventanas demasiado pronto, una pasada perfecta
    daria fallos aca.
    """
    pendientes = sorted(detecciones, key=lambda d: d.t)
    resultados = []
    paso = 1.0 / fps
    cuadros = int((duracion + retardo_s + evaluador.tolerancias.temporal_s
                   + 1.0) / paso) + 1
    for cuadro in range(cuadros):
        t = cuadro * paso
        listas, restantes = [], []
        for deteccion in pendientes:
            if deteccion.t + retardo_s <= t:
                listas.append(deteccion)
            else:
                restantes.append(deteccion)
        pendientes = restantes
        resultados.extend(evaluador.avanzar(t, listas))
        if evaluador.terminado and not pendientes:
            break
    return resultados
