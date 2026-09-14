"""Comprueba la regla de capas del proyecto.

El BRIEF la pide asi: la logica de juego no debe importar sounddevice ni
pygame, para poder testearla sin audio ni ventana. Es facil romperla sin
darse cuenta agregando un import de conveniencia, asi que se verifica.
"""

import ast
import pathlib

import pytest

# Modulos que tienen que poder importarse sin tarjeta de sonido ni pantalla.
PUROS = [
    "audio/notas.py",
    "audio/yin.py",
    "audio/onset.py",
    "audio/analizador.py",
    "audio/calibracion.py",
    "nucleo/pista.py",
    "nucleo/evaluador.py",
    "nucleo/puntaje.py",
    "nucleo/simulacion.py",
    "juego/sesion.py",
    "juego/geometria.py",
]

PROHIBIDOS = {"sounddevice", "pygame"}

# Los unicos modulos autorizados a importarlos.
FRONTERAS = {
    "sounddevice": {"audio/captura.py"},
    "pygame": {"juego/render.py", "juego/aplicacion.py"},
}


def importados_por(ruta):
    arbol = ast.parse(pathlib.Path(ruta).read_text(encoding="utf-8"))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres |= {alias.name.split(".")[0] for alias in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.add(nodo.module.split(".")[0])
    return nombres


@pytest.mark.parametrize("ruta", PUROS)
def test_los_modulos_puros_no_importan_audio_ni_ventana(ruta):
    encontrados = importados_por(ruta) & PROHIBIDOS
    assert not encontrados, f"{ruta} importa {encontrados}"


@pytest.mark.parametrize("biblioteca, permitidos", sorted(FRONTERAS.items()))
def test_solo_los_modulos_de_frontera_importan_cada_biblioteca(biblioteca,
                                                               permitidos):
    culpables = set()
    for ruta in pathlib.Path(".").glob("*/*.py"):
        if ruta.parts[0] not in ("audio", "nucleo", "juego"):
            continue
        if biblioteca in importados_por(ruta):
            culpables.add(str(ruta))
    assert culpables == permitidos, (
        f"{biblioteca} deberia importarse solo en {permitidos}, "
        f"y lo importan {culpables}")


@pytest.mark.parametrize("ruta", PUROS)
def test_los_modulos_puros_se_importan_de_verdad(ruta):
    """Que el import estatico este limpio no basta: tiene que cargar."""
    import importlib
    modulo = ruta.replace("/", ".").removesuffix(".py")
    importlib.import_module(modulo)
