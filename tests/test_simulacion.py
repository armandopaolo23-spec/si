"""Pruebas de la simulacion, que es tambien la prueba de integracion.

Corre el evaluador como lo hara el juego -bucle de 60 fps, detecciones que
llegan con el retardo real del motor- contra las pistas que se entregan.
"""

import glob

import pytest

from nucleo.evaluador import ACIERTO, Evaluador, Tolerancias
from nucleo.pista import cargar
from nucleo.simulacion import PERFILES, generar_detecciones, reproducir

PISTAS = sorted(glob.glob("pistas/*.json"))


def jugar(ruta, perfil, tolerancias=None, semilla=1):
    pista = cargar(ruta)
    evaluador = Evaluador(pista, tolerancias=tolerancias)
    detecciones = generar_detecciones(pista, PERFILES[perfil], semilla=semilla)
    resultados = reproducir(evaluador, detecciones, pista.duracion)
    return pista, evaluador, resultados


@pytest.mark.parametrize("ruta", PISTAS)
def test_una_pasada_perfecta_acierta_todo(ruta):
    """La prueba que importa: el retardo del motor no inventa fallos.

    Si el evaluador cerrara las ventanas cuando el reloj las pasa, en vez de
    esperar a que ya no pueda llegar una deteccion en camino, aca apareceria
    un fallo por cada nota.
    """
    pista, evaluador, resultados = jugar(ruta, "perfecto")
    resumen = evaluador.resumen
    assert resumen.aciertos == resumen.total == len(pista.eventos)
    assert resumen.fallos == 0
    assert resumen.extras == 0
    assert resumen.racha_maxima == resumen.total
    assert evaluador.terminado
    assert all(r.tipo == ACIERTO for r in resultados)


@pytest.mark.parametrize("ruta", PISTAS)
def test_tocar_tarde_de_forma_sistematica_igual_acierta(ruta):
    """80 ms tarde entra en la ventana de 120 ms, y el promedio lo delata."""
    _, evaluador, _ = jugar(ruta, "tarde")
    resumen = evaluador.resumen
    assert resumen.aciertos == resumen.total
    assert resumen.error_temporal_medio_s == pytest.approx(0.080, abs=0.001)


@pytest.mark.parametrize("ruta", PISTAS)
def test_una_guitarra_25_cents_baja_sigue_acertando(ruta):
    """Es el caso real medido: la 4a cuerda daba D3 a -17 cents constante.

    Con tolerancia de 35 cents esas notas tienen que pasar, o el juego
    marcaria fallo por la afinacion de la guitarra y no por como se toca.
    """
    _, evaluador, _ = jugar(ruta, "desafinado")
    resumen = evaluador.resumen
    assert resumen.aciertos == resumen.total
    assert resumen.error_cents_medio == pytest.approx(-25.0, abs=0.1)


def test_una_tolerancia_estricta_castiga_al_que_va_tarde():
    """Comprueba que las ventanas de verdad hacen algo."""
    _, evaluador, _ = jugar(PISTAS[0], "tarde",
                            tolerancias=Tolerancias(temporal_s=0.05))
    assert evaluador.resumen.aciertos == 0
    assert evaluador.resumen.fallos == evaluador.resumen.total


def test_una_tolerancia_estricta_castiga_al_desafinado():
    _, evaluador, _ = jugar(PISTAS[0], "desafinado",
                            tolerancias=Tolerancias(cents=15.0))
    assert evaluador.resumen.aciertos == 0


@pytest.mark.parametrize("ruta", PISTAS)
def test_tocar_desprolijo_produce_fallos_y_notas_de_mas(ruta):
    _, evaluador, _ = jugar(ruta, "desprolijo")
    resumen = evaluador.resumen
    assert resumen.fallos > 0
    assert resumen.extras > 0
    assert resumen.aciertos < resumen.total
    assert resumen.racha_maxima < resumen.total


@pytest.mark.parametrize("ruta", PISTAS)
def test_todo_evento_queda_resuelto(ruta):
    """Ningun evento puede quedar colgado: o se acierta o se falla."""
    for perfil in PERFILES:
        pista, evaluador, _ = jugar(ruta, perfil)
        resumen = evaluador.resumen
        assert resumen.aciertos + resumen.fallos == len(pista.eventos)
        assert evaluador.eventos_pendientes() == ()


def test_la_simulacion_es_determinista():
    primera = jugar(PISTAS[1], "desprolijo", semilla=3)[1].resumen
    segunda = jugar(PISTAS[1], "desprolijo", semilla=3)[1].resumen
    assert primera == segunda
    distinta = jugar(PISTAS[1], "desprolijo", semilla=4)[1].resumen
    assert distinta != primera


def test_se_saltan_notas_con_probabilidad_de_salto():
    """Guarda contra una semilla desafortunada: con la de por defecto la
    version anterior no salteaba ninguna y el perfil parecia no funcionar."""
    pista = cargar(PISTAS[1])
    perfil = PERFILES["desprolijo"]
    saltos = []
    for semilla in range(10):
        detecciones = generar_detecciones(pista, perfil, semilla=semilla)
        saltos.append(len(pista.eventos) + perfil.notas_de_mas
                      - len(detecciones))
    assert all(s >= 0 for s in saltos)
    assert sum(saltos) > 0
