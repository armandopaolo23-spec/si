"""Pruebas del reconocimiento de acordes.

Las unitarias usan vectores de energia construidos a mano; la de integracion
sintetiza rasgueos y los hace pasar por el analizador y el evaluador reales.
"""

import numpy as np
import pytest

from audio.analizador import SALTO, Analizador
from audio.croma import MIDI_MAXIMO, MIDI_MINIMO, NOTAS, MedidorArmonico
from audio.notas import midi_a_hz
from nucleo.acordes import (ACORDES_ABIERTOS, FRACCION_MINIMA, croma,
                            nombrar, notas_presentes, plantilla, reconocer,
                            similitud)
from nucleo.evaluador import Deteccion, Evaluador
from nucleo.pista import cargar
from nucleo.simulacion import energias_de
from tests.sintesis import SR, pulsacion

EM = ACORDES_ABIERTOS["Em"]
AM = ACORDES_ABIERTOS["Am"]
DO = ACORDES_ABIERTOS["C"]


def rasgueada(notas, t0, muestras, retardo=0.018, semilla=0, amplitud=0.12):
    """Un rasgueo: las cuerdas se barren, no suenan juntas."""
    x = np.zeros(muestras)
    for indice, midi in enumerate(notas):
        golpe = pulsacion(midi_a_hz(midi), 2.2, amplitud=amplitud,
                          decaimiento=0.9, recorte_graves=0.6,
                          semilla=semilla * 13 + indice)
        inicio = int((t0 + indice * retardo) * SR)
        fin = min(muestras, inicio + len(golpe))
        x[inicio:fin] += golpe[:fin - inicio]
    return x


# ------------------------------------------------------------------- croma

def test_el_croma_tiene_doce_clases_y_esta_normalizado():
    vector = croma(energias_de(EM))
    assert len(vector) == 12
    assert np.linalg.norm(vector) == pytest.approx(1.0)


def test_el_croma_de_nada_es_nulo():
    assert not croma(np.zeros(NOTAS)).any()
    assert not croma(None).any()


def test_la_plantilla_incluye_los_armonicos():
    """Sin armonicos la plantilla no se parece a lo que mide el microfono: el
    tercer armonico de una nota cae en su quinta."""
    sin_armonicos = plantilla([40], armonicos=1)
    con_armonicos = plantilla([40], armonicos=4)
    assert np.count_nonzero(con_armonicos) > np.count_nonzero(sin_armonicos)
    # El tercer armonico de E2 es un Si.
    assert con_armonicos[11] > 0


def test_la_similitud_de_algo_consigo_mismo_es_uno():
    assert similitud(plantilla(EM), plantilla(EM)) == pytest.approx(1.0)


@pytest.mark.parametrize("nombre", sorted(ACORDES_ABIERTOS))
def test_el_croma_nombra_cada_acorde_abierto(nombre):
    oido, puntaje = nombrar(energias_de(ACORDES_ABIERTOS[nombre]))
    assert oido == nombre
    assert puntaje > 0.8


def test_nombrar_sin_energias_no_devuelve_nada():
    assert nombrar(None) == (None, 0.0)
    assert nombrar(np.zeros(NOTAS)) == (None, 0.0)


# -------------------------------------------------------------- presencia

def test_presencia_de_las_notas_que_suenan():
    presentes = notas_presentes(energias_de(EM), EM)
    assert all(presentes)


def test_una_nota_que_no_suena_se_nota():
    """Las graves son las fiables: los armonicos van hacia arriba, asi que
    nada puede poner un E2 que no se toco."""
    sin_el_bajo = [m for m in EM if m != 40]
    presentes = notas_presentes(energias_de(sin_el_bajo), EM)
    assert presentes[0] is False
    assert sum(presentes) >= len(EM) - 2


def test_presencia_sin_energias_es_todo_falso():
    assert notas_presentes(None, EM) == (False,) * len(EM)
    assert notas_presentes(np.zeros(NOTAS), EM) == (False,) * len(EM)


def test_el_piso_se_adapta_al_nivel_de_entrada():
    """El mismo acorde mas fuerte o mas flojo tiene que dar lo mismo: el piso
    sale de un percentil de lo medido, no de un valor absoluto."""
    base = energias_de(EM)
    for escala in (0.01, 1.0, 100.0):
        assert notas_presentes(base * escala, EM) == notas_presentes(base, EM)


# ------------------------------------------------------------- reconocer

def test_reconoce_el_acorde_pedido():
    resultado = reconocer(energias_de(EM), EM, nombre="Em")
    assert resultado.acertado
    assert resultado.fraccion == 1.0
    assert resultado.faltantes == ()
    assert resultado.nombre_oido == "Em"


@pytest.mark.parametrize("ajeno", ["Am", "C", "G", "D", "A"])
def test_rechaza_otro_acorde(ajeno):
    """Do comparte dos de las tres notas de Mi menor, y aun asi se rechaza."""
    resultado = reconocer(energias_de(ACORDES_ABIERTOS[ajeno]), EM,
                          nombre="Em")
    assert not resultado.acertado


def test_la_fraccion_minima_es_configurable():
    faltan_dos = [m for m in EM if m not in (40, 47)]
    energias = energias_de(faltan_dos)
    assert not reconocer(energias, EM, nombre="Em").acertado
    assert reconocer(energias, EM, fraccion_minima=0.5, nombre="Em").acertado


def test_sin_nombre_esperado_solo_mira_la_presencia():
    """Util para un acorde que no este entre las plantillas abiertas."""
    resultado = reconocer(energias_de(EM), EM)
    assert resultado.acertado
    assert FRACCION_MINIMA <= resultado.fraccion


# ------------------------------------------------------ medida del espectro

def test_el_medidor_necesita_la_ventana_completa():
    medidor = MedidorArmonico(SR)
    assert not medidor.energia_por_nota(np.zeros(100)).any()


def test_el_medidor_encuentra_una_nota_sola():
    medidor = MedidorArmonico(SR)
    muestras = pulsacion(midi_a_hz(45), 1.0, amplitud=0.2, decaimiento=0.4)
    energias = medidor.energia_por_nota(muestras)
    assert energias.argmax() + MIDI_MINIMO in (45, 45 + 12)
    assert MIDI_MINIMO <= 45 <= MIDI_MAXIMO


# --------------------------------------------------------- de punta a punta

def test_una_pista_de_acordes_tocada_entera_con_audio():
    """La prueba que importa: rasgueos sintetizados entrando por el motor
    real y saliendo calificados por el evaluador real."""
    pista = cargar("pistas/03_acordes_basicos.json")
    muestras = int((pista.duracion + 1.0) * SR)
    x = np.zeros(muestras)
    for indice, evento in enumerate(pista.eventos):
        x += rasgueada(evento.notas, evento.t, muestras, semilla=indice + 1)
    x = (x + np.random.default_rng(0).normal(0, 0.0015, muestras)).astype(
        np.float32)

    analizador = Analizador()
    evaluador = Evaluador(pista)
    for inicio in range(0, len(x), SALTO):
        ataques = analizador.procesar(x[inicio:inicio + SALTO])
        evaluador.avanzar(analizador.t_actual,
                          [Deteccion(t=a.t, f0=a.f0, energias=a.energias)
                           for a in ataques])
    evaluador.avanzar(1e6)

    resumen = evaluador.resumen
    assert resumen.aciertos == resumen.total == len(pista.eventos)
    assert resumen.fallos == 0
    assert resumen.extras == 0


def test_un_rasgueo_no_entrega_pitch_pero_si_energias():
    """Es la razon de existir de este modulo: YIN no sirve para un acorde."""
    muestras = int(3.0 * SR)
    x = rasgueada(EM, 0.5, muestras, semilla=3)
    x = (x + np.random.default_rng(1).normal(0, 0.0015, muestras)).astype(
        np.float32)
    analizador = Analizador()
    ataques = []
    for inicio in range(0, len(x), SALTO):
        ataques += analizador.procesar(x[inicio:inicio + SALTO])

    assert len(ataques) == 1
    assert ataques[0].nota is None          # YIN no encontro periodicidad
    assert ataques[0].energias is not None
    assert reconocer(ataques[0].energias, EM, nombre="Em").acertado
