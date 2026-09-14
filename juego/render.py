"""Dibujo con pygame. Es la unica parte del juego que sabe de pantallas.

No decide nada: toma el modelo de vista que produce juego/sesion.py y lo
dibuja. Por eso la logica del juego se puede probar sin abrir ventana.
"""

import pygame

from audio.notas import nombre_midi
from juego.geometria import indice_carril, posicion_relativa
from juego.sesion import (ACERTADA, FALLADA, JUGANDO, MENU, RESULTADOS)
from nucleo.evaluador import ACIERTO, EXTRA, FALLO
from nucleo.pista import CUERDAS

ANCHO, ALTO = 960, 640
FONDO = (18, 20, 28)
PANEL = (26, 29, 40)
TEXTO = (222, 226, 236)
TEXTO_TENUE = (128, 134, 150)
LINEA_GOLPE = (238, 240, 248)
ACENTO = (96, 186, 255)

VERDE = (90, 208, 132)
ROJO = (232, 94, 104)
AMBAR = (238, 186, 84)

# Un color por cuerda, de la 6a a la 1a. Sirve para leer el highway de un
# vistazo sin tener que mirar el nombre de la nota.
COLORES_CUERDA = [
    (208, 108, 96), (214, 152, 88), (206, 200, 96),
    (122, 198, 122), (110, 168, 226), (176, 132, 224),
]
# Los acordes llevan un color neutro, fuera de la escala de colores de las
# cuerdas: con el color prestado de una de sus cuerdas, un acorde y una nota
# suelta de esa cuerda se veian practicamente iguales. Un tono claro y sin
# matiz lee bien como "todas las cuerdas".
COLOR_ACORDE = (216, 216, 228)

MARGEN_LATERAL = 150
ALTURA_LINEA = 0.80        # fraccion de la pantalla donde esta la linea
ALTO_NOTA = 26
CABECERA = 96


class Renderizador:
    def __init__(self, pantalla):
        self.pantalla = pantalla
        self.ancho, self.alto = pantalla.get_size()
        self.fuente_titulo = pygame.font.Font(None, 44)
        self.fuente = pygame.font.Font(None, 28)
        self.fuente_chica = pygame.font.Font(None, 22)
        self.fuente_nota = pygame.font.Font(None, 20)
        # Lo pone la aplicacion cuando hay algo que contar del sistema, por
        # ejemplo que el microfono dejo de entregar audio.
        self.aviso_sistema = None

    # ------------------------------------------------------------ geometria

    @property
    def y_linea(self):
        return int(self.alto * ALTURA_LINEA)

    @property
    def ancho_carril(self):
        return (self.ancho - 2 * MARGEN_LATERAL) / CUERDAS

    def x_carril(self, carril):
        """Centro horizontal de un carril. La 6a cuerda va a la izquierda."""
        return MARGEN_LATERAL + self.ancho_carril * (indice_carril(carril) + 0.5)

    def y_de(self, restante, ventana_vista):
        alto_util = self.y_linea - CABECERA
        return CABECERA + alto_util * posicion_relativa(restante, ventana_vista)

    # --------------------------------------------------------------- estados

    def dibujar(self, sesion):
        self.pantalla.fill(FONDO)
        if sesion.estado == MENU:
            self._menu(sesion)
        elif sesion.estado == JUGANDO:
            self._juego(sesion)
        elif sesion.estado == RESULTADOS:
            self._resultados(sesion)
        if self.aviso_sistema:
            self._centrado(self.aviso_sistema, self.ancho // 2,
                           self.alto - 54, self.fuente_chica, AMBAR)

    def _menu(self, sesion):
        self._texto("Tutor de guitarra", (MARGEN_LATERAL, 70),
                    self.fuente_titulo)
        self._texto("Flechas para elegir, Enter para tocar, Esc para salir",
                    (MARGEN_LATERAL, 118), self.fuente_chica, TEXTO_TENUE)

        y = 190
        for indice, pista in enumerate(sesion.pistas):
            elegida = indice == sesion.seleccion
            rect = pygame.Rect(MARGEN_LATERAL - 20, y - 14,
                               self.ancho - 2 * MARGEN_LATERAL + 40, 62)
            if elegida:
                pygame.draw.rect(self.pantalla, PANEL, rect, border_radius=8)
                pygame.draw.rect(self.pantalla, ACENTO, rect, width=2,
                                 border_radius=8)
            self._texto(pista.titulo, (MARGEN_LATERAL, y),
                        self.fuente, TEXTO if elegida else TEXTO_TENUE)
            notas = sum(1 for e in pista.eventos if e.tipo == "nota")
            acordes = len(pista.eventos) - notas
            detalle = (f"{pista.bpm:g} bpm   {notas} notas"
                       + (f"   {acordes} acordes" if acordes else "")
                       + f"   {pista.duracion:.0f} s")
            self._texto(detalle, (MARGEN_LATERAL, y + 28), self.fuente_chica,
                        TEXTO_TENUE)
            y += 84

    def _juego(self, sesion):
        pista = sesion.pista_actual
        self._carriles(pista)
        self._linea_de_golpe()
        self._notas(sesion)
        self._avisos(sesion)
        self._cabecera(sesion)
        self._pie(sesion)

    def _carriles(self, pista):
        for carril in range(1, CUERDAS + 1):
            x = self.x_carril(carril)
            color = COLORES_CUERDA[indice_carril(carril)]
            pygame.draw.line(self.pantalla, _oscurecer(color, 0.28),
                             (x, CABECERA), (x, self.y_linea), 1)
            etiqueta = f"{carril}a  {nombre_midi(pista.afinacion[CUERDAS - carril])}"
            self._centrado(etiqueta, x, self.y_linea + 22, self.fuente_chica,
                           _oscurecer(color, 0.75))

    def _notas(self, sesion):
        for vista in sesion.notas_en_vista():
            if not vista.carriles:
                continue
            y = self.y_de(vista.restante, sesion.ventana_vista_s)
            izquierda = self.x_carril(max(vista.carriles)) - self.ancho_carril * 0.38
            derecha = self.x_carril(min(vista.carriles)) + self.ancho_carril * 0.38
            rect = pygame.Rect(izquierda, y - ALTO_NOTA / 2,
                               derecha - izquierda, ALTO_NOTA)

            base = (COLOR_ACORDE if vista.evento.tipo == "acorde"
                    else COLORES_CUERDA[indice_carril(vista.carriles[0])])
            if vista.estado == ACERTADA:
                relleno, borde = _oscurecer(VERDE, 0.45), VERDE
            elif vista.estado == FALLADA:
                relleno, borde = _oscurecer(ROJO, 0.4), ROJO
            else:
                relleno, borde = _oscurecer(base, 0.55), base

            pygame.draw.rect(self.pantalla, relleno, rect, border_radius=6)
            pygame.draw.rect(self.pantalla, borde, rect, width=2,
                             border_radius=6)
            etiqueta = (vista.evento.nombre if vista.evento.tipo == "acorde"
                        else nombre_midi(vista.evento.midi))
            self._en_el_centro(etiqueta, rect.center, self.fuente_nota)

    def _linea_de_golpe(self):
        y = self.y_linea
        pygame.draw.line(self.pantalla, LINEA_GOLPE,
                         (MARGEN_LATERAL - 30, y), (self.ancho - MARGEN_LATERAL + 30, y), 3)

    def _avisos(self, sesion):
        colores = {ACIERTO: VERDE, FALLO: ROJO, EXTRA: AMBAR}
        for aviso in sesion.avisos_vigentes():
            color = colores.get(aviso.tipo, TEXTO)
            self._centrado(aviso.texto, self.x_carril(aviso.carril),
                           self.y_linea + 52, self.fuente_chica, color)

    def _cabecera(self, sesion):
        pista = sesion.pista_actual
        resumen = sesion.resumen
        # El titulo se recorta para no pisar el marcador de pulso del centro.
        ancho_titulo = self.ancho // 2 - (MARGEN_LATERAL - 30) - 70
        self._texto(_recortar(pista.titulo, self.fuente, ancho_titulo),
                    (MARGEN_LATERAL - 30, 24), self.fuente)
        self._texto(f"{sesion.puntaje}", (MARGEN_LATERAL - 30, 54),
                    self.fuente_titulo, ACENTO)

        derecha = self.ancho - MARGEN_LATERAL + 30
        self._derecha(f"racha {resumen.racha}   maxima {resumen.racha_maxima}",
                      derecha, 30, self.fuente_chica, TEXTO_TENUE)
        self._derecha(f"{resumen.aciertos} de {resumen.total}",
                      derecha, 54, self.fuente, TEXTO)
        if resumen.fallos or resumen.extras:
            self._derecha(f"{_plural(resumen.fallos, 'fallo')}   "
                          f"{resumen.extras} de mas",
                          derecha, 78, self.fuente_chica, TEXTO_TENUE)

        # Marcador de pulso: late con el compas para orientar el ritmo. Es
        # visual y no sonoro a proposito: un clic por los parlantes lo
        # captaria el microfono y el detector lo contaria como notas.
        pulso = pista.pulso(max(sesion.t_pista, 0.0))
        fraccion = pulso - int(pulso)
        radio = 9 if fraccion < 0.2 else 5
        color = ACENTO if fraccion < 0.2 else _oscurecer(ACENTO, 0.4)
        pygame.draw.circle(self.pantalla, color, (self.ancho // 2, 40), radio)
        self._centrado(f"pulso {int(pulso) + 1}", self.ancho // 2, 56,
                       self.fuente_chica, TEXTO_TENUE)

    def _pie(self, sesion):
        y = self.alto - 26
        ancho_barra = self.ancho - 2 * (MARGEN_LATERAL - 30)
        fondo = pygame.Rect(MARGEN_LATERAL - 30, y, ancho_barra, 6)
        pygame.draw.rect(self.pantalla, PANEL, fondo, border_radius=3)
        avance = pygame.Rect(fondo.left, y, ancho_barra * sesion.progreso, 6)
        pygame.draw.rect(self.pantalla, ACENTO, avance, border_radius=3)
        if sesion.t_pista < 0:
            self._centrado(f"empieza en {-sesion.t_pista:.1f} s",
                           self.ancho // 2, self.y_linea - 60, self.fuente,
                           TEXTO_TENUE)

    def _resultados(self, sesion):
        resumen = sesion.resumen
        self._texto("Resultados", (MARGEN_LATERAL, 70), self.fuente_titulo)
        self._texto(sesion.pista_actual.titulo, (MARGEN_LATERAL, 118),
                    self.fuente_chica, TEXTO_TENUE)

        precision = (100.0 * resumen.aciertos / resumen.total
                     if resumen.total else 0.0)
        ms = 1000 * resumen.error_temporal_medio_s
        filas = [
            ("Puntaje", f"{sesion.puntaje}"),
            ("Aciertos", f"{resumen.aciertos} de {resumen.total}"
                         f"   ({precision:.0f}%)"),
            ("Fallos", f"{resumen.fallos}"),
            ("Notas de mas", f"{resumen.extras}"),
            ("Racha maxima", f"{resumen.racha_maxima}"),
            ("En promedio",
             ("clavado en tiempo" if abs(ms) < 5 else
              f"{abs(ms):.0f} ms {'tarde' if ms > 0 else 'temprano'}")),
            ("Afinacion",
             ("afinado" if abs(resumen.error_cents_medio) < 3 else
              f"{abs(resumen.error_cents_medio):.0f} cents "
              f"{'agudo' if resumen.error_cents_medio > 0 else 'grave'}")),
        ]
        y = 180
        for etiqueta, valor in filas:
            self._texto(etiqueta, (MARGEN_LATERAL, y), self.fuente_chica,
                        TEXTO_TENUE)
            self._texto(valor, (MARGEN_LATERAL + 220, y - 2), self.fuente)
            y += 42

        self._texto("Enter para volver al menu, R para repetir",
                    (MARGEN_LATERAL, y + 20), self.fuente_chica, TEXTO_TENUE)

    # ---------------------------------------------------------------- texto

    def _texto(self, cadena, posicion, fuente, color=TEXTO):
        self.pantalla.blit(fuente.render(cadena, True, color), posicion)

    def _centrado(self, cadena, x, y, fuente, color=TEXTO):
        superficie = fuente.render(cadena, True, color)
        self.pantalla.blit(superficie, (x - superficie.get_width() / 2, y))

    def _derecha(self, cadena, x, y, fuente, color=TEXTO):
        superficie = fuente.render(cadena, True, color)
        self.pantalla.blit(superficie, (x - superficie.get_width(), y))

    def _en_el_centro(self, cadena, centro, fuente, color=TEXTO):
        """Centra en los dos ejes, sin ajustes a ojo."""
        superficie = fuente.render(cadena, True, color)
        rect = superficie.get_rect(center=centro)
        self.pantalla.blit(superficie, rect)


def _plural(cantidad, singular):
    return f"{cantidad} {singular}" + ("" if cantidad == 1 else "s")


def _recortar(cadena, fuente, ancho_maximo):
    """Acorta con puntos suspensivos si no entra en el ancho dado."""
    if fuente.size(cadena)[0] <= ancho_maximo:
        return cadena
    recortada = cadena
    while recortada and fuente.size(recortada + "...")[0] > ancho_maximo:
        recortada = recortada[:-1]
    return recortada.rstrip() + "..."


def _oscurecer(color, factor):
    """Mezcla un color con el fondo. factor 1.0 lo deja igual."""
    return tuple(int(FONDO[i] + (color[i] - FONDO[i]) * factor)
                 for i in range(3))
