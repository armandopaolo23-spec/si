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
    def __init__(self, t, f0):
        self.t = t
        self.f0 = f0


@pytest.fixture(scope="module")
def pantalla():
    pygame.init()
    superficie = pygame.display.set_mode((ANCHO, ALTO))
    yield superficie
    pygame.quit()


@pytest.fixture
def pistas():
    return [cargar(ruta) for ruta in
            ("pistas/01_cuerdas_al_aire.json",
             "pistas/02_escala_do_mayor.json",
             "pistas/03_acordes_y_melodia.json")]


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


@pytest.mark.parametrize("indice", [0, 1, 2])
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


@pytest.mark.parametrize("indice", [0, 1, 2])
def test_cada_cuadro_de_la_pista_entera_se_dibuja(pantalla, pistas, indice):
    """Recorre la pista de punta a punta dibujando: ningun instante revienta."""
    pista = pistas[indice]
    sesion = Sesion([pista])
    sesion.empezar(0.0)
    renderizador = Renderizador(pantalla)
    cuadro = 0
    while sesion.estado == JUGANDO and cuadro < 60 * 40:
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
