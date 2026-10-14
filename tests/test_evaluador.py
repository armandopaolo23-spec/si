"""Pruebas del evaluador. Logica pura: detecciones inventadas, sin audio."""

import pytest

from audio.notas import midi_a_hz
from nucleo.evaluador import (ACIERTO, ACORDE_INCOMPLETO, AFINACION, EXTRA,
                              FALLO, RETARDO_MOTOR_S, SIN_ALTURA, SIN_EVENTO,
                              Compensacion, Deteccion, Evaluador, Tolerancias)
from nucleo.pista import desde_dict
from nucleo.simulacion import energias_de

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

EM = [40, 47, 52, 55, 59, 64]
AM = [45, 52, 57, 60, 64]
C = [48, 52, 55, 60, 64]


def rasgueo(t, midis):
    """Deteccion de un rasgueo: energia por semitono, sin pitch."""
    return Deteccion(t=t, energias=energias_de(midis))


def test_un_rasgueo_del_acorde_pedido_acierta():
    ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
    resultados = ev.avanzar(1.0, [rasgueo(1.0, EM)])
    assert tipos(resultados) == [ACIERTO]
    assert resultados[0].faltantes == ()
    assert resultados[0].nombre_oido == "Em"


def test_una_sola_nota_del_acorde_ya_no_alcanza():
    """Hasta la fase 4 bastaba con acertar una nota, porque YIN es monofonico
    y no habia con que exigir mas. Con el croma, rasguear mal se nota."""
    ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
    resultados = ev.avanzar(DESPUES, [deteccion(1.0, 40)])
    assert ACIERTO not in tipos(resultados)


def test_rasguear_otro_acorde_no_acierta():
    """Do comparte dos de las tres notas de Mi menor; tiene que rechazarse."""
    for ajeno in (AM, C):
        ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
        resultados = ev.avanzar(DESPUES, [rasgueo(1.0, ajeno)])
        assert ACIERTO not in tipos(resultados), ajeno


def test_una_cuerda_floja_se_perdona_pero_se_informa():
    """Quien empieza no aprieta parejo. Un acorde al que le falta una cuerda
    se da por bueno, pero el resultado dice cual fue."""
    ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
    sin_la_tercera = [m for m in EM if m != 55]
    resultados = ev.avanzar(1.0, [rasgueo(1.0, sin_la_tercera)])
    assert tipos(resultados) == [ACIERTO]
    assert 55 in resultados[0].faltantes


def test_un_acorde_mal_armado_dice_que_cuerdas_faltaron():
    """La devolucion util para quien aprende no es "no", es "te falto esta".

    Se dejan fuera las dos cuerdas graves porque son las que no se pueden
    falsear: los armonicos van hacia arriba, asi que si falta un E2 no hay
    nada que pueda ponerlo. Ver
    test_las_notas_agudas_si_las_pueden_poner_los_armonicos.
    """
    ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
    solo_las_agudas = EM[2:]
    resultados = ev.avanzar(DESPUES, [rasgueo(1.0, solo_las_agudas)])
    extra = next(r for r in resultados if r.tipo == EXTRA)
    assert extra.motivo == ACORDE_INCOMPLETO
    assert extra.indice == 0
    assert set(EM[:2]) <= set(extra.faltantes)


def test_las_notas_agudas_si_las_pueden_poner_los_armonicos():
    """Limite conocido del metodo, que conviene tener escrito.

    Tocando solo E2 y B2, los armonicos de E2 caen en E3, B3 y E4, que son
    otras tres notas del acorde: fisicamente esas frecuencias suenan, asi que
    medir presencia no puede distinguirlo de un Em completo. Lo que lo
    delataria es el G3, que no es armonico de ninguna de las dos.
    """
    ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
    assert tipos(ev.avanzar(1.0, [rasgueo(1.0, EM[:2])])) == [ACIERTO]


def test_un_rasgueo_tiene_ventana_temporal_mas_ancha_que_una_nota():
    """Las seis cuerdas no suenan juntas: el barrido corre el onset."""
    tolerancias = Tolerancias()
    assert tolerancias.temporal_acorde_s > tolerancias.temporal_s
    ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
    desfase = (tolerancias.temporal_s + tolerancias.temporal_acorde_s) / 2
    assert tipos(ev.avanzar(1.0 + desfase,
                            [rasgueo(1.0 + desfase, EM)])) == [ACIERTO]


def test_una_deteccion_sin_energias_no_puede_juzgar_un_acorde():
    """Un ataque que se cerro antes de llenar la ventana armonica no trae con
    que decidir, y decir que no sono el acorde es lo honesto."""
    ev = Evaluador(pista_de(acorde(1.0, EM, nombre="Em")))
    resultados = ev.avanzar(DESPUES, [Deteccion(t=1.0, f0=None)])
    assert ACIERTO not in tipos(resultados)


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


# ------------------------------------------------- por que no acerto

def test_un_extra_sin_nada_cerca_dice_sin_evento():
    ev = Evaluador(pista_de(nota(1.0, 40)))
    extra = next(r for r in ev.avanzar(5.0, [deteccion(5.0, 40)])
                 if r.tipo == EXTRA)
    assert extra.motivo == SIN_EVENTO
    assert extra.indice is None


def test_un_extra_que_solo_fallo_la_afinacion_lo_dice_y_señala_el_evento():
    """Decir "no habia nada pedido ahi" cuando si habia es enganoso.

    Es el caso que aparecio en la simulacion: una deteccion de D3 a 2.5 ms
    del evento que pedia D3, rechazada por estar 37 cents alta. Son dos
    errores distintos -nota equivocada contra nota desafinada- y se corrigen
    de forma distinta, asi que el evaluador tiene que diferenciarlos.
    """
    ev = Evaluador(pista_de(nota(1.0, 50)))
    extra = next(r for r in ev.avanzar(DESPUES, [deteccion(1.0025, 50, 37.0)])
                 if r.tipo == EXTRA)
    assert extra.motivo == AFINACION
    assert extra.indice == 0
    assert extra.error_cents == pytest.approx(37.0, abs=0.1)
    assert extra.error_s == pytest.approx(0.0025, abs=1e-6)


def test_el_evento_igual_falla_aparte_del_extra_por_afinacion():
    ev = Evaluador(pista_de(nota(1.0, 50)))
    resultados = ev.avanzar(DESPUES, [deteccion(1.0, 50, 40.0)])
    assert tipos(resultados) == [EXTRA, FALLO]
    assert all(r.indice == 0 for r in resultados)
    assert ev.resumen.extras == 1
    assert ev.resumen.fallos == 1


def test_fuera_de_la_ventana_temporal_no_es_problema_de_afinacion():
    """Si el golpe esta lejos en el tiempo, el motivo no es la afinacion
    aunque la nota fuera la correcta."""
    ev = Evaluador(pista_de(nota(1.0, 40)))
    extra = next(r for r in ev.avanzar(DESPUES, [deteccion(1.5, 40)])
                 if r.tipo == EXTRA)
    assert extra.motivo == SIN_EVENTO


def test_entre_varios_candidatos_desafinados_señala_el_menos_desviado():
    ev = Evaluador(pista_de(nota(1.0, 40), nota(1.05, 45)))
    # Suena algo a 45 cents de A2 (evento 1) y muy lejos de E2 (evento 0).
    extra = next(r for r in ev.avanzar(DESPUES, [deteccion(1.02, 45, 45.0)])
                 if r.tipo == EXTRA)
    assert extra.motivo == AFINACION
    assert extra.indice == 1



# ------------------------------------------------- golpes sin altura clara

def test_un_golpe_sin_altura_donde_se_pedia_una_nota_lo_dice():
    """Cuerda mal pisada o traste que zumba: sono algo, pero sin nota.

    Desde que los ataques traen energias ya no se descartan en silencio, y
    antes de este motivo salian como "nada pedido ahi" aunque hubiera una
    nota pedida en ese mismo instante.
    """
    ev = Evaluador(pista_de(nota(1.0, 53)))
    resultados = ev.avanzar(DESPUES, [Deteccion(t=1.0, energias=energias_de([53]))])
    extra = next(r for r in resultados if r.tipo == EXTRA)
    assert extra.motivo == SIN_ALTURA
    assert extra.indice == 0


def test_un_golpe_sin_altura_lejos_de_todo_sigue_siendo_sin_evento():
    ev = Evaluador(pista_de(nota(1.0, 53)))
    resultados = ev.avanzar(DESPUES, [Deteccion(t=5.0, energias=energias_de([53]))])
    extra = next(r for r in resultados if r.tipo == EXTRA)
    assert extra.motivo == SIN_EVENTO


def test_el_resumen_cuenta_las_notas_de_mas_por_motivo():
    ev = Evaluador(pista_de(nota(1.0, 40), nota(3.0, 45), nota(5.0, 50)))
    ev.avanzar(DESPUES, [
        Deteccion(t=1.0, energias=energias_de([40])),   # sin altura
        deteccion(3.0, 45, 50.0),                        # desafinada
        deteccion(8.0, 50),                              # fuera de lugar
    ])
    assert ev.resumen.extras_por_motivo == {
        SIN_ALTURA: 1, AFINACION: 1, SIN_EVENTO: 1}


# -------------------------------------------- compensacion por tipo de evento

def test_la_compensacion_de_notas_no_toca_los_acordes():
    compensacion = Compensacion(nota_s=0.1, acorde_s=0.0)
    ev = Evaluador(pista_de(nota(1.0, 40), acorde(3.0, EM, nombre="Em")),
                   compensacion=compensacion)
    ev.avanzar(DESPUES, [deteccion(0.9, 40), rasgueo(3.0, EM)])
    resumen = ev.resumen
    assert resumen.aciertos == 2
    assert resumen.error_temporal_notas_s == pytest.approx(0.0, abs=1e-9)
    assert resumen.error_temporal_acordes_s == pytest.approx(0.0, abs=1e-9)


def test_la_compensacion_de_acordes_no_toca_las_notas():
    compensacion = Compensacion(nota_s=0.0, acorde_s=0.109)
    ev = Evaluador(pista_de(nota(1.0, 40), acorde(3.0, EM, nombre="Em")),
                   compensacion=compensacion)
    ev.avanzar(DESPUES, [deteccion(1.0, 40), rasgueo(3.0 - 0.109, EM)])
    resumen = ev.resumen
    assert resumen.error_temporal_notas_s == pytest.approx(0.0, abs=1e-9)
    assert resumen.error_temporal_acordes_s == pytest.approx(0.0, abs=1e-9)


def test_con_compensacion_negativa_la_ventana_espera_lo_que_haga_falta():
    """Quien se atrasa 150 ms: su deteccion entra en la ventana despues de
    compensada, pero llega mas tarde de lo que cubre el retardo del motor.
    Si la ventana se cerrara antes, seria un fallo inventado."""
    ev = Evaluador(pista_de(nota(1.0, 40)),
                   compensacion=Compensacion(nota_s=-0.15))
    llega = 1.15 + RETARDO_MOTOR_S
    assert ev.avanzar(llega - 0.001) == ()
    assert tipos(ev.avanzar(llega, [deteccion(1.15, 40)])) == [ACIERTO]
