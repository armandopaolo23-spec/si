#!/usr/bin/env python3
"""Diagnostico del motor de audio en vivo, antes de montar el juego encima.

Dos modos:

  ataques (por defecto)  Una linea por cada pulsacion detectada, con nota,
                         desviacion en cents, confianza y timestamp. Es el
                         entregable de la fase 1 y lo que consumira el juego.

  afinador               Lectura continua de pitch con barra de afinacion.
                         Sirve para comprobar que el microfono capta bien las
                         cuerdas graves y para afinar la guitarra.

Instalacion (Ubuntu):
    sudo apt install libportaudio2
    pip install numpy sounddevice

Uso:
    python3 detector_notas.py --lista           # ver dispositivos de entrada
    python3 detector_notas.py                   # modo ataques
    python3 detector_notas.py --afinador        # modo afinador
    python3 detector_notas.py --dispositivo 3   # forzar un dispositivo
    python3 detector_notas.py --umbral 0.006    # subir la puerta de ruido
"""

import argparse
import sys

from audio.analizador import Analizador
from audio.captura import BLOQUE, SR, Captura, dispositivos
from audio.notas import CUERDAS_ESTANDAR, hz_a_nota, midi_a_hz, nombre_midi


def barra_afinacion(cents, ancho=21):
    """Barra visual: el centro es la nota afinada, +-50 cents a los lados."""
    centro = ancho // 2
    posicion = int(round(centro + (cents / 50.0) * centro))
    posicion = max(0, min(ancho - 1, posicion))
    celdas = ["-"] * ancho
    celdas[centro] = "|"
    celdas[posicion] = "#"
    return "".join(celdas)


def referencia_cuerdas():
    return ", ".join(
        f"{6 - i}a {nombre_midi(m)}={midi_a_hz(m):.2f} Hz"
        for i, m in enumerate(CUERDAS_ESTANDAR)
    )


def modo_ataques(captura, analizador):
    print("Modo ataques. Toca notas sueltas. Ctrl+C para salir.")
    print("Referencia:", referencia_cuerdas())
    print()
    print(f"{'t (s)':>8}  {'nota':<11} {'Hz':>8}  {'cents':>7}  {'conf':>5}  {'nivel':>7}")
    total = 0
    for bloque in captura.bloques():
        for ataque in analizador.procesar(bloque):
            total += 1
            nota = ataque.nota
            print(f"{ataque.t:8.3f}  {nota.nombre + ' (' + nota.nombre_es + ')':<11} "
                  f"{ataque.f0:8.2f}  {nota.cents:+7.1f}  "
                  f"{ataque.confianza:5.2f}  {ataque.nivel:7.4f}")
    return total


def modo_afinador(captura, analizador):
    print("Modo afinador. Toca una cuerda y sostenla. Ctrl+C para salir.")
    print("Referencia:", referencia_cuerdas())
    print()
    for bloque in captura.bloques():
        analizador.procesar(bloque)
        marco = analizador.ultimo_marco
        if marco is None:
            continue
        if marco.nivel < analizador.umbral_ruido:
            texto = f"{'(silencio)':<44}"
        elif marco.f0 <= 0.0 or marco.confianza < analizador.conf_minima:
            texto = f"{'(sin tono claro)':<44}"
        else:
            nota = hz_a_nota(marco.f0)
            etiqueta = f"{nota.nombre} ({nota.nombre_es})"
            texto = (f"{etiqueta:<12} {barra_afinacion(nota.cents)} "
                     f"{nota.cents:+6.1f}c  {marco.f0:7.2f} Hz  "
                     f"conf {marco.confianza:.2f}")
        print(f"\r{texto}  nivel {marco.nivel:.4f}   ", end="", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lista", action="store_true",
                    help="listar dispositivos de entrada y salir")
    ap.add_argument("--dispositivo", type=int, default=None,
                    help="indice del dispositivo de entrada")
    ap.add_argument("--afinador", action="store_true",
                    help="modo afinador en vez de modo ataques")
    ap.add_argument("--umbral", type=float, default=None,
                    help="puerta de ruido RMS (sube si detecta en silencio)")
    args = ap.parse_args()

    try:
        if args.lista:
            print(dispositivos())
            return
        opciones = {} if args.umbral is None else {"umbral_ruido": args.umbral}
        analizador = Analizador(sr=SR, **opciones)
        with Captura(sr=SR, bloque=BLOQUE, dispositivo=args.dispositivo) as captura:
            try:
                if args.afinador:
                    total = modo_afinador(captura, analizador)
                else:
                    total = modo_ataques(captura, analizador)
            except KeyboardInterrupt:
                total = None
            print()
            resumen(analizador, captura, total)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        sys.exit(1)


def resumen(analizador, captura, total):
    print()
    print(f"Audio analizado: {analizador.t_actual:.1f} s")
    print(f"Nivel maximo registrado: {analizador.pico_nivel:.4f}")
    if total:
        print(f"Ataques detectados: {total}")
    if analizador.descartados:
        print(f"Ataques sin pitch claro (descartados): {analizador.descartados}")
    if captura.descartes:
        print(f"AVISO: {captura.descartes} bloques descartados, el analisis no "
              "alcanzo el ritmo del audio y los timestamps se corrieron.")
    if captura.avisos:
        print(f"AVISO de PortAudio: {sorted(set(captura.avisos))}")
    if analizador.pico_nivel < 0.01:
        print("Con la 6a cuerda el nivel no paso de ~0.01: el microfono esta "
              "cortando los graves. Acerca la laptop a la boca de la guitarra "
              "o sube la ganancia de entrada.")


if __name__ == "__main__":
    main()
