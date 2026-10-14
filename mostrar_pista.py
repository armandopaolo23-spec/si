#!/usr/bin/env python3
"""Carga una pista .json, la valida e imprime su linea de tiempo.

Es el entregable de la fase 2 y la forma de revisar una pista escrita a
mano antes de intentar tocarla.

Con --simular tambien la "toca" con detecciones inventadas y muestra como la
calificaria el evaluador, sin microfono.

Uso:
    python3 mostrar_pista.py pistas/01_cuerdas_al_aire.json
    python3 mostrar_pista.py pistas/*.json          # revisar todas
    python3 mostrar_pista.py pistas/02_escala_do_mayor.json --simular tarde
    python3 mostrar_pista.py pistas/02_escala_do_mayor.json --simular todos
"""

import argparse
import sys

from audio.notas import hz_a_nota, nombre_midi
from nucleo.evaluador import (ACIERTO, AFINACION, EXTRA, Evaluador,
                              Tolerancias)
from nucleo.pista import PistaInvalida, cargar
from nucleo.simulacion import PERFILES, generar_detecciones, reproducir


def columna_notas(evento):
    """Notas del evento en notacion inglesa, compacta."""
    if evento.tipo == "nota":
        return nombre_midi(evento.midi)
    return " ".join(nombre_midi(midi) for midi in evento.notas)


def columna_detalle(evento):
    if evento.tipo == "acorde":
        return f"acorde {evento.nombre}"
    if evento.cuerda is None or evento.traste is None:
        return "digitacion libre"
    return f"{evento.cuerda}a cuerda, traste {evento.traste}"


def mostrar(pista):
    print(pista.titulo)
    print(f"{pista.bpm:g} bpm | afinacion "
          + " ".join(nombre_midi(m) for m in pista.afinacion)
          + f" | {len(pista.eventos)} eventos | {pista.duracion:.2f} s")
    print()
    print(f"{'#':>3}  {'t (s)':>7} {'pulso':>7} {'dur':>6}  {'tipo':<7} "
          f"{'notas':<26} detalle")
    for indice, evento in enumerate(pista.eventos):
        print(f"{indice:>3}  {evento.t:7.3f} {pista.pulso(evento.t):7.2f} "
              f"{evento.dur:6.2f}  {evento.tipo:<7} "
              f"{columna_notas(evento):<26} {columna_detalle(evento)}")

    notas = sum(1 for e in pista.eventos if e.tipo == "nota")
    acordes = len(pista.eventos) - notas
    print()
    print(f"Resumen: {notas} notas, {acordes} acordes.")
    if pista.eventos:
        agudos = max(max(e.midis) for e in pista.eventos)
        graves = min(min(e.midis) for e in pista.eventos)
        print(f"Rango: {nombre_midi(graves)} a {nombre_midi(agudos)}.")


def instante(pista, resultado):
    """Momento que corresponde mostrar para un resultado."""
    if resultado.deteccion is not None:
        return resultado.deteccion.t
    return pista.eventos[resultado.indice].t


def describir(pista, resultado):
    if resultado.tipo == ACIERTO:
        evento = pista.eventos[resultado.indice]
        return (f"{resultado.deteccion.t:7.3f}  ACIERTO  "
                f"evento {resultado.indice:>2} ({columna_notas(evento)})  "
                f"{1000 * resultado.error_s:+6.1f} ms  "
                f"{resultado.error_cents:+6.1f} cents")

    if resultado.tipo == EXTRA:
        sono = hz_a_nota(resultado.deteccion.f0).nombre
        if resultado.motivo != AFINACION:
            return (f"{resultado.deteccion.t:7.3f}  EXTRA    "
                    f"sono {sono} y no habia nada pedido ahi")
        # Aca estaba lo importante: decir "no habia nada pedido" cuando si
        # habia algo pedido y solo fallo la afinacion es enganoso, y son dos
        # errores que se corrigen de forma distinta.
        evento = pista.eventos[resultado.indice]
        direccion = "agudo" if resultado.error_cents > 0 else "grave"
        return (f"{resultado.deteccion.t:7.3f}  EXTRA    "
                f"evento {resultado.indice:>2} "
                f"({columna_notas(evento)}) pedido a "
                f"{1000 * resultado.error_s:+.0f} ms, pero sono {sono} "
                f"{abs(resultado.error_cents):.0f} cents {direccion}")

    evento = pista.eventos[resultado.indice]
    return (f"{evento.t:7.3f}  FALLO    "
            f"evento {resultado.indice:>2} ({columna_notas(evento)})  "
            f"no se toco")


def simular(pista, nombre_perfil, tolerancias, semilla):
    perfil = PERFILES[nombre_perfil]
    evaluador = Evaluador(pista, tolerancias=tolerancias)
    detecciones = generar_detecciones(pista, perfil, semilla=semilla)
    resultados = reproducir(evaluador, detecciones, pista.duracion)

    print(f"--- simulacion '{nombre_perfil}': {perfil.descripcion}")
    # Se ordena por el instante que se muestra, no por el orden en que el
    # evaluador los produjo, para que el registro se lea cronologicamente.
    for resultado in sorted(resultados, key=lambda r: instante(pista, r)):
        print("    " + describir(pista, resultado))

    r = evaluador.resumen
    print(f"    resumen: {r.aciertos}/{r.total} aciertos, {r.fallos} fallos, "
          f"{r.extras} de mas, racha maxima {r.racha_maxima}")
    if r.aciertos:
        ms = 1000 * r.error_temporal_medio_s
        tiempo = ("clavado en tiempo" if abs(ms) < 5 else
                  f"{abs(ms):.0f} ms {'tarde' if ms > 0 else 'temprano'}")
        cents = r.error_cents_medio
        afinacion = ("afinado" if abs(cents) < 3 else
                     f"{abs(cents):.0f} cents "
                     f"{'agudo' if cents > 0 else 'grave'}")
        print(f"    en promedio: {tiempo}, {afinacion}")
    print()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rutas", nargs="+", help="archivos .json de pista")
    ap.add_argument("--simular", choices=sorted(PERFILES) + ["todos"],
                    help="tocar la pista con detecciones inventadas y "
                         "mostrar como la califica el evaluador")
    ap.add_argument("--tolerancia-ms", type=float, default=None,
                    help="ventana temporal en milisegundos")
    ap.add_argument("--tolerancia-cents", type=float, default=None,
                    help="ventana de afinacion en cents")
    ap.add_argument("--semilla", type=int, default=1,
                    help="semilla de la simulacion")
    args = ap.parse_args()

    por_defecto = Tolerancias()
    tolerancias = Tolerancias(
        temporal_s=(por_defecto.temporal_s if args.tolerancia_ms is None
                    else args.tolerancia_ms / 1000.0),
        cents=(por_defecto.cents if args.tolerancia_cents is None
               else args.tolerancia_cents))

    fallos = 0
    for indice, ruta in enumerate(args.rutas):
        if indice:
            print()
            print("-" * 72)
            print()
        try:
            pista = cargar(ruta)
            mostrar(pista)
            if args.simular:
                print()
                perfiles = (sorted(PERFILES) if args.simular == "todos"
                            else [args.simular])
                print(f"Tolerancias: {1000 * tolerancias.temporal_s:.0f} ms, "
                      f"{tolerancias.cents:.0f} cents")
                print()
                for nombre in perfiles:
                    simular(pista, nombre, tolerancias, args.semilla)
        except PistaInvalida as error:
            print(error, file=sys.stderr)
            fallos += 1
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
