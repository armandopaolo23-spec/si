"""Generador procedural de pistas: escalas y progresiones de acordes.

Produce el mismo diccionario que se escribiria a mano en un .json, y lo pasa
por el validador de nucleo/pista.py antes de devolverlo, asi que una pista
generada nunca puede ser invalida.

Los valores por defecto siguen el ritmo de los ejercicios de ejemplo: una
nota por pulso a 60 bpm, y siete pulsos entre acordes. Con otros parametros
la pista puede salir mas rapida; sigue siendo valida, y
nucleo.pista.advertencias_de_ritmo dice si conviene para empezar.
"""

import json

from audio.notas import ESPANOL, NOMBRES, nombre_a_midi
from nucleo.acordes import ACORDES_ABIERTOS
from nucleo.pista import desde_dict

# Intervalos en semitonos desde la tonica.
ESCALAS = {
    "mayor": (0, 2, 4, 5, 7, 9, 11),
    "menor": (0, 2, 3, 5, 7, 8, 10),
    "pentatonica_mayor": (0, 2, 4, 7, 9),
    "pentatonica_menor": (0, 3, 5, 7, 10),
}

# La tonica se ubica en la primera octava que empiece en la 6a cuerda al aire
# o mas arriba: asi la escala queda en primera posicion y sin notas que la
# guitarra en afinacion estandar no alcance.
MIDI_MAS_GRAVE = 40           # E2, 6a cuerda al aire

BPM = 60
PULSOS_POR_ACORDE = 7         # a 60 bpm, 7 s entre acordes como el ejercicio 3
PULSOS_DE_ENTRADA = 4         # el primer acorde no cae apenas empieza

_LATINOS = {"do": "C", "re": "D", "mi": "E", "fa": "F",
            "sol": "G", "la": "A", "si": "B"}


def clase_de_tono(tono):
    """Clase de nota (0-11) de una tonica en notacion inglesa o latina.

    Acepta "G", "F#", "Bb", "Sol", "fa#", "Sib". Lanza ValueError con un
    mensaje en español si no la reconoce.
    """
    if not isinstance(tono, str) or not tono.strip():
        raise ValueError("falta la tonica")
    texto = tono.strip()
    minuscula = texto.lower()
    for latino, letra in sorted(_LATINOS.items(), key=lambda par: -len(par[0])):
        if minuscula.startswith(latino):
            texto = letra + texto[len(latino):]
            break
    else:
        texto = texto[0].upper() + texto[1:]
    try:
        return nombre_a_midi(texto + "4") % 12
    except ValueError:
        raise ValueError(
            f"tonica no reconocida: {tono!r} (se espera algo como G, F#, Bb, "
            "Sol o Fa#)") from None


def _segundos(pulsos, bpm):
    return round(pulsos * 60.0 / bpm, 3)


def escala(tono, tipo="mayor", octavas=1, bpm=BPM):
    """Escala subiendo y bajando, una nota por pulso.

    Igual que el ejercicio 2: la nota de arriba se sostiene un poco mas y
    deja un pulso de aire antes de bajar, y la ultima suena larga.
    """
    if tipo not in ESCALAS:
        raise ValueError(f"tipo de escala desconocido: {tipo!r}. "
                         f"Hay: {', '.join(ESCALAS)}")
    if octavas not in (1, 2):
        raise ValueError(f"octavas tiene que ser 1 o 2, es {octavas!r}")
    if bpm <= 0:
        raise ValueError(f"bpm tiene que ser mayor que 0, es {bpm!r}")

    clase = clase_de_tono(tono)
    tonica = MIDI_MAS_GRAVE + (clase - MIDI_MAS_GRAVE) % 12
    subida = [tonica + 12 * octava + intervalo
              for octava in range(octavas) for intervalo in ESCALAS[tipo]]
    subida.append(tonica + 12 * octavas)
    bajada = list(reversed(subida[:-1]))

    eventos = []
    pulso = 0
    for indice, midi in enumerate(subida):
        arriba = indice == len(subida) - 1
        eventos.append(_nota(_segundos(pulso, bpm),
                             _segundos(1.6 if arriba else 0.9, bpm), midi))
        pulso += 2 if arriba else 1
    for indice, midi in enumerate(bajada):
        ultima = indice == len(bajada) - 1
        eventos.append(_nota(_segundos(pulso, bpm),
                             _segundos(2.0 if ultima else 0.9, bpm), midi))
        pulso += 1

    nombre_tipo = tipo.replace("_", " ")
    titulo = f"Escala {nombre_tipo} de {ESPANOL[clase]} ({NOMBRES[clase]})"
    if octavas == 2:
        titulo += ", dos octavas"
    return _validar({"titulo": titulo, "bpm": bpm, "eventos": eventos})


def progresion(acordes, vueltas=1, bpm=BPM, pulsos_por_acorde=PULSOS_POR_ACORDE):
    """Progresion de acordes abiertos, repetida y resuelta en el primero.

    Termina volviendo al primer acorde porque es como cierra una progresion:
    G D Em C suena incompleta si se corta en C.
    """
    if not acordes:
        raise ValueError("la progresion necesita al menos un acorde")
    desconocidos = [a for a in acordes if a not in ACORDES_ABIERTOS]
    if desconocidos:
        raise ValueError(
            f"acordes sin plantilla: {', '.join(desconocidos)}. "
            f"El detector reconoce: {', '.join(ACORDES_ABIERTOS)}")
    if vueltas < 1:
        raise ValueError(f"vueltas tiene que ser al menos 1, es {vueltas!r}")
    if pulsos_por_acorde < 2:
        raise ValueError("pulsos_por_acorde tiene que ser al menos 2")
    if bpm <= 0:
        raise ValueError(f"bpm tiene que ser mayor que 0, es {bpm!r}")

    secuencia = list(acordes) * vueltas + [acordes[0]]
    # El acorde suena una parte del tramo y deja aire para mover la mano.
    sostenido = max(1, min(4, pulsos_por_acorde - 2))
    eventos = []
    for indice, nombre in enumerate(secuencia):
        ultimo = indice == len(secuencia) - 1
        eventos.append({
            "t": _segundos(PULSOS_DE_ENTRADA + indice * pulsos_por_acorde, bpm),
            "dur": _segundos(5 if ultimo else sostenido, bpm),
            "tipo": "acorde",
            "nombre": nombre,
            "notas": list(ACORDES_ABIERTOS[nombre]),
        })

    titulo = "Progresion " + " ".join(acordes)
    if vueltas > 1:
        titulo += f", {vueltas} vueltas"
    return _validar({"titulo": titulo, "bpm": bpm, "eventos": eventos})


def a_json(datos):
    """Texto JSON con un evento por linea, como las pistas escritas a mano.

    json.dumps con indentacion pone cada nota de un acorde en su propia
    linea y vuelve la pista ilegible; asi se puede editar a mano despues.
    """
    lineas = ["{"]
    for clave in ("titulo", "bpm", "afinacion"):
        if clave in datos:
            lineas.append(f"  {json.dumps(clave)}: "
                          f"{json.dumps(datos[clave], ensure_ascii=False)},")
    lineas.append('  "eventos": [')
    eventos = [json.dumps(e, ensure_ascii=False) for e in datos["eventos"]]
    lineas.extend(f"    {texto}," for texto in eventos[:-1])
    lineas.append(f"    {eventos[-1]}")
    lineas.append("  ]")
    lineas.append("}")
    return "\n".join(lineas) + "\n"


def _nota(t, dur, midi):
    return {"t": t, "dur": dur, "tipo": "nota", "midi": midi}


def _validar(datos):
    """Pasa la pista por el validador: lo que sale de aca siempre carga."""
    desde_dict(datos, origen="generador")
    return datos
