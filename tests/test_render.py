"""Pruebas del render. Corren sin pantalla con el driver dummy de SDL.

No comprueban que el dibujo sea lindo, sino que cada estado se dibuje sin
reventar y que deje algo en pantalla. Alcanza para que un cambio en el modelo
de vista no rompa el render en silencio.
"""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

pygame = pytest.importorskip("pygame")

from audio.notas import midi_a_hz                       # noqa: E402
from juego.render import ALTO, ANCHO, FONDO, Renderizador   # noqa: E402
from juego.sesion import JUGANDO, RESULTADOS, Sesion     # noqa: E402
from nucleo.pista import cargar                          # noqa: E402


class AtaqueFalso:
    def __init__(self, t, f0=None, energias=None):
        self.t = t
        self.f0 = f0
        self.energias = energias


@pytest.fixture(scope="module")
def pantalla():
    pygame.init()
    superficie = pygame.display.set_mode((ANCHO, ALTO))
    yield superficie
    pygame.quit()


@pytest.fixture
def pistas():
    """Todas las pistas que se entregan, para que agregar una quede cubierta."""
    import glob
    return [cargar(ruta) for ruta in sorted(glob.glob("pistas/*.json"))]


def pinto_algo(superficie):
    """True si quedo algo distinto del fondo en pantalla."""
    ancho, alto = superficie.get_size()
    for x in range(0, ancho, 7):
        for y in range(0, alto, 7):
            if superficie.get_at((x, y))[:3] != FONDO:
                return True
    return False


def test_el_menu_se_dibuja(pantalla, pistas):
    sesion = Sesion(pistas)
    Renderizador(pantalla).dibujar(sesion)
    assert pinto_algo(pantalla)


def test_el_menu_se_dibuja_con_cualquier_seleccion(pantalla, pistas):
    sesion = Sesion(pistas)
    renderizador = Renderizador(pantalla)
    for _ in range(len(pistas) + 1):
        renderizador.dibujar(sesion)
        sesion.mover_seleccion(1)
    assert pinto_algo(pantalla)


def test_la_entrada_antes_de_la_primera_nota_se_dibuja(pantalla, pistas):
    sesion = Sesion([pistas[0]])
    sesion.empezar(0.0)
    sesion.avanzar(1.0)
    assert sesion.estado == JUGANDO
    Renderizador(pantalla).dibujar(sesion)
    assert pinto_algo(pantalla)


@pytest.mark.parametrize("indice", [0, 1, 2, 3])
def test_el_highway_se_dibuja_con_aciertos_fallos_y_extras(pantalla, pistas,
                                                           indice):
    pista = pistas[indice]
    sesion = Sesion([pista])
    sesion.empezar(0.0)
    renderizador = Renderizador(pantalla)

    # Acierta la primera, falla la segunda y mete una nota de mas.
    primera = pista.eventos[0]
    sesion.avanzar(3.0 + primera.t,
                   [AtaqueFalso(3.0 + primera.t, midi_a_hz(primera.midis[0]))])
    renderizador.dibujar(sesion)
    assert pinto_algo(pantalla)

    sesion.avanzar(3.0 + pista.eventos[1].t + 0.5)
    sesion.avanzar(3.0 + pista.eventos[1].t + 0.6,
                   [AtaqueFalso(3.0 + pista.eventos[1].t + 0.6,
                                midi_a_hz(43))])
    renderizador.dibujar(sesion)
    assert pinto_algo(pantalla)


@pytest.mark.parametrize("indice", [0, 1, 2, 3])
def test_cada_cuadro_de_la_pista_entera_se_dibuja(pantalla, pistas, indice):
    """Recorre la pista de punta a punta dibujando: ningun instante revienta."""
    from nucleo.evaluador import RETARDO_MOTOR_S
    pista = pistas[indice]
    sesion = Sesion([pista])
    sesion.empezar(0.0)
    renderizador = Renderizador(pantalla)
    # El tope sale de la pista y no de un numero fijo: con uno fijo, alargar
    # un ejercicio hacia fallar la prueba por quedarse corta de cuadros.
    tope = int(60 * (pista.duracion + sesion.ventana_vista_s
                     + RETARDO_MOTOR_S + 2.0))
    cuadro = 0
    while sesion.estado == JUGANDO and cuadro < tope:
        sesion.avanzar(cuadro / 60)
        renderizador.dibujar(sesion)
        cuadro += 1
    assert sesion.estado == RESULTADOS
    renderizador.dibujar(sesion)
    assert pinto_algo(pantalla)


def test_los_resultados_se_dibujan(pantalla, pistas):
    sesion = Sesion([pistas[1]])
    sesion.empezar(0.0)
    sesion.avanzar(1000.0)
    assert sesion.estado == RESULTADOS
    Renderizador(pantalla).dibujar(sesion)
    assert pinto_algo(pantalla)


def test_el_aviso_de_sistema_se_dibuja(pantalla, pistas):
    renderizador = Renderizador(pantalla)
    renderizador.aviso_sistema = "sin audio del microfono desde hace 3 s"
    renderizador.dibujar(Sesion(pistas))
    assert pinto_algo(pantalla)


def test_un_titulo_larguisimo_no_desborda(pantalla, pistas):
    """El titulo se recorta para no pisar el marcador de pulso."""
    from juego.render import _recortar
    renderizador = Renderizador(pantalla)
    largo = "Ejercicio interminable " * 20
    recortado = _recortar(largo, renderizador.fuente, 280)
    assert renderizador.fuente.size(recortado)[0] <= 280
    assert recortado.endswith("...")
    assert _recortar("corto", renderizador.fuente, 280) == "corto"


def test_una_nota_a_tiempo_llena_la_caja_de_acierto(pantalla, pistas):
    """La caja existe para que no haya duda de donde se acierta.

    Antes solo habia una linea, y el borde de abajo de la nota la tocaba
    94 ms antes que el centro: no se sabia si el objetivo era el borde o el
    centro, y eso se medio como 73 ms de adelanto sistematico.
    """
    from juego.render import ALTO_CAJA, ALTO_NOTA, MARGEN_CAJA
    renderizador = Renderizador(pantalla)
    assert ALTO_CAJA == ALTO_NOTA + 2 * MARGEN_CAJA

    # Con restante 0 la nota esta centrada en la linea, o sea dentro de la caja.
    y = renderizador.y_de(0.0, 3.0)
    assert y == pytest.approx(renderizador.y_linea)
    assert abs(y - renderizador.y_linea) + ALTO_NOTA / 2 <= ALTO_CAJA / 2


def test_los_resultados_sugieren_el_desfase(pantalla, pistas):
    from audio.notas import midi_a_hz
    sesion = Sesion([pistas[0]], ventana_vista_s=3.0)
    sesion.empezar(0.0)
    for evento in pistas[0].eventos:
        t = 3.0 + evento.t - 0.073
        sesion.avanzar(3.0 + evento.t, [AtaqueFalso(t, midi_a_hz(evento.midi))])
    sesion.avanzar(1000.0)
    assert sesion.desfase_sugerido_notas_ms == 73
    Renderizador(pantalla).dibujar(sesion)
    assert pinto_algo(pantalla)


def test_el_desglose_de_notas_de_mas_dice_por_que():
    """Sin el desglose el numero no dice que corregir."""
    from juego.render import _texto_extras
    from nucleo.evaluador import AFINACION, SIN_ALTURA, Resumen
    resumen = Resumen(total=15, aciertos=12, fallos=3, extras=5, racha=0,
                      racha_maxima=6, error_temporal_medio_s=0.0,
                      error_cents_medio=0.0,
                      extras_por_motivo={SIN_ALTURA: 3, AFINACION: 2})
    texto = _texto_extras(resumen)
    assert texto.startswith("5")
    assert "3 no sonaron claras" in texto
    assert "2 desafinadas" in texto
    assert texto.index("3 no sonaron") < texto.index("2 desafinadas")


def test_el_desglose_respeta_el_singular():
    from juego.render import _texto_extras
    from nucleo.evaluador import AFINACION, SIN_ALTURA, Resumen
    resumen = Resumen(total=5, aciertos=4, fallos=1, extras=2, racha=0,
                      racha_maxima=4, error_temporal_medio_s=0.0,
                      error_cents_medio=0.0,
                      extras_por_motivo={SIN_ALTURA: 1, AFINACION: 1})
    texto = _texto_extras(resumen)
    assert "1 no sono clara" in texto
    assert "1 desafinada" in texto and "desafinadas" not in texto


def test_por_defecto_la_nota_dice_cuerda_y_traste(pantalla, pistas):
    """Es lo que pidio quien lo usa: "E2" no dice que hacer con las manos."""
    from juego.render import ETIQUETA_DIGITACION
    renderizador = Renderizador(pantalla, etiquetas=ETIQUETA_DIGITACION)
    sesion = Sesion([pistas[0]], ventana_vista_s=3.0)
    sesion.empezar(0.0)
    sesion.avanzar(3.0)
    vista = next(n for n in sesion.notas_en_vista() if n.indice == 0)
    # El E2 de la pista 1 va en la 6a al aire.
    assert vista.evento.cuerda == 6 and vista.evento.traste == 0
    renderizador.dibujar(sesion)
    assert pinto_algo(pantalla)


def test_con_etiquetas_notas_vuelve_el_nombre(pantalla, pistas):
    from juego.render import ETIQUETA_NOTAS
    renderizador = Renderizador(pantalla, etiquetas=ETIQUETA_NOTAS)
    sesion = Sesion([pistas[0]], ventana_vista_s=3.0)
    sesion.empezar(0.0)
    sesion.avanzar(3.0)
    vista = next(n for n in sesion.notas_en_vista() if n.indice == 0)
    assert renderizador._etiqueta(vista, pistas[0].afinacion) == "E2"


def test_el_bloque_del_acorde_lleva_solo_el_nombre(pantalla, pistas):
    """Como se arma la mano lo cuenta el diagrama del costado.

    "x02210" sobre una barra que esta bajando hay que descifrarlo; la grilla
    con los dedos se lee de un golpe.
    """
    from juego.render import ETIQUETA_DIGITACION, ETIQUETA_NOTAS
    pista = pistas[2]
    primer_acorde = next(e for e in pista.eventos if e.tipo == "acorde")
    sesion = Sesion([pista], ventana_vista_s=3.0)
    sesion.empezar(0.0)
    sesion.avanzar(3.0 + primer_acorde.t)       # el acorde llega a la linea
    vista = next(n for n in sesion.notas_en_vista()
                 if n.evento is primer_acorde)
    for modo in (ETIQUETA_DIGITACION, ETIQUETA_NOTAS):
        assert Renderizador(pantalla, etiquetas=modo)._etiqueta(
            vista, pista.afinacion) == primer_acorde.nombre


def test_el_diagrama_de_acorde_se_dibuja(pantalla, pistas):
    sesion = Sesion([pistas[2]], ventana_vista_s=3.0)
    sesion.empezar(0.0)
    sesion.avanzar(3.0)
    assert sesion.acorde_a_la_vista() is not None
    Renderizador(pantalla).dibujar(sesion)
    assert pinto_algo(pantalla)


def test_un_acorde_en_posicion_alta_no_desborda_la_grilla(pantalla):
    """Un acorde con cejilla arriba del traste 4 corre la grilla y lo indica."""
    from nucleo.pista import desde_dict
    # F#m con cejilla en el traste 2 llega al 4; un Bm en el 7 llega al 9.
    pista = desde_dict({"titulo": "x", "bpm": 60, "eventos": [
        {"t": 0.0, "dur": 2.0, "tipo": "acorde", "nombre": "Bm",
         "notas": [59, 66, 71, 74, 78]}]})
    sesion = Sesion([pista], ventana_vista_s=3.0)
    sesion.empezar(0.0)
    sesion.avanzar(3.0)
    Renderizador(pantalla).dibujar(sesion)
    assert pinto_algo(pantalla)


def test_una_nota_sin_digitacion_posible_cae_en_el_nombre(pantalla):
    """Con una afinacion rara puede no haber cuerda que la alcance."""
    from juego.render import ETIQUETA_DIGITACION
    from nucleo.pista import desde_dict
    pista = desde_dict({"titulo": "x", "bpm": 60,
                        "afinacion": ["E4", "E4", "E4", "E4", "E4", "E4"],
                        "eventos": [{"t": 0.0, "dur": 1.0, "tipo": "nota",
                                     "midi": 40}]})
    sesion = Sesion([pista], ventana_vista_s=3.0)
    sesion.empezar(0.0)
    sesion.avanzar(3.0)
    vista = next(n for n in sesion.notas_en_vista() if n.indice == 0)
    renderizador = Renderizador(pantalla, etiquetas=ETIQUETA_DIGITACION)
    assert renderizador._etiqueta(vista, pista.afinacion) == "E2"
    renderizador.dibujar(sesion)
