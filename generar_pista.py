#!/usr/bin/env python3
"""Genera pistas de escalas y progresiones, y las deja listas para el juego.

Las pistas se escriben en pistas/generadas/ y aparecen solas en el menu de
tocar.py. Van aparte de las de ejemplo para no mezclarse con ellas.

Uso:
    python3 generar_pista.py escala G mayor
    python3 generar_pista.py escala Sol mayor --octavas 2
    python3 generar_pista.py escala A pentatonica_menor
    python3 generar_pista.py progresion G D Em C
    python3 generar_pista.py progresion Am C G --vueltas 2
    python3 generar_pista.py progresion Em C --bpm 80 --pulsos 6

Tipos de escala: mayor, menor, pentatonica_mayor, pentatonica_menor.
Acordes disponibles: los que reconoce el detector (Em E Am A C G D).
"""

import argparse
import pathlib
import re
import sys

from audio.notas import NOMBRES
from juego.geometria import VENTANA_VISTA_S
from mostrar_pista import mostrar
from nucleo.generador import (BPM, ESCALAS, PULSOS_POR_ACORDE, a_json,
                              clase_de_tono, escala, progresion)
from nucleo.pista import advertencias_de_ritmo, desde_dict

CARPETA = pathlib.Path("pistas/generadas")


def nombre_de_archivo(partes):
    """Nombre seguro para el sistema de archivos: F# pasa a Fs."""
    texto = "_".join(str(p) for p in partes).replace("#", "s")
    return re.sub(r"[^A-Za-z0-9_]", "", texto) + ".json"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="que", required=True)

    a_escala = sub.add_parser("escala", help="escala subiendo y bajando")
    a_escala.add_argument("tono", help="tonica: G, F#, Bb, Sol, Fa#...")
    a_escala.add_argument("tipo", nargs="?", default="mayor",
                          choices=sorted(ESCALAS))
    a_escala.add_argument("--octavas", type=int, default=1, choices=(1, 2))

    a_prog = sub.add_parser("progresion", help="progresion de acordes")
    a_prog.add_argument("acordes", nargs="+", help="por ejemplo: G D Em C")
    a_prog.add_argument("--vueltas", type=int, default=1)
    a_prog.add_argument("--pulsos", type=int, default=PULSOS_POR_ACORDE,
                        help="pulsos entre un acorde y el siguiente")

    for parser in (a_escala, a_prog):
        parser.add_argument("--bpm", type=float, default=BPM)
        parser.add_argument("--salida", help="ruta del .json a escribir")
        parser.add_argument("--forzar", action="store_true",
                            help="sobrescribir si el archivo ya existe")
    args = ap.parse_args()

    try:
        if args.que == "escala":
            datos = escala(args.tono, args.tipo, octavas=args.octavas,
                           bpm=args.bpm)
            partes = ["escala", args.tipo, NOMBRES[clase_de_tono(args.tono)]]
            if args.octavas == 2:
                partes.append("2oct")
        else:
            datos = progresion(args.acordes, vueltas=args.vueltas,
                               bpm=args.bpm, pulsos_por_acorde=args.pulsos)
            partes = ["progresion", *args.acordes]
            if args.vueltas > 1:
                partes.append(f"{args.vueltas}vueltas")
    except ValueError as error:
        print(f"No se pudo generar: {error}", file=sys.stderr)
        sys.exit(1)

    if args.bpm != BPM:
        partes.append(f"{args.bpm:g}bpm")
    ruta = pathlib.Path(args.salida) if args.salida \
        else CARPETA / nombre_de_archivo(partes)
    if ruta.exists() and not args.forzar:
        print(f"Ya existe {ruta}. Usa --forzar para sobrescribirla.",
              file=sys.stderr)
        sys.exit(1)

    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(a_json(datos), encoding="utf-8")

    pista = desde_dict(datos, origen=str(ruta))
    mostrar(pista)
    print()
    avisos = advertencias_de_ritmo(pista, VENTANA_VISTA_S)
    if avisos:
        print("Ojo, va mas rapido de lo que conviene para empezar:")
        for aviso in avisos:
            print(f"  - {aviso}")
        print()
    print(f"Guardada en {ruta}. Aparece en el menu de tocar.py.")


if __name__ == "__main__":
    main()
