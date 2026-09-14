#!/usr/bin/env python3
"""Diagnostico del motor de audio en vivo, antes de montar el juego encima.

Dos modos:

  ataques (por defecto)  Una linea por cada pulsacion detectada, con nota,
                         desviacion en cents, confianza y timestamp. Es el
                         entregable de la fase 1 y lo que consumira el juego.

  afinador               Lectura continua de pitch con barra de afinacion.
                         Sirve para comprobar que el microfono capta bien las
                         cuerdas graves y para afinar la guitarra.

  calibrar               Mide el ruido de sala y el nivel de la guitarra, y
                         sugiere los umbrales para *tu* microfono. Conviene
                         correrlo antes que nada.

Instalacion (Ubuntu):
    sudo apt install libportaudio2
    pip install numpy sounddevice

Uso:
    python3 detector_notas.py --lista           # ver dispositivos de entrada
    python3 detector_notas.py                   # modo ataques
    python3 detector_notas.py --calibrar        # medir umbrales de tu micro
    python3 detector_notas.py --afinador        # modo afinador
    python3 detector_notas.py --dispositivo 3   # forzar un dispositivo
    python3 detector_notas.py --umbral 0.006    # subir la puerta de ruido
    python3 detector_notas.py --sr 48000        # si el micro no acepta 44100
"""

import argparse
import sys

from audio.analizador import Analizador
from audio.calibracion import estadisticas, recomendar
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


def medir(captura, analizador, segundos, etiqueta):
    """Recolecta nivel y flujo por ventana durante unos segundos de audio."""
    niveles, flujos = [], []
    captura.vaciar()   # el audio acumulado durante el prompt no cuenta
    # Las primeras ventanas todavia tienen ceros en el buffer y falsearian
    # el piso de ruido hacia abajo.
    por_descartar = analizador.marco // analizador.salto
    t_inicio = None
    ultimo_aviso = None
    for bloque in captura.bloques():
        analizador.procesar(bloque)
        marco = analizador.ultimo_marco
        if marco is None:
            continue
        if por_descartar > 0:
            por_descartar -= 1
            t_inicio = analizador.t_actual
            continue
        niveles.append(marco.nivel)
        flujos.append(marco.flujo)
        restante = segundos - (analizador.t_actual - t_inicio)
        if restante <= 0:
            break
        if int(restante) + 1 != ultimo_aviso:
            ultimo_aviso = int(restante) + 1
            print(f"\r  {etiqueta}... {ultimo_aviso:2d} s   ", end="", flush=True)
    print(f"\r  {etiqueta}... listo      ")
    return niveles, flujos


def modo_calibrar(captura, analizador, segundos):
    print("Calibracion del microfono. Dos etapas, "
          f"{segundos} segundos cada una.")
    print()
    input("1) Silencio: no toques nada. Enter para empezar. ")
    nivel_silencio, flujo_silencio = medir(
        captura, analizador, segundos, "midiendo silencio")
    print()
    input("2) Guitarra: toca cuerdas al aire, una tras otra. Enter para empezar. ")
    nivel_tocando, flujo_tocando = medir(
        captura, analizador, segundos, "midiendo guitarra")

    silencio_n, tocando_n = estadisticas(nivel_silencio), estadisticas(nivel_tocando)
    silencio_f, tocando_f = estadisticas(flujo_silencio), estadisticas(flujo_tocando)
    recomendacion = recomendar(silencio_n, tocando_n, silencio_f, tocando_f)

    print()
    print(f"{'':<10} {'nivel mediana':>14} {'nivel p95':>10} {'nivel max':>10}"
          f" {'flujo mediana':>14} {'flujo p99':>10}")
    for etiqueta, n, f in (("silencio", silencio_n, silencio_f),
                           ("guitarra", tocando_n, tocando_f)):
        print(f"{etiqueta:<10} {n.mediana:14.4f} {n.p95:10.4f} {n.maximo:10.4f}"
              f" {f.mediana:14.2f} {f.p99:10.2f}")
    print()
    print(f"Separacion de nivel: {recomendacion.separacion_nivel:6.1f}x"
          "   (cuanto sube el volumen al tocar)")
    print(f"Separacion de flujo: {recomendacion.separacion_flujo:6.1f}x"
          "   (cuanto destacan los ataques)")
    print()
    for aviso in recomendacion.avisos:
        print(f"AVISO: {aviso}")
    if not recomendacion.avisos:
        print("El microfono separa bien la guitarra del ruido de sala.")
    print()
    print("Umbral sugerido para este microfono:")
    print(f"    python3 detector_notas.py --umbral {recomendacion.umbral:.4f}")
    if abs(recomendacion.factor - 6.0) > 1.5:
        print(f"Factor de onset sugerido: {recomendacion.factor:.1f} "
              "(el defecto es 6.0). Pasame este numero y lo ajusto.")
    return None


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
    ap.add_argument("--calibrar", action="store_true",
                    help="medir el ruido de sala y sugerir umbrales")
    ap.add_argument("--segundos", type=float, default=8.0,
                    help="duracion de cada etapa de la calibracion")
    ap.add_argument("--umbral", type=float, default=None,
                    help="puerta de ruido RMS (sube si detecta en silencio)")
    ap.add_argument("--sr", type=int, default=SR,
                    help=f"frecuencia de muestreo (por defecto {SR})")
    args = ap.parse_args()

    try:
        if args.lista:
            print(dispositivos())
            return
        opciones = {} if args.umbral is None else {"umbral_ruido": args.umbral}
        analizador = Analizador(sr=args.sr, **opciones)
        with Captura(sr=args.sr, bloque=BLOQUE,
                     dispositivo=args.dispositivo) as captura:
            try:
                if args.calibrar:
                    # Sin puerta de ruido: hay que poder medir el silencio.
                    analizador.umbral_ruido = 0.0
                    total = modo_calibrar(captura, analizador, args.segundos)
                elif args.afinador:
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
