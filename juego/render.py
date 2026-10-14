"""Dibujo con pygame. Es la unica parte del juego que sabe de pantallas.

No decide nada: toma el modelo de vista que produce juego/sesion.py y lo
dibuja. Por eso la logica del juego se puede probar sin abrir ventana.
"""

import pygame

from audio.notas import nombre_midi
from juego.geometria import (digitacion_de_acorde, digitacion_de_nota,
                             indice_carril, posicion_relativa, tablatura)
from juego.sesion import (ACERTADA, FALLADA, JUGANDO, MENU, RESULTADOS)
from nucleo.evaluador import (ACIERTO, ACORDE_INCOMPLETO, AFINACION, EXTRA,
                              FALLO, SIN_ALTURA, SIN_EVENTO)
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
# La caja de acierto tiene la altura de una nota mas un pelo de margen: una
# nota la llena justo en el instante en que hay que tocarla. Sin ella solo
# habia una linea, y el borde de abajo de la nota la tocaba 94 ms antes que
# el centro, asi que no se sabia si el objetivo era el borde o el centro.
MARGEN_CAJA = 4
ALTO_CAJA = ALTO_NOTA + 2 * MARGEN_CAJA

ALTO_FILA_MENU = 84

# Diagrama de acorde del costado derecho, en el hueco que deja el highway.
DIAGRAMA_CUERDAS = 6
DIAGRAMA_FILAS = 4            # trastes visibles en la grilla
DIAGRAMA_PASO = 21            # separacion entre cuerdas
DIAGRAMA_ALTO_FILA = 25
DIAGRAMA_Y = 190
DIAGRAMA_RADIO = 8


# Que se escribe sobre cada nota que baja.
ETIQUETA_DIGITACION = "digitacion"   # "6a 0": cuerda y traste
ETIQUETA_NOTAS = "notas"             # "E2": nombre de la nota
ETIQUETAS = (ETIQUETA_DIGITACION, ETIQUETA_NOTAS)


class Renderizador:
    def __init__(self, pantalla, etiquetas=ETIQUETA_DIGITACION):
        self.etiquetas = etiquetas
        self.pantalla = pantalla
        self.ancho, self.alto = pantalla.get_size()
        self.fuente_titulo = pygame.font.Font(None, 44)
        self.fuente = pygame.font.Font(None, 28)
        self.fuente_chica = pygame.font.Font(None, 22)
        self.fuente_nota = pygame.font.Font(None, 20)
        self.fuente_traste = pygame.font.Font(None, 28)
        self.fuente_cuerda = pygame.font.Font(None, 18)
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

        # Con pistas generadas la lista ya no entra entera: se muestra una
        # ventana que sigue a la seleccion y se avisa que hay mas.
        primero, ultimo = _ventana_menu(len(sesion.pistas), sesion.seleccion,
                                        self._pistas_visibles())
        if primero > 0:
            self._texto(f"... {primero} mas arriba", (MARGEN_LATERAL, 160),
                        self.fuente_chica, TEXTO_TENUE)
        y = 190
        for indice in range(primero, ultimo):
            pista = sesion.pistas[indice]
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
            partes = [f"{pista.bpm:g} bpm"]
            if notas:
                partes.append(_plural(notas, "nota"))
            if acordes:
                partes.append(_plural(acordes, "acorde"))
            partes.append(f"{pista.duracion:.0f} s")
            detalle = "   ".join(partes)
            self._texto(detalle, (MARGEN_LATERAL, y + 28), self.fuente_chica,
                        TEXTO_TENUE)
            y += ALTO_FILA_MENU
        if ultimo < len(sesion.pistas):
            self._texto(f"... {len(sesion.pistas) - ultimo} mas abajo",
                        (MARGEN_LATERAL, y - 6), self.fuente_chica, TEXTO_TENUE)

    def _pistas_visibles(self):
        """Cuantas filas del menu entran, dejando lugar para el aviso de abajo."""
        return max(1, (self.alto - 190 - 40) // ALTO_FILA_MENU)

    def _juego(self, sesion):
        pista = sesion.pista_actual
        self._carriles(pista)
        self._linea_de_golpe()
        self._notas(sesion)
        self._avisos(sesion)
        self._cabecera(sesion)
        self._diagrama(sesion)
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

    def _etiqueta(self, vista, afinacion):
        """Que decir sobre la nota que baja.

        Por defecto la digitacion y no el nombre: para quien recien empieza,
        "6a 0" es una instruccion y "E2" no dice que hacer con las manos.
        """
        evento = vista.evento
        if evento.tipo == "acorde":
            # Solo el nombre: como se arma la mano lo cuenta el diagrama del
            # costado, que se lee mucho mejor que "x02210" sobre una barra
            # que esta bajando.
            return evento.nombre
        if self.etiquetas == ETIQUETA_NOTAS:
            return nombre_midi(evento.midi)
        digitacion = digitacion_de_nota(evento.midi, afinacion, evento.cuerda,
                                        evento.traste)
        if digitacion is None:
            return nombre_midi(evento.midi)
        cuerda, traste = digitacion
        return f"{cuerda}a  {traste}"

    def _notas(self, sesion):
        afinacion = sesion.pista_actual.afinacion
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
            digitacion = (None if vista.evento.tipo == "acorde"
                          or self.etiquetas == ETIQUETA_NOTAS
                          else digitacion_de_nota(vista.evento.midi, afinacion,
                                                  vista.evento.cuerda,
                                                  vista.evento.traste))
            if digitacion is None:
                self._en_el_centro(self._etiqueta(vista, afinacion),
                                   rect.center, self.fuente_nota)
            else:
                self._digitacion(rect, *digitacion)

    def _digitacion(self, rect, cuerda, traste):
        """Escribe la cuerda chica y el traste grande, centrados en la nota.

        El traste va destacado porque es la instruccion: en que carril esta
        la nota ya dice la cuerda, pero el traste no se deduce de nada.
        """
        texto_cuerda = self.fuente_cuerda.render(f"{cuerda}a", True, TEXTO_TENUE)
        texto_traste = self.fuente_traste.render(str(traste), True, TEXTO)
        separacion = 5
        total = texto_cuerda.get_width() + separacion + texto_traste.get_width()
        x = rect.centerx - total / 2
        self.pantalla.blit(
            texto_cuerda,
            texto_cuerda.get_rect(midleft=(x, rect.centery + 1)))
        self.pantalla.blit(
            texto_traste,
            texto_traste.get_rect(
                midleft=(x + texto_cuerda.get_width() + separacion,
                         rect.centery)))

    def _linea_de_golpe(self):
        """Caja de acierto: la nota la llena justo cuando hay que tocarla."""
        y = self.y_linea
        izquierda = MARGEN_LATERAL - 30
        ancho = self.ancho - 2 * izquierda
        caja = pygame.Rect(izquierda, y - ALTO_CAJA / 2, ancho, ALTO_CAJA)
        pygame.draw.rect(self.pantalla, _oscurecer(LINEA_GOLPE, 0.12), caja,
                         border_radius=8)
        pygame.draw.rect(self.pantalla, LINEA_GOLPE, caja, width=2,
                         border_radius=8)

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

    def _diagrama(self, sesion):
        """Diagrama del acorde que viene, en el hueco de la derecha.

        Para rasguear, una grilla con los dedos se lee de un golpe; un texto
        como "x02210" sobre la barra que baja hay que descifrarlo. Las notas
        sueltas no lo necesitan: ya traen cuerda y traste encima.
        """
        evento = sesion.acorde_a_la_vista()
        if evento is None:
            return

        trastes = digitacion_de_acorde(evento.notas,
                                       sesion.pista_actual.afinacion)
        if all(traste is None for traste in trastes):
            # Sin digitacion posible es mejor no dibujar nada que dibujar una
            # grilla vacia, que se leeria como "no se toca ninguna cuerda".
            return
        ancho = DIAGRAMA_PASO * (DIAGRAMA_CUERDAS - 1)
        x0 = self.ancho - MARGEN_LATERAL + (MARGEN_LATERAL - ancho) / 2
        y0 = DIAGRAMA_Y

        # Si el acorde no es de posicion abierta, la grilla arranca en el
        # traste mas bajo que se pisa y se indica cual es.
        pisados = [t for t in trastes if t]
        primero = 1
        if pisados and max(pisados) > DIAGRAMA_FILAS:
            primero = min(pisados)

        self._centrado(evento.nombre, x0 + ancho / 2, y0 - 54, self.fuente)

        # Cuerdas al aire y silenciadas, arriba de la grilla.
        for indice, traste in enumerate(trastes):
            if traste is None:
                marca, color = "x", TEXTO_TENUE
            elif traste == 0:
                marca, color = "o", TEXTO
            else:
                continue
            self._centrado(marca, x0 + indice * DIAGRAMA_PASO, y0 - 22,
                           self.fuente_chica, color)

        alto = DIAGRAMA_ALTO_FILA * DIAGRAMA_FILAS
        for indice in range(DIAGRAMA_CUERDAS):
            x = x0 + indice * DIAGRAMA_PASO
            pygame.draw.line(self.pantalla, TEXTO_TENUE, (x, y0),
                             (x, y0 + alto), 1)
        for fila in range(DIAGRAMA_FILAS + 1):
            y = y0 + fila * DIAGRAMA_ALTO_FILA
            # La cejuela es gruesa y solo existe en posicion abierta.
            grosor = 4 if (fila == 0 and primero == 1) else 1
            pygame.draw.line(self.pantalla, TEXTO if grosor > 1 else TEXTO_TENUE,
                             (x0, y), (x0 + ancho, y), grosor)
        if primero > 1:
            self._texto(f"{primero}fr", (x0 + ancho + 6, y0 - 6),
                        self.fuente_chica, TEXTO_TENUE)

        for indice, traste in enumerate(trastes):
            if not traste:
                continue
            fila = traste - primero
            if not 0 <= fila < DIAGRAMA_FILAS:
                continue
            centro = (int(x0 + indice * DIAGRAMA_PASO),
                      int(y0 + (fila + 0.5) * DIAGRAMA_ALTO_FILA))
            pygame.draw.circle(self.pantalla, ACENTO, centro, DIAGRAMA_RADIO)

        self._centrado(tablatura(trastes), x0 + ancho / 2, y0 + alto + 12,
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
        self._texto("Resultados", (MARGEN_LATERAL, 50), self.fuente_titulo)
        self._texto(sesion.pista_actual.titulo, (MARGEN_LATERAL, 98),
                    self.fuente_chica, TEXTO_TENUE)

        precision = (100.0 * resumen.aciertos / resumen.total
                     if resumen.total else 0.0)
        filas = [
            ("Puntaje", f"{sesion.puntaje}"),
            ("Aciertos", f"{resumen.aciertos} de {resumen.total}"
                         f"   ({precision:.0f}%)"),
            ("Fallos", f"{resumen.fallos}"),
            ("Notas de mas", _texto_extras(resumen)),
            ("Racha maxima", f"{resumen.racha_maxima}"),
        ]
        # Notas y rasgueos tienen sesgos distintos y se compensan por
        # separado, asi que se informan por separado.
        if resumen.aciertos_notas:
            filas.append(("Notas, en promedio",
                          _texto_tiempo(resumen.error_temporal_notas_s)))
        if resumen.aciertos_acordes:
            filas.append(("Acordes, en promedio",
                          _texto_tiempo(resumen.error_temporal_acordes_s)))
        if resumen.aciertos_notas:
            filas.append(("Afinacion",
                          ("afinado" if abs(resumen.error_cents_medio) < 3 else
                           f"{abs(resumen.error_cents_medio):.0f} cents "
                           f"{'agudo' if resumen.error_cents_medio > 0 else 'grave'}")))

        y = 150
        for etiqueta, valor in filas:
            self._texto(etiqueta, (MARGEN_LATERAL, y), self.fuente_chica,
                        TEXTO_TENUE)
            self._texto(valor, (MARGEN_LATERAL + 220, y - 2), self.fuente)
            y += 38

        opciones = []
        notas = sesion.desfase_sugerido_notas_ms
        acordes = sesion.desfase_sugerido_acordes_ms
        if notas is not None:
            opciones.append(f"--desfase-ms {notas}")
        if acordes is not None:
            opciones.append(f"--desfase-acorde-ms {acordes}")
        if opciones:
            self._texto("Hay un desfase sistematico. Para compensarlo:",
                        (MARGEN_LATERAL, y + 12), self.fuente_chica, AMBAR)
            self._texto("python3 tocar.py " + " ".join(opciones),
                        (MARGEN_LATERAL, y + 36), self.fuente_chica, TEXTO)
            y += 48

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


# Como se cuenta cada motivo de nota de mas: (singular, plural).
NOMBRES_MOTIVO = {
    SIN_ALTURA: ("no sono clara", "no sonaron claras"),
    AFINACION: ("desafinada", "desafinadas"),
    ACORDE_INCOMPLETO: ("acorde incompleto", "acordes incompletos"),
    SIN_EVENTO: ("fuera de lugar", "fuera de lugar"),
}


def _texto_extras(resumen):
    """'5  (3 no sonaron claras, 2 desafinadas)'.

    Sin el desglose el numero no dice que corregir: una nota apagada se
    arregla pisando mas fuerte y una desafinada afinando o soltando presion.
    """
    if not resumen.extras:
        return "0"
    detalle = sorted((resumen.extras_por_motivo or {}).items(),
                     key=lambda par: -par[1])
    partes = []
    for motivo, cantidad in detalle:
        singular, plural = NOMBRES_MOTIVO.get(motivo, (motivo, motivo))
        partes.append(f"{cantidad} {singular if cantidad == 1 else plural}")
    return f"{resumen.extras}   ({', '.join(partes)})"


def _texto_tiempo(error_s):
    ms = 1000 * error_s
    if abs(ms) < 5:
        return "clavado en tiempo"
    return f"{abs(ms):.0f} ms {'tarde' if ms > 0 else 'temprano'}"


def _ventana_menu(total, seleccion, visibles):
    """(primero, ultimo) de las pistas a mostrar, con la elegida adentro.

    Mantiene la seleccion centrada cuando se puede y no deja huecos al final.
    """
    if total <= visibles:
        return 0, total
    primero = min(max(seleccion - visibles // 2, 0), total - visibles)
    return primero, primero + visibles


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
