"""Pruebas de la maquina de estados del juego. Sin ventana y sin microfono."""

import pytest

from nucleo.evaluador import Tolerancias
from nucleo.pista import cargar, desde_dict
from nucleo.puntaje import puntos_por_acierto
from juego.sesion import (ACERTADA, FALLADA, JUGANDO, MENU, PENDIENTE,
                          RESULTADOS, Sesion)
from nucleo.simulacion import PERFILES, generar_detecciones


class AtaqueFalso:
    """Lo minimo que la sesion usa de un Ataque del motor de audio."""

    def __init__(self, t, f0):
        self.t = t
        self.f0 = f0


def pista_simple(cantidad=3, paso=1.0):
    return desde_dict({"titulo": "prueba", "bpm": 60, "eventos": [
        {"t": i * paso, "dur": 0.5, "tipo": "nota", "midi": 40 + i * 5}
        for i in range(cantidad)]})


def sesion(pistas=None, **kw):
    return Sesion(pistas or [pista_simple()], **kw)


# -------------------------------------------------------------------- estados

def test_arranca_en_el_menu():
    s = sesion()
    assert s.estado == MENU
    assert s.seleccion == 0
    assert s.resumen is None


def test_la_seleccion_da_la_vuelta():
    s = sesion([pista_simple(), pista_simple(), pista_simple()])
    s.mover_seleccion(1)
    assert s.seleccion == 1
    s.mover_seleccion(-2)
    assert s.seleccion == 2      # dio la vuelta
    s.mover_seleccion(1)
    assert s.seleccion == 0


def test_la_seleccion_no_se_mueve_mientras_se_juega():
    s = sesion([pista_simple(), pista_simple()])
    s.empezar(0.0)
    s.mover_seleccion(1)
    assert s.seleccion == 0


def test_empezar_pasa_a_jugando_con_la_pista_entrando_por_arriba():
    s = sesion(ventana_vista_s=3.0)
    s.empezar(10.0)
    assert s.estado == JUGANDO
    # El reloj de pista empieza en negativo: la primera nota recien entra.
    assert s.t_pista == pytest.approx(-3.0)


def test_la_sesion_necesita_al_menos_una_pista():
    with pytest.raises(ValueError):
        Sesion([])


def test_se_pasa_a_resultados_cuando_termina_la_pista():
    s = sesion()
    s.empezar(0.0)
    s.avanzar(1000.0)
    assert s.estado == RESULTADOS
    assert s.resumen.total == 3


def test_volver_al_menu_y_reintentar():
    s = sesion()
    s.empezar(0.0)
    s.avanzar(1000.0)
    s.al_menu()
    assert s.estado == MENU
    s.reintentar(2000.0)
    assert s.estado == JUGANDO
    assert s.puntaje == 0


def test_avanzar_fuera_de_jugando_no_hace_nada():
    s = sesion()
    assert s.avanzar(5.0, [AtaqueFalso(5.0, 110.0)]) == ()


# ------------------------------------------------------- los dos relojes

def test_los_timestamps_se_traducen_al_reloj_de_la_pista():
    """El motor cuenta desde que abrio el stream; la pista desde que empieza.

    Si no se restara el desfase, el evaluador veria todo fuera de tiempo.
    """
    from audio.notas import midi_a_hz
    s = sesion(ventana_vista_s=3.0)
    s.empezar(100.0)                 # la pista arranca en t_audio 103.0
    # El evento 0 va en t_pista 0.0, o sea t_audio 103.0.
    s.avanzar(103.0, [AtaqueFalso(103.0, midi_a_hz(40))])
    assert s.resumen.aciertos == 1
    assert s.resumen.error_temporal_medio_s == pytest.approx(0.0, abs=1e-9)


def test_lo_que_suena_durante_la_entrada_no_se_evalua():
    """Antes de la primera nota se esta afinando o acomodando, no tocando."""
    from audio.notas import midi_a_hz
    s = sesion(ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(1.0, [AtaqueFalso(1.0, midi_a_hz(45))])   # t_pista = -2.0
    assert s.resumen.extras == 0


# ------------------------------------------------------- modelo de vista

def test_solo_se_ven_las_notas_dentro_de_la_ventana():
    s = sesion([pista_simple(cantidad=10, paso=1.0)], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0)               # t_pista = 0.0
    indices = [n.indice for n in s.notas_en_vista()]
    assert indices == [0, 1, 2, 3]       # la de t=3.0 recien entra


def test_las_notas_bajan_a_medida_que_pasa_el_tiempo():
    s = sesion([pista_simple(cantidad=4)], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0)
    primera = next(n for n in s.notas_en_vista() if n.indice == 1)
    s.avanzar(3.5)
    despues = next(n for n in s.notas_en_vista() if n.indice == 1)
    assert despues.restante < primera.restante


def test_una_nota_acertada_queda_marcada_para_el_render():
    from audio.notas import midi_a_hz
    s = sesion(ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0, [AtaqueFalso(3.0, midi_a_hz(40))])
    vista = next(n for n in s.notas_en_vista() if n.indice == 0)
    assert vista.estado == ACERTADA


def test_una_nota_no_tocada_queda_marcada_como_fallada():
    s = sesion([pista_simple(cantidad=3, paso=2.0)], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0 + 0.5)         # pasa la ventana del evento 0
    estados = {n.indice: n.estado for n in s.notas_en_vista()}
    assert estados[0] == FALLADA
    assert estados[1] == PENDIENTE


def test_una_nota_fallada_sigue_en_pantalla_cuando_se_marca():
    """Si no, el rojo nunca se veria.

    El fallo se confirma tarde a proposito: hay que esperar la ventana
    temporal mas el retardo del motor. El margen de salida del highway tiene
    que alcanzar para cubrir esa espera.
    """
    from nucleo.evaluador import RETARDO_MOTOR_S
    from juego.geometria import MARGEN_SALIDA_S
    s = sesion([pista_simple(cantidad=3, paso=2.0)], ventana_vista_s=3.0)
    s.empezar(0.0)

    cuadro = 0
    while cuadro < 600:
        s.avanzar(3.0 + cuadro / 60)
        vistas = {n.indice: n for n in s.notas_en_vista()}
        if 0 in vistas and vistas[0].estado == FALLADA:
            break
        cuadro += 1
    else:
        raise AssertionError("el evento 0 nunca se vio marcado como fallado")

    # Y todavia queda tiempo de pantalla para que el aviso se vea.
    espera = s.tolerancias.temporal_s + RETARDO_MOTOR_S
    assert espera < MARGEN_SALIDA_S
    assert vistas[0].restante > -MARGEN_SALIDA_S


def test_cada_nota_en_vista_trae_su_carril():
    s = sesion([cargar("pistas/01_cuerdas_al_aire.json")], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0)
    for vista in s.notas_en_vista():
        assert vista.carriles
        assert all(1 <= c <= 6 for c in vista.carriles)


def test_el_progreso_va_de_cero_a_uno():
    s = sesion([pista_simple(cantidad=3, paso=1.0)], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0)
    assert s.progreso == pytest.approx(0.0)
    s.avanzar(1000.0)
    assert s.progreso == 1.0


# -------------------------------------------------------------------- avisos

def test_un_acierto_deja_un_aviso_en_su_carril():
    from audio.notas import midi_a_hz
    s = sesion([cargar("pistas/01_cuerdas_al_aire.json")], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0, [AtaqueFalso(3.0, midi_a_hz(40))])   # E2, 6a cuerda
    avisos = s.avisos_vigentes()
    assert len(avisos) == 1
    assert avisos[0].carril == 6
    assert avisos[0].texto == "PERFECTO"


def test_un_acierto_tarde_dice_cuanto():
    from audio.notas import midi_a_hz
    s = sesion(ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.08, [AtaqueFalso(3.08, midi_a_hz(40))])
    assert s.avisos_vigentes()[0].texto == "+80 ms"


def test_una_nota_desafinada_dice_si_esta_alta_o_baja():
    """Es la devolucion que hace util distinguir afinacion de nota ajena."""
    from audio.notas import midi_a_hz
    for cents, esperado in ((45.0, "ALTO"), (-45.0, "BAJO")):
        s = sesion(ventana_vista_s=3.0)
        s.empezar(0.0)
        f0 = midi_a_hz(40) * 2.0 ** (cents / 1200.0)
        s.avanzar(3.0, [AtaqueFalso(3.0, f0)])
        textos = [a.texto for a in s.avisos_vigentes()]
        assert any(esperado in t for t in textos), textos


def test_los_avisos_se_borran_solos():
    from audio.notas import midi_a_hz
    from juego.sesion import DURACION_AVISO_S
    s = sesion(ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0, [AtaqueFalso(3.0, midi_a_hz(40))])
    aviso = s.avisos_vigentes()[0]
    assert aviso.texto == "PERFECTO"

    # Avanzar genera avisos nuevos (los fallos de las notas que no se
    # tocaron), asi que lo que se comprueba es que este ya no este.
    s.avanzar(3.0 + DURACION_AVISO_S + 0.1)
    assert aviso not in s.avisos_vigentes()


# ------------------------------------------------------------------- puntaje

def test_el_puntaje_crece_con_la_racha():
    from audio.notas import midi_a_hz
    pista = pista_simple(cantidad=3, paso=1.0)
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    esperado = 0
    for i in range(3):
        t = 3.0 + i
        s.avanzar(t, [AtaqueFalso(t, midi_a_hz(40 + i * 5))])
        esperado += puntos_por_acierto(i + 1)
        assert s.puntaje == esperado
    assert s.resumen.racha == 3


def test_fallar_todo_deja_el_puntaje_en_cero():
    s = sesion()
    s.empezar(0.0)
    s.avanzar(1000.0)
    assert s.puntaje == 0
    assert s.resumen.fallos == 3


# ----------------------------------------------------- pasada completa

def test_una_pasada_perfecta_de_punta_a_punta():
    """Integracion: la sesion con detecciones perfectas acierta todo."""
    pista = cargar("pistas/02_escala_do_mayor.json")
    s = Sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    detecciones = generar_detecciones(pista, PERFILES["perfecto"])
    pendientes = list(detecciones)
    paso = 1.0 / 60
    from nucleo.evaluador import RETARDO_MOTOR_S
    cuadro = 0
    while s.estado == JUGANDO and cuadro < 60 * 30:
        t_audio = cuadro * paso
        t_pista = t_audio - 3.0
        listos = [d for d in pendientes if d.t + RETARDO_MOTOR_S <= t_pista]
        pendientes = [d for d in pendientes if d not in listos]
        s.avanzar(t_audio, [AtaqueFalso(d.t + 3.0, d.f0) for d in listos])
        cuadro += 1
    assert s.estado == RESULTADOS
    assert s.resumen.aciertos == s.resumen.total == len(pista.eventos)
    assert s.resumen.fallos == 0
    assert s.puntaje > 0
