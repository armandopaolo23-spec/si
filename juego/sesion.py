"""Maquina de estados del juego: menu, jugando y resultados.

Es logica pura: no importa pygame ni sounddevice. El render consume el modelo
de vista que produce esta clase, asi que el juego se puede probar entero sin
ventana y sin microfono.

Sobre los dos relojes
---------------------
El motor de audio cuenta segundos de audio consumidos desde que se abrio el
stream; la pista cuenta segundos desde que empieza el ejercicio. La sesion
traduce entre los dos, y la resta se aplica tambien a los timestamps de las
detecciones: si se compararan contra el reloj equivocado, el evaluador veria
todo fuera de tiempo.

El ejercicio arranca con el reloj de pista en -ventana_vista_s, de modo que
la primera nota entra por arriba de la pantalla justo cuando empieza. Asi no
hace falta una cuenta regresiva aparte.
"""

from dataclasses import dataclass

from audio.notas import hz_a_nota
from juego.geometria import (MARGEN_SALIDA_S, VENTANA_VISTA_S,
                             asignacion_de_acorde, carril_de_nota,
                             carriles_de_evento, en_vista)
from nucleo.evaluador import (ACIERTO, ACORDE_INCOMPLETO, AFINACION, EXTRA,
                              FALLO, Deteccion, Evaluador, Tolerancias)
from nucleo.puntaje import puntos_por_acierto

MENU = "menu"
JUGANDO = "jugando"
RESULTADOS = "resultados"

PENDIENTE = "pendiente"
ACERTADA = "acertada"
FALLADA = "fallada"

DURACION_AVISO_S = 0.7      # cuanto queda en pantalla una devolucion
MS_PERFECTO = 30.0          # por debajo de esto el acierto se llama perfecto
CENTS_PERFECTO = 12.0


@dataclass(frozen=True)
class NotaEnVista:
    """Una nota que toca dibujar en este cuadro."""

    indice: int
    evento: object
    restante: float      # segundos hasta que hay que tocarla; negativo = pasada
    estado: str          # PENDIENTE, ACERTADA o FALLADA
    carriles: tuple


@dataclass(frozen=True)
class Aviso:
    """Devolucion momentanea junto a la linea de golpe."""

    t_pista: float
    tipo: str            # ACIERTO, FALLO o EXTRA
    texto: str
    carril: int


class Sesion:
    def __init__(self, pistas, tolerancias=None,
                 ventana_vista_s=VENTANA_VISTA_S, desfase_s=0.0):
        if not pistas:
            raise ValueError("la sesion necesita al menos una pista")
        self.pistas = tuple(pistas)
        self.tolerancias = tolerancias or Tolerancias()
        self.ventana_vista_s = ventana_vista_s
        # Compensacion personal: cuanto se corre cada deteccion antes de
        # compararla. Positivo = quien toca se adelanta, asi que se empujan
        # hacia adelante. Es distinto de retardo_onset_s del analizador: ese
        # corrige un sesgo de medicion del detector y se calibra contra
        # señales con instante conocido; este corrige como se sincroniza una
        # persona con lo que ve en pantalla, y es distinto para cada una.
        self.desfase_s = desfase_s

        self.estado = MENU
        self.seleccion = 0
        self.t_pista = 0.0
        self.puntaje = 0
        self.avisos = []

        self._evaluador = None
        self._t_inicio = 0.0
        self._estados = {}

    # ------------------------------------------------------------------ menu

    @property
    def pista_actual(self):
        return self.pistas[self.seleccion]

    def mover_seleccion(self, delta):
        if self.estado == MENU:
            self.seleccion = (self.seleccion + delta) % len(self.pistas)

    # --------------------------------------------------------------- jugando

    def empezar(self, t_audio):
        """Arranca el ejercicio elegido. t_audio es el reloj del motor."""
        self.estado = JUGANDO
        self.puntaje = 0
        self.avisos = []
        self._estados = {}
        self._evaluador = Evaluador(self.pista_actual,
                                    tolerancias=self.tolerancias)
        # El reloj de pista empieza en negativo para que la primera nota
        # entre por arriba justo ahora.
        self._t_inicio = t_audio + self.ventana_vista_s
        self.t_pista = -self.ventana_vista_s

    def avanzar(self, t_audio, ataques=()):
        """Adelanta el reloj, evalua los ataques nuevos y devuelve resultados."""
        if self.estado != JUGANDO:
            return ()

        self.t_pista = t_audio - self._t_inicio
        detecciones = []
        for ataque in ataques:
            t = ataque.t - self._t_inicio + self.desfase_s
            # Lo que suena durante la entrada, antes de la primera nota, no
            # se evalua: seria afinar o acomodarse, no tocar la pista.
            if t >= -self.tolerancias.temporal_s:
                detecciones.append(Deteccion(t=t, f0=ataque.f0,
                                             energias=ataque.energias))

        resultados = self._evaluador.avanzar(self.t_pista, detecciones)
        for resultado in resultados:
            self._registrar(resultado)
        self._podar_avisos()

        if self._evaluador.terminado and self.t_pista > self.pista_actual.duracion:
            self.estado = RESULTADOS
        return resultados

    def al_menu(self):
        self.estado = MENU

    def reintentar(self, t_audio):
        self.empezar(t_audio)

    # ---------------------------------------------------------- modelo vista

    def notas_en_vista(self):
        afinacion = self.pista_actual.afinacion
        vistas = []
        for indice, evento in enumerate(self.pista_actual.eventos):
            restante = evento.t - self.t_pista
            if not en_vista(restante, self.ventana_vista_s, MARGEN_SALIDA_S):
                continue
            vistas.append(NotaEnVista(
                indice=indice,
                evento=evento,
                restante=restante,
                estado=self._estados.get(indice, PENDIENTE),
                carriles=carriles_de_evento(evento, afinacion),
            ))
        return tuple(vistas)

    def acorde_a_la_vista(self):
        """Acorde que conviene mostrar en el diagrama lateral, o None.

        Es el primero que todavia no quedo atras: mientras se acerca sirve
        para armar la mano, y un rato despues de tocarlo sigue visible para
        comprobar la posicion. Una pista de solo punteo no devuelve ninguno
        y el diagrama no se dibuja.
        """
        limite = self.t_pista - MARGEN_SALIDA_S
        for evento in self.pista_actual.eventos:
            if evento.tipo == "acorde" and evento.t >= limite:
                return evento
        return None

    def avisos_vigentes(self):
        return tuple(self.avisos)

    @property
    def resumen(self):
        return self._evaluador.resumen if self._evaluador else None

    @property
    def desfase_sugerido_ms(self):
        """Compensacion que centraria el sesgo temporal medido, en ms.

        Suma la compensacion ya aplicada, asi que el valor sirve tal cual
        aunque se venga de una pasada que ya usaba desfase.
        """
        resumen = self.resumen
        if resumen is None or not resumen.aciertos:
            return 0
        return round(1000 * (self.desfase_s - resumen.error_temporal_medio_s))

    @property
    def progreso(self):
        """Fraccion de la pista ya recorrida, entre 0 y 1."""
        duracion = self.pista_actual.duracion
        if duracion <= 0:
            return 1.0
        return min(max(self.t_pista / duracion, 0.0), 1.0)

    # -------------------------------------------------------------- interno

    def _registrar(self, resultado):
        if resultado.tipo == ACIERTO:
            self._estados[resultado.indice] = ACERTADA
            self.puntaje += puntos_por_acierto(self._evaluador.resumen.racha)
            self._avisar(resultado, self._texto_acierto(resultado))
        elif resultado.tipo == FALLO:
            self._estados[resultado.indice] = FALLADA
            self._avisar(resultado, "FALLO")
        else:
            self._avisar(resultado, self._texto_extra(resultado))

    def _cuerdas_faltantes(self, resultado):
        """Nombres de las cuerdas que no sonaron en un acorde, de grave a aguda."""
        if resultado.indice is None or not resultado.faltantes:
            return ()
        evento = self.pista_actual.eventos[resultado.indice]
        if evento.tipo != "acorde":
            return ()
        asignacion = asignacion_de_acorde(evento.notas,
                                          self.pista_actual.afinacion)
        cuerdas = sorted(asignacion[midi][0] for midi in resultado.faltantes
                         if midi in asignacion)
        return tuple(f"{cuerda}a" for cuerda in reversed(cuerdas))

    def _texto_acierto(self, resultado):
        faltantes = self._cuerdas_faltantes(resultado)
        if faltantes:
            return "falta " + " ".join(faltantes)
        if resultado.error_cents is None:
            return "PERFECTO"
        ms = 1000 * resultado.error_s
        if abs(ms) <= MS_PERFECTO and abs(resultado.error_cents) <= CENTS_PERFECTO:
            return "PERFECTO"
        if abs(ms) > MS_PERFECTO:
            return f"{ms:+.0f} ms"
        return f"{resultado.error_cents:+.0f} cents"

    def _texto_extra(self, resultado):
        if resultado.motivo == ACORDE_INCOMPLETO:
            faltantes = self._cuerdas_faltantes(resultado)
            if faltantes:
                return "falta " + " ".join(faltantes)
            return (f"sono {resultado.nombre_oido}"
                    if resultado.nombre_oido else "acorde incompleto")
        if resultado.motivo == AFINACION:
            direccion = "ALTO" if resultado.error_cents > 0 else "BAJO"
            return f"{abs(resultado.error_cents):.0f}c {direccion}"
        if not resultado.deteccion.f0:
            return "rasgueo de mas"
        return f"{hz_a_nota(resultado.deteccion.f0).nombre} de mas"

    def _carril_de_resultado(self, resultado):
        afinacion = self.pista_actual.afinacion
        if resultado.indice is not None:
            carriles = carriles_de_evento(
                self.pista_actual.eventos[resultado.indice], afinacion)
            if carriles:
                return carriles[0]
        if resultado.deteccion is not None and resultado.deteccion.f0:
            # Una nota de mas se muestra en el carril de la cuerda que la
            # habria producido: dice de paso que cuerda cree que se toco.
            carril = carril_de_nota(hz_a_nota(resultado.deteccion.f0).midi,
                                    afinacion)
            if carril is not None:
                return carril
        return 1

    def _avisar(self, resultado, texto):
        self.avisos.append(Aviso(t_pista=self.t_pista, tipo=resultado.tipo,
                                 texto=texto,
                                 carril=self._carril_de_resultado(resultado)))

    def _podar_avisos(self):
        limite = self.t_pista - DURACION_AVISO_S
        self.avisos = [a for a in self.avisos if a.t_pista > limite]
