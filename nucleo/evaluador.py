"""Evaluador: decide si una deteccion acierta un evento de la pista.

Es logica pura sobre numeros: no importa sounddevice ni pygame, y las
pruebas lo alimentan con detecciones inventadas.

Dos ventanas de tolerancia
--------------------------
Temporal: cuanto antes o despues del `t` esperado vale el golpe.
Afinacion: cuantos cents de desviacion se perdonan.

La desviacion se mide en cents contra la frecuencia exacta que se esperaba,
no comparando nombres de nota. Asi el limite se comporta bien en los bordes:
una nota 55 cents alta de E2 se detecta como F2 con -45 cents, y comparando
nombres parece estar a 45 cents de F2, cuando en realidad esta a 55 de lo
que se pedia. Lo que importa es la distancia a lo pedido.

Por que hay que esperar antes de dar una nota por perdida
--------------------------------------------------------
El motor de audio emite cada ataque bastante despues del golpe fisico: el
timestamp es temprano y correcto, pero el evento tarda en llegar porque el
pitch se mide unas ventanas mas tarde (ver audio/analizador.py). Si el
evaluador cerrara la ventana de un evento en el instante en que el reloj la
pasa, una deteccion legitima que todavia esta en camino llegaria tarde y la
nota contaria como fallo sin que nadie se equivocara.

Por eso la ventana se cierra recien cuando ya no puede llegar una deteccion
con timestamp dentro de ella. El margen se calcula desde las constantes del
analizador para que no puedan quedar desincronizados. La asimetria es
deliberada: cerrar tarde solo retrasa el aviso de fallo, cerrar temprano
inventa fallos, y eso ultimo es mucho peor.
"""

from dataclasses import dataclass

from audio.analizador import (RETARDO_ONSET_S, SALTO, SALTOS_VIDA, SR)
from audio.notas import cents_entre, midi_a_hz

ACIERTO = "acierto"
FALLO = "fallo"
EXTRA = "extra"

TOLERANCIA_TEMPORAL_S = 0.12
TOLERANCIA_CENTS = 35.0

# Peor caso de retraso entre el golpe y la emision del ataque: un pendiente
# puede vivir hasta SALTOS_VIDA saltos antes de cerrarse, y el timestamp ya
# viene corrido por RETARDO_ONSET_S.
RETARDO_MOTOR_S = SALTOS_VIDA * SALTO / SR + RETARDO_ONSET_S


@dataclass(frozen=True)
class Tolerancias:
    temporal_s: float = TOLERANCIA_TEMPORAL_S
    cents: float = TOLERANCIA_CENTS


@dataclass(frozen=True)
class Deteccion:
    """Lo que entrega el motor de audio, reducido a lo que el evaluador usa.

    Se guarda la frecuencia y no el par (nota, cents) porque la frecuencia es
    el dato exacto y evita decidir a que nota redondear antes de comparar.
    """

    t: float
    f0: float


@dataclass(frozen=True)
class Resultado:
    tipo: str                  # ACIERTO, FALLO o EXTRA
    indice: int = None         # evento de la pista; None en un EXTRA
    deteccion: Deteccion = None
    error_s: float = None      # deteccion.t - evento.t; positivo = tarde
    error_cents: float = None  # positivo = mas agudo de lo pedido


@dataclass(frozen=True)
class Resumen:
    total: int                     # eventos que tiene la pista
    aciertos: int
    fallos: int
    extras: int
    racha: int
    racha_maxima: int
    error_temporal_medio_s: float  # positivo = se toca tarde de forma sistematica
    error_cents_medio: float       # positivo = se toca agudo de forma sistematica


class Evaluador:
    """Se alimenta con avanzar(t_actual, detecciones) y devuelve resultados.

    `t_actual` es el reloj del motor de audio (segundos de audio consumidos),
    no el reloj de pared, por el mismo motivo que en el analizador: asi un
    tiron del hilo de render no adelanta el cierre de las ventanas.
    """

    def __init__(self, pista, tolerancias=None, retardo_motor_s=RETARDO_MOTOR_S):
        self.pista = pista
        self.tolerancias = tolerancias or Tolerancias()
        self.retardo_motor_s = retardo_motor_s

        self._pendientes = list(range(len(pista.eventos)))
        self._aciertos = 0
        self._fallos = 0
        self._extras = 0
        self._racha = 0
        self._racha_maxima = 0
        self._errores_s = []
        self._errores_cents = []

    # ------------------------------------------------------------------ API

    def avanzar(self, t_actual, detecciones=()):
        """Procesa detecciones nuevas y cierra las ventanas ya vencidas."""
        resultados = []
        # Las detecciones se ordenan por timestamp: el motor puede entregar
        # dos en el mismo bloque y el orden de emparejado cambia el resultado.
        for deteccion in sorted(detecciones, key=lambda d: d.t):
            resultados.append(self._emparejar(deteccion))
        resultados.extend(self._cerrar_vencidas(t_actual))
        return tuple(resultados)

    @property
    def terminado(self):
        """True cuando todos los eventos quedaron resueltos."""
        return not self._pendientes

    @property
    def resumen(self):
        return Resumen(
            total=len(self.pista.eventos),
            aciertos=self._aciertos,
            fallos=self._fallos,
            extras=self._extras,
            racha=self._racha,
            racha_maxima=self._racha_maxima,
            error_temporal_medio_s=_promedio(self._errores_s),
            error_cents_medio=_promedio(self._errores_cents),
        )

    def eventos_pendientes(self):
        """Indices de los eventos todavia sin resolver, en orden."""
        return tuple(self._pendientes)

    # -------------------------------------------------------------- interno

    def _desviacion(self, deteccion, evento):
        """Cents entre lo detectado y el pitch pedido mas cercano del evento.

        Un acorde tiene varios pitches y alcanza con acertar uno: con un
        detector monofonico como YIN, una rasgueada produce una sola lectura
        de pitch, la de la periodicidad mas fuerte. Exigir todas las notas
        necesita el detector de croma de la fase 5.
        """
        if deteccion.f0 <= 0.0:
            return None
        desviaciones = [cents_entre(deteccion.f0, midi_a_hz(midi))
                        for midi in evento.midis]
        return min(desviaciones, key=abs)

    def _emparejar(self, deteccion):
        for indice in self._pendientes:
            evento = self.pista.eventos[indice]
            if abs(deteccion.t - evento.t) > self.tolerancias.temporal_s:
                continue
            desviacion = self._desviacion(deteccion, evento)
            if desviacion is None or abs(desviacion) > self.tolerancias.cents:
                continue
            # Los pendientes estan en orden temporal, asi que el primero que
            # encaja es el mas antiguo: si el que viene antes quedo sin tocar,
            # se resolvera solo cuando su ventana venza.
            return self._acertar(indice, deteccion, desviacion)
        return self._extra(deteccion)

    def _acertar(self, indice, deteccion, desviacion):
        self._pendientes.remove(indice)
        evento = self.pista.eventos[indice]
        error_s = deteccion.t - evento.t
        self._aciertos += 1
        self._racha += 1
        self._racha_maxima = max(self._racha_maxima, self._racha)
        self._errores_s.append(error_s)
        self._errores_cents.append(desviacion)
        return Resultado(tipo=ACIERTO, indice=indice, deteccion=deteccion,
                         error_s=error_s, error_cents=desviacion)

    def _extra(self, deteccion):
        # Un extra no corta la racha. Con microfono integrado algunos falsos
        # positivos son inevitables, y castigarlos haria sentir el juego roto
        # cuando en realidad se toco bien.
        self._extras += 1
        return Resultado(tipo=EXTRA, deteccion=deteccion)

    def _cerrar_vencidas(self, t_actual):
        limite = t_actual - self.retardo_motor_s
        resultados = []
        for indice in list(self._pendientes):
            evento = self.pista.eventos[indice]
            if limite <= evento.t + self.tolerancias.temporal_s:
                continue
            self._pendientes.remove(indice)
            self._fallos += 1
            self._racha = 0
            resultados.append(Resultado(tipo=FALLO, indice=indice))
        return resultados


def _promedio(valores):
    return sum(valores) / len(valores) if valores else 0.0
