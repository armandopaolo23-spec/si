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

from audio.analizador import (RETARDO_ONSET_S, SALTO, SALTOS_ACORDE,
                              SALTOS_VIDA, SR)
from audio.notas import cents_entre, midi_a_hz
from nucleo.acordes import reconocer

ACIERTO = "acierto"
FALLO = "fallo"
EXTRA = "extra"

# Por que una deteccion no acerto nada. Distinguirlos importa: "sono algo que
# no se pedia" y "sono lo que se pedia pero desafinado" se corrigen de formas
# distintas, y confundirlos hace parecer que el juego esta roto.
SIN_EVENTO = "sin_evento"
AFINACION = "afinacion"
ACORDE_INCOMPLETO = "acorde_incompleto"

TOLERANCIA_TEMPORAL_S = 0.12
# Un rasgueo no es un instante sino un barrido: las seis cuerdas no suenan
# juntas. Con rasgueos sintetizados el onset llega a correrse 160 ms respecto
# del comienzo, asi que los acordes llevan una ventana mas ancha; con la de
# las notas sueltas se perderian rasgueos bien tocados.
TOLERANCIA_TEMPORAL_ACORDE_S = 0.25
TOLERANCIA_CENTS = 35.0

# Peor caso de retraso entre el golpe y la emision del ataque. El ataque se
# emite recien cuando la ventana armonica esta llena, porque hasta entonces no
# se puede saber si fue una nota o un rasgueo.
RETARDO_MOTOR_S = max(SALTOS_VIDA, SALTOS_ACORDE) * SALTO / SR + RETARDO_ONSET_S


@dataclass(frozen=True)
class Tolerancias:
    temporal_s: float = TOLERANCIA_TEMPORAL_S
    cents: float = TOLERANCIA_CENTS
    temporal_acorde_s: float = TOLERANCIA_TEMPORAL_ACORDE_S

    def ventana(self, evento):
        """Ventana temporal que le corresponde a un evento."""
        return (self.temporal_acorde_s if evento.tipo == "acorde"
                else self.temporal_s)


@dataclass(frozen=True)
class Deteccion:
    """Lo que entrega el motor de audio, reducido a lo que el evaluador usa.

    Se guarda la frecuencia y no el par (nota, cents) porque la frecuencia es
    el dato exacto y evita decidir a que nota redondear antes de comparar.

    `energias` es la energia por semitono que mide audio/croma.py, y es lo
    unico que sirve para juzgar un rasgueo: un acorde no tiene una frecuencia
    fundamental que YIN pueda medir, asi que ahi `f0` viene en None.
    """

    t: float
    f0: float = None
    energias: object = None


@dataclass(frozen=True)
class Resultado:
    tipo: str                  # ACIERTO, FALLO o EXTRA
    indice: int = None         # evento de la pista
    deteccion: Deteccion = None
    error_s: float = None      # deteccion.t - evento.t; positivo = tarde
    error_cents: float = None  # positivo = mas agudo de lo pedido
    motivo: str = None         # solo en un EXTRA: SIN_EVENTO o AFINACION
    faltantes: tuple = ()      # en un acorde, los midis que no sonaron
    nombre_oido: str = None    # en un acorde, a que acorde se parecio

    # En un EXTRA con motivo AFINACION, `indice` apunta al evento que estuvo
    # cerca en tiempo pero no se acepto por desviacion, y error_s y
    # error_cents dicen por cuanto. Ese evento igual produce su propio FALLO
    # cuando vence su ventana: son dos hechos distintos.


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
        """Cents entre lo detectado y el pitch pedido mas cercano del evento."""
        if not deteccion.f0:
            return None
        desviaciones = [cents_entre(deteccion.f0, midi_a_hz(midi))
                        for midi in evento.midis]
        return min(desviaciones, key=abs)

    def _juzgar_nota(self, deteccion, evento):
        """(acepta, desviacion) para un evento de nota suelta."""
        desviacion = self._desviacion(deteccion, evento)
        if desviacion is None:
            return False, None
        return abs(desviacion) <= self.tolerancias.cents, desviacion

    def _emparejar(self, deteccion):
        cercano = None        # nota que fallo solo por afinacion
        acorde_fallado = None  # acorde que estaba ahi pero no sono completo
        for indice in self._pendientes:
            evento = self.pista.eventos[indice]
            if abs(deteccion.t - evento.t) > self.tolerancias.ventana(evento):
                continue

            if evento.tipo == "acorde":
                reconocimiento = reconocer(deteccion.energias, evento.midis,
                                           nombre=evento.nombre)
                if reconocimiento.acertado:
                    # Los pendientes estan en orden temporal, asi que el
                    # primero que encaja es el mas antiguo.
                    return self._acertar(indice, deteccion, 0.0,
                                         reconocimiento)
                # Se guarda igual: saber que cuerdas faltaron es la
                # devolucion que sirve, y es justo cuando el acorde falla.
                if (acorde_fallado is None
                        or reconocimiento.fraccion > acorde_fallado[1].fraccion):
                    acorde_fallado = (indice, reconocimiento)
                continue

            acepta, desviacion = self._juzgar_nota(deteccion, evento)
            if desviacion is None:
                continue
            if acepta:
                return self._acertar(indice, deteccion, desviacion)
            if cercano is None or abs(desviacion) < abs(cercano[1]):
                cercano = (indice, desviacion)
        return self._extra(deteccion, cercano, acorde_fallado)

    def _acertar(self, indice, deteccion, desviacion, reconocimiento=None):
        self._pendientes.remove(indice)
        evento = self.pista.eventos[indice]
        error_s = deteccion.t - evento.t
        self._aciertos += 1
        self._racha += 1
        self._racha_maxima = max(self._racha_maxima, self._racha)
        self._errores_s.append(error_s)
        # Un acorde no tiene una desviacion de afinacion que promediar: se
        # juzga por que notas suenan, no por cuanto se desvia una sola.
        if reconocimiento is None:
            self._errores_cents.append(desviacion)
        return Resultado(
            tipo=ACIERTO, indice=indice, deteccion=deteccion,
            error_s=error_s, error_cents=desviacion,
            faltantes=reconocimiento.faltantes if reconocimiento else (),
            nombre_oido=reconocimiento.nombre_oido if reconocimiento else None)

    def _extra(self, deteccion, cercano=None, acorde_fallado=None):
        # Un extra no corta la racha. Con microfono integrado algunos falsos
        # positivos son inevitables, y castigarlos haria sentir el juego roto
        # cuando en realidad se toco bien.
        self._extras += 1
        if acorde_fallado is not None:
            indice, reconocimiento = acorde_fallado
            return Resultado(tipo=EXTRA, indice=indice, deteccion=deteccion,
                             motivo=ACORDE_INCOMPLETO,
                             error_s=deteccion.t - self.pista.eventos[indice].t,
                             faltantes=reconocimiento.faltantes,
                             nombre_oido=reconocimiento.nombre_oido)
        if cercano is None:
            return Resultado(tipo=EXTRA, deteccion=deteccion,
                             motivo=SIN_EVENTO)
        indice, desviacion = cercano
        evento = self.pista.eventos[indice]
        return Resultado(tipo=EXTRA, indice=indice, deteccion=deteccion,
                         error_s=deteccion.t - evento.t,
                         error_cents=desviacion, motivo=AFINACION)

    def _cerrar_vencidas(self, t_actual):
        limite = t_actual - self.retardo_motor_s
        resultados = []
        for indice in list(self._pendientes):
            evento = self.pista.eventos[indice]
            if limite <= evento.t + self.tolerancias.ventana(evento):
                continue
            self._pendientes.remove(indice)
            self._fallos += 1
            self._racha = 0
            resultados.append(Resultado(tipo=FALLO, indice=indice))
        return resultados


def _promedio(valores):
    return sum(valores) / len(valores) if valores else 0.0
