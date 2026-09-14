#!/usr/bin/env python3
"""Juego: baja la pista en pantalla y escucha la guitarra por el microfono.

Requiere pygame, que no hace falta para las fases anteriores:
    pip install -r requirements.txt

Uso:
    python3 tocar.py                       # todas las pistas de pistas/
    python3 tocar.py pistas/01_*.json      # solo las que se indiquen
    python3 tocar.py --dispositivo 3
    python3 tocar.py --umbral 0.004        # el que sugiera --calibrar
    python3 tocar.py --vista 2.0           # segundos de pista en pantalla

Controles:
    menu        flechas para elegir, Enter para tocar, Esc para salir
    jugando     Esc para volver al menu
    resultados  Enter para el menu, R para repetir
"""

import argparse
import glob
import sys

from audio.analizador import SR
from nucleo.evaluador import Tolerancias
from nucleo.pista import PistaInvalida, cargar


def rutas_de_pistas(argumentos):
    if argumentos:
        return argumentos
    encontradas = sorted(glob.glob("pistas/*.json"))
    if not encontradas:
        raise SystemExit("No hay pistas en pistas/. Indica los archivos a mano.")
    return encontradas


def avisar_falta_pygame(error):
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"No se pudo cargar pygame: {error}", file=sys.stderr)
    print(file=sys.stderr)
    print("Con el entorno virtual activo:", file=sys.stderr)
    print("    python3 -m venv .venv", file=sys.stderr)
    print("    source .venv/bin/activate", file=sys.stderr)
    print("    pip install -r requirements.txt", file=sys.stderr)
    print(file=sys.stderr)
    print(f"Estas usando Python {version}. Si pip falla con "
          "'externally-managed-environment' es que falta activar el entorno "
          "virtual: Ubuntu no deja instalar con pip en el Python del sistema.",
          file=sys.stderr)
    if sys.version_info >= (3, 14):
        print(file=sys.stderr)
        print(f"Ojo: pygame 2.6.1 publica wheels hasta CPython 3.13, asi que "
              f"en Python {version} habria que compilarlo. requirements.txt "
              "usa pygame-ce, que si tiene wheel y es reemplazo directo.",
              file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rutas", nargs="*", help="archivos .json de pista")
    ap.add_argument("--dispositivo", type=int, default=None,
                    help="indice del dispositivo de entrada")
    ap.add_argument("--sr", type=int, default=SR,
                    help=f"frecuencia de muestreo (por defecto {SR})")
    ap.add_argument("--umbral", type=float, default=None,
                    help="puerta de ruido RMS; usa el valor de --calibrar")
    ap.add_argument("--vista", type=float, default=None,
                    help="segundos de pista visibles (por defecto 3)")
    ap.add_argument("--tolerancia-ms", type=float, default=None,
                    help="ventana temporal en milisegundos")
    ap.add_argument("--tolerancia-cents", type=float, default=None,
                    help="ventana de afinacion en cents")
    args = ap.parse_args()

    try:
        pistas = [cargar(ruta) for ruta in rutas_de_pistas(args.rutas)]
    except PistaInvalida as error:
        print(error, file=sys.stderr)
        sys.exit(1)

    por_defecto = Tolerancias()
    tolerancias = Tolerancias(
        temporal_s=(por_defecto.temporal_s if args.tolerancia_ms is None
                    else args.tolerancia_ms / 1000.0),
        cents=(por_defecto.cents if args.tolerancia_cents is None
               else args.tolerancia_cents))

    # Se importa aca y no arriba para que --help funcione sin pygame puesto.
    try:
        from juego.aplicacion import ejecutar
    except ImportError as error:
        avisar_falta_pygame(error)
        sys.exit(1)
    try:
        analizador, sesion = ejecutar(
            pistas, dispositivo=args.dispositivo, sr=args.sr,
            umbral_ruido=args.umbral, tolerancias=tolerancias,
            ventana_vista_s=args.vista)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        sys.exit(1)

    print(f"Audio analizado: {analizador.t_actual:.1f} s")
    print(f"Nivel maximo registrado: {analizador.pico_nivel:.4f}")
    if analizador.pico_nivel < 0.01:
        print("El nivel no paso de 0.01: el microfono esta cortando los "
              "graves. Corre  python3 detector_notas.py --calibrar")


if __name__ == "__main__":
    main()
