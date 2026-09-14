"""Modelo de pista: carga y validacion del JSON que describe un ejercicio.

Las pistas se escriben a mano, asi que la validacion es la parte importante
de este modulo: un JSON con un error tipografico tiene que decir exactamente
que evento esta mal y por que, y tiene que informar *todos* los errores de
una pasada. Reportar solo el primero obliga a corregir de uno en uno.

Sobre el tiempo: `t` es el instante del ataque y es lo que el evaluador
compara. `dur` es cuanto deberia sonar la nota, y sirve para dibujarla; se
permite que la duracion de un evento pise el `t` del siguiente, porque en
musica real una cuerda sigue sonando mientras se toca la siguiente. Lo que
no se permite es que dos eventos compartan el mismo `t`: dos notas
simultaneas son un acorde, y ahi el tipo de evento es "acorde".
"""

import json
import math
from dataclasses import dataclass, field

from audio.notas import CUERDAS_ESTANDAR, hz_a_midi, nombre_a_midi, nombre_midi
from audio.yin import FMAX, FMIN

# Rango de notas que el detector puede oir. Se deriva de los limites de YIN
# en vez de escribirse a mano, para que no puedan quedar desincronizados: una
# pista con notas fuera de este rango seria imposible de acertar.
MIDI_MINIMO = math.ceil(hz_a_midi(FMIN))
MIDI_MAXIMO = math.floor(hz_a_midi(FMAX))

TIPOS = ("nota", "acorde")
CUERDAS = 6
TRASTE_MAXIMO = 24
NOTAS_MINIMAS_ACORDE = 2


class PistaInvalida(ValueError):
    """Agrupa todos los errores encontrados en una pista."""

    def __init__(self, errores, origen=None):
        self.errores = tuple(errores)
        self.origen = origen
        cabecera = "Pista invalida" + (f" ({origen}):" if origen else ":")
        super().__init__("\n".join([cabecera] + [f"  - {e}" for e in self.errores]))


@dataclass(frozen=True)
class EventoNota:
    """Una nota suelta. cuerda y traste son solo sugerencia de digitacion."""

    t: float
    dur: float
    midi: int
    cuerda: int = None
    traste: int = None

    @property
    def tipo(self):
        return "nota"

    @property
    def fin(self):
        return self.t + self.dur

    @property
    def midis(self):
        """Pitches que hay que oir para acertar este evento."""
        return (self.midi,)


@dataclass(frozen=True)
class EventoAcorde:
    """Un acorde. notas son los pitches que suenan, ya ordenados y sin repetir."""

    t: float
    dur: float
    nombre: str
    notas: tuple

    @property
    def tipo(self):
        return "acorde"

    @property
    def fin(self):
        return self.t + self.dur

    @property
    def midis(self):
        return self.notas


@dataclass(frozen=True)
class Pista:
    titulo: str
    bpm: float
    afinacion: tuple = field(default=CUERDAS_ESTANDAR)
    eventos: tuple = field(default=())

    @property
    def duracion(self):
        """Segundos hasta que termina de sonar el ultimo evento."""
        return max((evento.fin for evento in self.eventos), default=0.0)

    def pulso(self, t):
        """Numero de pulso (beat) en el que cae un instante, base 0."""
        return t * self.bpm / 60.0


def _es_numero(valor):
    # bool es subclase de int en Python, y JSON tiene true/false: si no se
    # excluye, {"t": true} pasaria como t = 1.
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _es_entero(valor):
    return isinstance(valor, int) and not isinstance(valor, bool)


def _validar_cabecera(datos, errores):
    titulo = datos.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        errores.append("'titulo' falta o no es texto no vacio")
        titulo = ""

    bpm = datos.get("bpm")
    if not _es_numero(bpm) or bpm <= 0:
        errores.append(f"'bpm' debe ser un numero mayor que 0, es {bpm!r}")
        bpm = 0.0

    if "afinacion" not in datos:
        afinacion, afinacion_valida = CUERDAS_ESTANDAR, True   # la estandar
    else:
        previos = len(errores)
        afinacion = _validar_afinacion(datos["afinacion"], errores)
        afinacion_valida = len(errores) == previos

    return str(titulo).strip(), float(bpm), afinacion, afinacion_valida


def _validar_afinacion(valor, errores):
    if not isinstance(valor, list) or len(valor) != CUERDAS:
        errores.append(
            f"'afinacion' debe ser una lista de {CUERDAS} nombres de nota "
            f"de la 6a a la 1a cuerda, es {valor!r}")
        return CUERDAS_ESTANDAR
    midis = []
    for indice, nombre in enumerate(valor):
        try:
            midis.append(nombre_a_midi(nombre))
        except ValueError as error:
            errores.append(f"'afinacion'[{indice}]: {error}")
            return CUERDAS_ESTANDAR
    return tuple(midis)


def _validar_midi(valor, etiqueta, errores):
    """Devuelve el midi si es valido y esta al alcance del detector, o None."""
    if not _es_entero(valor):
        errores.append(f"{etiqueta} debe ser un numero MIDI entero, es {valor!r}")
        return None
    if not MIDI_MINIMO <= valor <= MIDI_MAXIMO:
        errores.append(
            f"{etiqueta} = {valor} ({nombre_midi(valor)}) queda fuera de lo que "
            f"el detector puede oir: {MIDI_MINIMO} ({nombre_midi(MIDI_MINIMO)}) "
            f"a {MIDI_MAXIMO} ({nombre_midi(MIDI_MAXIMO)})")
        return None
    return valor


def _validar_digitacion(datos, etiqueta, errores):
    """cuerda y traste son opcionales; si estan, tienen que tener sentido."""
    cuerda = datos.get("cuerda")
    if cuerda is not None and not (_es_entero(cuerda) and 1 <= cuerda <= CUERDAS):
        errores.append(
            f"{etiqueta}: 'cuerda' debe ser un entero de 1 (la mas aguda) a "
            f"{CUERDAS} (la mas grave), es {cuerda!r}")
        cuerda = None
    traste = datos.get("traste")
    if traste is not None and not (_es_entero(traste)
                                   and 0 <= traste <= TRASTE_MAXIMO):
        errores.append(
            f"{etiqueta}: 'traste' debe ser un entero de 0 a "
            f"{TRASTE_MAXIMO}, es {traste!r}")
        traste = None
    return cuerda, traste


def _coherencia_digitacion(evento, afinacion, indice, errores):
    """Comprueba que la digitacion sugerida de verdad produzca ese pitch.

    cuerda y traste son solo una sugerencia y el evaluador acepta cualquier
    digitacion, pero una sugerencia equivocada confundiria a quien toca: si
    no coincide con el midi, uno de los dos campos es un error de tipeo.
    """
    if evento.cuerda is None or evento.traste is None:
        return
    esperado = afinacion[CUERDAS - evento.cuerda] + evento.traste
    if esperado != evento.midi:
        errores.append(
            f"evento {indice}: la digitacion sugerida (cuerda {evento.cuerda}, "
            f"traste {evento.traste}) da {nombre_midi(esperado)} con esta "
            f"afinacion, pero 'midi' pide {nombre_midi(evento.midi)}")


def _validar_evento(datos, indice, errores):
    """Devuelve el evento, o None si tenia errores."""
    etiqueta = f"evento {indice}"
    if not isinstance(datos, dict):
        errores.append(f"{etiqueta} no es un objeto: {datos!r}")
        return None

    tipo = datos.get("tipo")
    if tipo not in TIPOS:
        errores.append(f"{etiqueta}: 'tipo' debe ser uno de {TIPOS}, es {tipo!r}")
        return None

    t = datos.get("t")
    if not _es_numero(t) or t < 0:
        errores.append(f"{etiqueta}: 't' debe ser un numero >= 0, es {t!r}")
        t = None
    dur = datos.get("dur")
    if not _es_numero(dur) or dur <= 0:
        errores.append(f"{etiqueta}: 'dur' debe ser un numero > 0, es {dur!r}")
        dur = None

    if tipo == "nota":
        midi = _validar_midi(datos.get("midi"), f"{etiqueta}: 'midi'", errores)
        cuerda, traste = _validar_digitacion(datos, etiqueta, errores)
        if None in (t, dur, midi):
            return None
        return EventoNota(t=float(t), dur=float(dur), midi=midi,
                          cuerda=cuerda, traste=traste)

    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip():
        errores.append(f"{etiqueta}: 'nombre' del acorde falta o no es texto")
        nombre = None

    crudas = datos.get("notas")
    notas = None
    if not isinstance(crudas, list):
        errores.append(f"{etiqueta}: 'notas' debe ser una lista, es {crudas!r}")
    elif len(crudas) < NOTAS_MINIMAS_ACORDE:
        errores.append(
            f"{etiqueta}: un acorde necesita al menos "
            f"{NOTAS_MINIMAS_ACORDE} notas, tiene {len(crudas)}")
    else:
        validas = [_validar_midi(valor, f"{etiqueta}: 'notas'[{i}]", errores)
                   for i, valor in enumerate(crudas)]
        if None not in validas:
            # Se ordenan y se quitan repetidas: para acertar el acorde lo que
            # importa es el conjunto de pitches, y la misma nota puede caer en
            # dos cuerdas distintas.
            notas = tuple(sorted(set(validas)))

    if None in (t, dur, nombre, notas):
        return None
    return EventoAcorde(t=float(t), dur=float(dur), nombre=nombre.strip(),
                        notas=notas)


def _validar_orden(eventos, errores):
    for anterior, siguiente in zip(eventos, eventos[1:]):
        if siguiente.t < anterior.t:
            errores.append(
                f"los eventos deben ir ordenados por 't': "
                f"{siguiente.t} viene despues de {anterior.t}")
        elif siguiente.t == anterior.t:
            errores.append(
                f"hay dos eventos en t = {anterior.t}. Dos notas simultaneas "
                f"son un acorde: usa un evento de tipo 'acorde'")


def desde_dict(datos, origen=None):
    """Construye una Pista validada a partir de un diccionario ya parseado."""
    if not isinstance(datos, dict):
        raise PistaInvalida(
            [f"la pista debe ser un objeto JSON, es {type(datos).__name__}"],
            origen)

    errores = []
    titulo, bpm, afinacion, afinacion_valida = _validar_cabecera(datos, errores)

    crudos = datos.get("eventos")
    eventos = []
    if not isinstance(crudos, list):
        errores.append(f"'eventos' debe ser una lista, es {crudos!r}")
    elif not crudos:
        errores.append("'eventos' esta vacio: la pista no tiene nada que tocar")
    else:
        for indice, crudo in enumerate(crudos):
            evento = _validar_evento(crudo, indice, errores)
            if evento is not None:
                # Si la afinacion no era valida se usa la estandar de
                # respaldo, y comparar contra ella inventaria errores de
                # digitacion que la pista no tiene.
                if evento.tipo == "nota" and afinacion_valida:
                    _coherencia_digitacion(evento, afinacion, indice, errores)
                eventos.append(evento)
        # El orden solo se puede revisar entre los eventos que si son validos.
        _validar_orden(eventos, errores)

    if errores:
        raise PistaInvalida(errores, origen)
    return Pista(titulo=titulo, bpm=bpm, afinacion=afinacion,
                 eventos=tuple(eventos))


def cargar(ruta):
    """Lee y valida una pista desde un archivo .json."""
    try:
        texto = open(ruta, encoding="utf-8").read()
    except OSError as error:
        raise PistaInvalida([f"no se pudo leer el archivo: {error}"], str(ruta))
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as error:
        raise PistaInvalida(
            [f"el JSON esta mal formado en la linea {error.lineno}, "
             f"columna {error.colno}: {error.msg}"], str(ruta))
    return desde_dict(datos, origen=str(ruta))
