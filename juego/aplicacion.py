"""Bucle principal: une captura de audio, analisis, sesion y render.

Reparto de hilos, que es la parte delicada:

- El callback de sounddevice corre en un hilo de tiempo real y solo copia el
  bloque a una cola. No analiza nada.
- Este bucle, en el hilo principal, drena la cola una vez por cuadro, pasa
  las muestras al analizador y le entrega los ataques a la sesion. Drenar no
  bloquea: si no hay audio nuevo, el cuadro se dibuja igual.

El reloj del juego es el del audio (segundos de audio consumidos) y no el de
pared. Asi un tiron del render no adelanta las notas ni corre las ventanas de
tolerancia. La contra es que si el microfono deja de entregar audio el juego
se congela, asi que eso se detecta y se avisa en pantalla.
"""

import time

import pygame

from audio.analizador import SR, Analizador
from audio.captura import BLOQUE, Captura
from juego.render import ALTO, ANCHO, Renderizador
from juego.sesion import JUGANDO, MENU, RESULTADOS, Sesion

FPS = 60
ESPERA_AVISO_AUDIO_S = 1.0     # sin audio nuevo por mas de esto, se avisa


def _manejar_teclado(evento, sesion, analizador):
    """Devuelve False si hay que cerrar el juego."""
    if evento.key == pygame.K_ESCAPE:
        if sesion.estado == JUGANDO:
            sesion.al_menu()
            return True
        return False

    if sesion.estado == MENU:
        if evento.key in (pygame.K_UP, pygame.K_LEFT):
            sesion.mover_seleccion(-1)
        elif evento.key in (pygame.K_DOWN, pygame.K_RIGHT):
            sesion.mover_seleccion(1)
        elif evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            sesion.empezar(analizador.t_actual)
    elif sesion.estado == RESULTADOS:
        if evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            sesion.al_menu()
        elif evento.key == pygame.K_r:
            sesion.reintentar(analizador.t_actual)
    return True


def ejecutar(pistas, dispositivo=None, sr=SR, umbral_ruido=None,
             tolerancias=None, ventana_vista_s=None):
    opciones = {} if umbral_ruido is None else {"umbral_ruido": umbral_ruido}
    analizador = Analizador(sr=sr, **opciones)

    argumentos = {}
    if tolerancias is not None:
        argumentos["tolerancias"] = tolerancias
    if ventana_vista_s is not None:
        argumentos["ventana_vista_s"] = ventana_vista_s
    sesion = Sesion(pistas, **argumentos)

    pygame.init()
    pantalla = pygame.display.set_mode((ANCHO, ALTO))
    pygame.display.set_caption("Tutor de guitarra")
    reloj = pygame.time.Clock()
    renderizador = Renderizador(pantalla)

    try:
        with Captura(sr=sr, bloque=BLOQUE, dispositivo=dispositivo) as captura:
            t_ultimo_audio = time.monotonic()
            t_audio_previo = -1.0
            corriendo = True
            while corriendo:
                for evento in pygame.event.get():
                    if evento.type == pygame.QUIT:
                        corriendo = False
                    elif evento.type == pygame.KEYDOWN:
                        corriendo = _manejar_teclado(evento, sesion, analizador)

                ataques = []
                for bloque in captura.drenar():
                    ataques.extend(analizador.procesar(bloque))
                sesion.avanzar(analizador.t_actual, ataques)

                if analizador.t_actual > t_audio_previo:
                    t_audio_previo = analizador.t_actual
                    t_ultimo_audio = time.monotonic()
                silencio = time.monotonic() - t_ultimo_audio
                renderizador.aviso_sistema = (
                    f"sin audio del microfono desde hace {silencio:.0f} s"
                    if silencio > ESPERA_AVISO_AUDIO_S else None)

                renderizador.dibujar(sesion)
                pygame.display.flip()
                reloj.tick(FPS)
    finally:
        pygame.quit()

    return analizador, sesion
