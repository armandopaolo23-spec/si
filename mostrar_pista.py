#!/usr/bin/env python3
"""Carga una pista .json, la valida e imprime su linea de tiempo.

Es el entregable de la fase 2 y la forma de revisar una pista escrita a
mano antes de intentar tocarla.

Uso:
    python3 mostrar_pista.py pistas/01_cuerdas_al_aire.json
    python3 mostrar_pista.py pistas/*.json          # revisar todas
"""

import argparse
import sys

from audio.notas import nombre_midi
from nucleo.pista import PistaInvalida, cargar


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


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rutas", nargs="+", help="archivos .json de pista")
    args = ap.parse_args()

    fallos = 0
    for indice, ruta in enumerate(args.rutas):
        if indice:
            print()
            print("-" * 72)
            print()
        try:
            mostrar(cargar(ruta))
        except PistaInvalida as error:
            print(error, file=sys.stderr)
            fallos += 1
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
