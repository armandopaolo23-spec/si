"""Pruebas del evaluador. Logica pura: detecciones inventadas, sin audio."""

import pytest

from audio.notas import midi_a_hz
from nucleo.evaluador import (ACIERTO, EXTRA, FALLO, RETARDO_MOTOR_S,
                              Deteccion, Evaluador, Tolerancias)
from nucleo.pista import desde_dict

# Instante bien posterior a cualquier ventana de estas pruebas: sirve para
# forzar el cierre de todo lo que quedara pendiente.
DESPUES = 1000.0


def pista_de(*eventos):
    return desde_dict({"titulo": "prueba", "bpm": 60, "eventos": list(eventos)})


def nota(t, midi, dur=1.0):
    return {"t": t, "dur": dur, "tipo": "nota", "midi": midi}


def acorde(t, notas, dur=1.0, nombre="X"):
    return {"t": t, "dur": dur, "tipo": "acorde", "nombre": nombre,
            "notas": list(notas)}


def deteccion(t, midi, cents=0.0):
    """Deteccion en el pitch de un midi, desviada los cents que se pidan."""
    return Deteccion(t=t, f0=midi_a_hz(midi) * 2.0 ** (cents / 1200.0))


def tipos(resultados):
    return [r.tipo for r in resultados]


# ------------------------------------------------------------------ aciertos

def test_deteccion_en_el_instante_exacto():
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(1.0, [deteccion(1.0, 40)])
    assert tipos(resultados) == [ACIERTO]
    assert resultados[0].indice == 0
    assert resultados[0].error_s == pytest.approx(0.0)
    assert resultados[0].error_cents == pytest.approx(0.0, abs=1e-9)
    assert ev.terminado


@pytest.mark.parametrize("desfase", [-0.119, -0.06, 0.0, 0.06, 0.119])
def test_dentro_de_la_ventana_temporal(desfase):
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(1.0 + desfase, [deteccion(1.0 + desfase, 40)])
    assert tipos(resultados) == [ACIERTO]
    assert resultados[0].error_s == pytest.approx(desfase)


@pytest.mark.parametrize("desfase", [-0.121, -0.3, 0.121, 0.5])
def test_fuera_de_la_ventana_temporal_no_acierta(desfase):
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(DESPUES, [deteccion(1.0 + desfase, 40)])
    assert set(tipos(resultados)) == {EXTRA, FALLO}


@pytest.mark.parametrize("cents", [-34.9, -20.0, 0.0, 20.0, 34.9])
def test_dentro_de_la_ventana_de_afinacion(cents):
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(1.0, [deteccion(1.0, 40, cents)])
    assert tipos(resultados) == [ACIERTO]
    assert resultados[0].error_cents == pytest.approx(cents, abs=0.01)


@pytest.mark.parametrize("cents", [-35.1, -60.0, 35.1, 80.0])
def test_fuera_de_la_ventana_de_afinacion_no_acierta(cents):
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(DESPUES, [deteccion(1.0, 40, cents)])
    assert set(tipos(resultados)) == {EXTRA, FALLO}


def test_la_desviacion_se_mide_contra_lo_pedido_no_contra_la_nota_vecina():
    """Una nota 55 cents alta de E2 se lee como F2 a -45 cents.

    Comparando nombres de nota parece estar a 45 cents y pasaria; medida
    contra el pitch pedido esta a 55 y no pasa, que es lo correcto.
    """
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(DESPUES, [deteccion(1.0, 40, 55.0)])
    assert set(tipos(resultados)) == {EXTRA, FALLO}


def test_cualquier_digitacion_que_de_el_pitch_vale():
    """El BRIEF lo pide: un E4 vale igual en la 1a al aire que en la 2a.

    El evaluador solo ve frecuencia, asi que no hay nada que distinguir: la
    prueba deja constancia de que la digitacion sugerida no se exige.
    """
    ev = Evaluador(pista_de({"t": 1.0, "dur": 1.0, "tipo": "nota",
                             "midi": 64, "cuerda": 1, "traste": 0}))
    assert tipos(ev.avanzar(1.0, [deteccion(1.0, 64)])) == [ACIERTO]


# -------------------------------------------------------------------- fallos

def test_una_nota_no_tocada_es_fallo_cuando_vence_la_ventana():
    ev = Evaluador(pista_de(nota(1.0, 40)))
    assert ev.avanzar(1.0) == ()
    assert tipos(ev.avanzar(DESPUES)) == [FALLO]
    assert ev.terminado
    assert ev.resumen.fallos == 1


def test_la_ventana_no_se_cierra_antes_del_retardo_del_motor():
    """El nucleo de por que existe RETARDO_MOTOR_S.

    El ataque se emite bastante despues del golpe, con timestamp temprano y
    correcto. Si la ventana se cerrara al pasar el reloj, una deteccion
    legitima en camino llegaria tarde y seria un fallo inventado.
    """
    ev = Evaluador(pista_de(nota(1.0, 40)))
    cierre = 1.0 + 0.12          # fin de la ventana temporal

    # Justo pasada la ventana pero dentro del retardo del motor: no se cierra.
    assert ev.avanzar(cierre + RETARDO_MOTOR_S - 0.01) == ()
    assert not ev.terminado

    # Y la deteccion que venia en camino todavia acierta.
    resultados = ev.avanzar(cierre + RETARDO_MOTOR_S - 0.005,
                            [deteccion(1.05, 40)])
    assert tipos(resultados) == [ACIERTO]


def test_pasado_el_retardo_si_se_cierra():
    ev = Evaluador(pista_de(nota(1.0, 40)))
    assert tipos(ev.avanzar(1.0 + 0.12 + RETARDO_MOTOR_S + 0.01)) == [FALLO]


def test_nota_equivocada_en_el_momento_correcto_da_extra_y_fallo():
    """Son dos cosas distintas y conviene informar las dos: se toco algo que
    no estaba pedido, y nunca se toco lo que si estaba pedido."""
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(DESPUES, [deteccion(1.0, 45)])
    assert tipos(resultados) == [EXTRA, FALLO]
    assert ev.resumen.extras == 1
    assert ev.resumen.fallos == 1
    assert ev.resumen.aciertos == 0


# -------------------------------------------------------------------- extras

def test_deteccion_sin_ningun_evento_cerca_es_extra():
    ev = Evaluador(pista_de(nota(1.0, 40)))
    assert tipos(ev.avanzar(5.0, [deteccion(5.0, 40)])) == [EXTRA, FALLO]


def test_un_extra_no_corta_la_racha():
    """Con microfono integrado hay falsos positivos inevitables; castigarlos
    haria sentir el juego roto cuando en realidad se toco bien."""
    ev = Evaluador(pista_de(nota(1.0, 40), nota(2.0, 45)))
    ev.avanzar(1.0, [deteccion(1.0, 40)])
    ev.avanzar(1.5, [deteccion(1.5, 59)])      # nota de mas, sin evento cerca
    ev.avanzar(2.0, [deteccion(2.0, 45)])
    assert ev.resumen.racha == 2
    assert ev.resumen.extras == 1


# ------------------------------------------------------------------- acordes

def test_un_acorde_se_acierta_con_cualquiera_de_sus_notas():
    """Con un detector monofonico, una rasgueada da una sola lectura de pitch.

    Exigir todas las notas del acorde necesita el croma de la fase 5.
    """
    em = [40, 47, 52, 55, 59, 64]
    for midi in em:
        ev = Evaluador(pista_de(acorde(1.0, em, nombre="Em")))
        assert tipos(ev.avanzar(1.0, [deteccion(1.0, midi)])) == [ACIERTO], midi


def test_una_nota_ajena_al_acorde_no_lo_acierta():
    ev = Evaluador(pista_de(acorde(1.0, [40, 47, 52], nombre="Em")))
    resultados = ev.avanzar(DESPUES, [deteccion(1.0, 45)])   # A2 no esta en Em
    assert set(tipos(resultados)) == {EXTRA, FALLO}


# ------------------------------------------------------- varios eventos

def test_pista_tocada_perfecta():
    eventos = [nota(i * 1.0, 40 + i) for i in range(6)]
    ev = Evaluador(pista_de(*eventos))
    for i in range(6):
        assert tipos(ev.avanzar(i * 1.0, [deteccion(i * 1.0, 40 + i)])) == [ACIERTO]
    ev.avanzar(DESPUES)
    resumen = ev.resumen
    assert (resumen.aciertos, resumen.fallos, resumen.extras) == (6, 0, 0)
    assert resumen.racha == resumen.racha_maxima == 6
    assert ev.terminado


def test_una_nota_saltada_no_arrastra_las_siguientes():
    """Si no se toca la primera, la segunda tiene que seguir acertando."""
    ev = Evaluador(pista_de(nota(1.0, 40), nota(3.0, 45)))
    resultados = ev.avanzar(3.0, [deteccion(3.0, 45)])
    assert tipos(resultados) == [ACIERTO, FALLO]
    acierto = next(r for r in resultados if r.tipo == ACIERTO)
    assert acierto.indice == 1


def test_dos_eventos_con_ventanas_solapadas_se_resuelven_en_orden():
    """Con tolerancia de 120 ms, dos eventos a 100 ms se solapan.

    La deteccion cae dentro de las dos ventanas; gana el evento mas antiguo,
    que es el orden en el que se esta tocando la pista.
    """
    ev = Evaluador(pista_de(nota(1.0, 40), nota(1.1, 40)))
    resultados = ev.avanzar(1.05, [deteccion(1.05, 40)])
    assert tipos(resultados) == [ACIERTO]
    assert resultados[0].indice == 0
    # La segunda sigue pendiente y se cierra sola.
    assert tipos(ev.avanzar(DESPUES)) == [FALLO]


def test_dos_detecciones_en_el_mismo_bloque_se_ordenan_por_timestamp():
    ev = Evaluador(pista_de(nota(1.0, 40), nota(1.1, 45)))
    resultados = ev.avanzar(1.2, [deteccion(1.1, 45), deteccion(1.0, 40)])
    assert tipos(resultados) == [ACIERTO, ACIERTO]
    assert [r.indice for r in resultados] == [0, 1]


def test_una_deteccion_no_puede_acertar_dos_eventos():
    ev = Evaluador(pista_de(nota(1.0, 40), nota(1.05, 40)))
    resultados = ev.avanzar(1.02, [deteccion(1.02, 40)])
    assert tipos(resultados) == [ACIERTO]
    assert ev.resumen.aciertos == 1


# ------------------------------------------------------------------- resumen

def test_los_errores_medios_llevan_signo():
    """Un promedio con signo dice algo accionable: 'vas tarde' o 'vas agudo'.
    Con valor absoluto esa informacion se pierde."""
    eventos = [nota(1.0, 40), nota(2.0, 45), nota(3.0, 50)]
    ev = Evaluador(pista_de(*eventos))
    for t, midi in ((1.0, 40), (2.0, 45), (3.0, 50)):
        ev.avanzar(t + 0.05, [deteccion(t + 0.05, midi, 20.0)])
    resumen = ev.resumen
    assert resumen.error_temporal_medio_s == pytest.approx(0.05, abs=1e-6)
    assert resumen.error_cents_medio == pytest.approx(20.0, abs=0.01)


def test_la_racha_se_corta_con_un_fallo_y_se_recuerda_la_maxima():
    eventos = [nota(float(i), 40) for i in range(5)]
    ev = Evaluador(pista_de(*eventos))
    ev.avanzar(0.0, [deteccion(0.0, 40)])
    ev.avanzar(1.0, [deteccion(1.0, 40)])
    ev.avanzar(2.0 + 0.12 + RETARDO_MOTOR_S + 0.01)     # se pierde la de t=2
    ev.avanzar(3.0, [deteccion(3.0, 40)])
    ev.avanzar(DESPUES)
    resumen = ev.resumen
    assert resumen.racha_maxima == 2
    assert (resumen.aciertos, resumen.fallos) == (3, 2)


def test_resumen_de_una_pista_intacta():
    ev = Evaluador(pista_de(nota(1.0, 40), nota(2.0, 45)))
    resumen = ev.resumen
    assert resumen.total == 2
    assert (resumen.aciertos, resumen.fallos, resumen.extras) == (0, 0, 0)
    assert resumen.error_temporal_medio_s == 0.0
    assert not ev.terminado


# -------------------------------------------------------------- configurable

def test_las_tolerancias_son_configurables():
    estricto = Tolerancias(temporal_s=0.03, cents=10.0)
    ev = Evaluador(pista_de(nota(1.0, 40)), tolerancias=estricto)
    assert set(tipos(ev.avanzar(DESPUES, [deteccion(1.05, 40)]))) == {EXTRA, FALLO}

    permisivo = Tolerancias(temporal_s=0.25, cents=49.0)
    ev = Evaluador(pista_de(nota(1.0, 40)), tolerancias=permisivo)
    assert tipos(ev.avanzar(1.2, [deteccion(1.2, 40, 45.0)])) == [ACIERTO]


def test_una_frecuencia_invalida_no_revienta():
    ev = Evaluador(pista_de(nota(1.0, 40)))
    resultados = ev.avanzar(DESPUES, [Deteccion(t=1.0, f0=0.0)])
    assert set(tipos(resultados)) == {EXTRA, FALLO}


def test_pista_sin_detecciones_termina_toda_en_fallos():
    eventos = [nota(float(i), 40 + i) for i in range(4)]
    ev = Evaluador(pista_de(*eventos))
    resultados = ev.avanzar(DESPUES)
    assert tipos(resultados) == [FALLO] * 4
    assert ev.resumen.fallos == 4
    assert ev.terminado
