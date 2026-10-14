"""Pruebas de la maquina de estados del juego. Sin ventana y sin microfono."""

import pytest

from nucleo.evaluador import Tolerancias
from nucleo.pista import cargar, desde_dict
from nucleo.puntaje import puntos_por_acierto
from juego.sesion import (ACERTADA, FALLADA, JUGANDO, MENU, PENDIENTE,
                          RESULTADOS, Sesion)
from nucleo.simulacion import PERFILES, generar_detecciones


class AtaqueFalso:
    """Lo minimo que la sesion usa de un Ataque del motor de audio.

    `energias` es la medida armonica con la que se juzgan los rasgueos; en una
    nota suelta el motor tampoco la necesita, pero el campo existe siempre.
    """

    def __init__(self, t, f0=None, energias=None):
        self.t = t
        self.f0 = f0
        self.energias = energias


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
    tope = int(60 * (pista.duracion + 3.0 + RETARDO_MOTOR_S + 2.0))
    while s.estado == JUGANDO and cuadro < tope:
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


# --------------------------------------------- compensacion personal

def test_el_desfase_corre_las_detecciones_antes_de_comparar():
    """Quien toca 73 ms adelantado, con --desfase-ms 73 queda centrado."""
    from audio.notas import midi_a_hz
    adelanto = 0.073
    for desfase, esperado in ((0.0, -adelanto), (adelanto, 0.0)):
        s = sesion(ventana_vista_s=3.0, desfase_s=desfase)
        s.empezar(0.0)
        t = 3.0 - adelanto                      # se toca antes de tiempo
        s.avanzar(3.0, [AtaqueFalso(t, midi_a_hz(40))])
        assert s.resumen.aciertos == 1
        assert s.resumen.error_temporal_medio_s == pytest.approx(esperado,
                                                                 abs=1e-9)


def tocar_notas_corridas(adelanto, desfase=0.0, cantidad=6):
    """Toca una pista de notas sueltas, todas `adelanto` segundos antes."""
    from audio.notas import midi_a_hz
    pista = pista_simple(cantidad=cantidad, paso=1.0)
    s = sesion([pista], ventana_vista_s=3.0, desfase_s=desfase)
    s.empezar(0.0)
    for evento in pista.eventos:
        t = 3.0 + evento.t
        s.avanzar(t, [AtaqueFalso(t - adelanto, midi_a_hz(evento.midi))])
    s.avanzar(1000.0)
    return s


def tocar_pista_mixta(adelanto_notas, adelanto_acordes, desfase_acorde=0.0):
    """La pista 4, con notas y rasgueos corridos cada uno a su manera."""
    from audio.notas import midi_a_hz
    from nucleo.simulacion import energias_de
    pista = cargar("pistas/04_acordes_y_melodia.json")
    s = sesion([pista], ventana_vista_s=3.0, desfase_acorde_s=desfase_acorde)
    s.empezar(0.0)
    for evento in pista.eventos:
        t = 3.0 + evento.t
        if evento.tipo == "acorde":
            ataque = AtaqueFalso(t - adelanto_acordes,
                                 energias=energias_de(evento.notas))
        else:
            ataque = AtaqueFalso(t - adelanto_notas, midi_a_hz(evento.midi))
        s.avanzar(t, [ataque])
    s.avanzar(1000.0)
    return s


def test_el_desfase_sugerido_centra_el_sesgo():
    assert tocar_notas_corridas(0.073).desfase_sugerido_notas_ms == 73


def test_el_desfase_sugerido_es_acumulativo():
    """Sirve tal cual aunque la pasada ya viniera con desfase aplicado.

    Si no acumulara, cada pasada propondria una correccion sobre la anterior
    y el valor oscilaria en vez de converger.
    """
    s = tocar_notas_corridas(0.120, desfase=0.030)
    assert s.desfase_sugerido_notas_ms == 120


def test_un_desfase_chico_no_se_sugiere():
    """Es lo que paso con la guitarra real: 26 ms con seis notas.

    El detector ya tiene unos 20 ms de error propio y una pasada corta suma
    jitter; sugerir compensar eso seria ajustar ruido.
    """
    assert tocar_notas_corridas(0.026).desfase_sugerido_notas_ms is None


def test_con_pocos_aciertos_no_se_sugiere_nada():
    assert tocar_notas_corridas(0.073, cantidad=3).desfase_sugerido_notas_ms is None


def test_sin_aciertos_no_hay_desfase_que_sugerir():
    s = sesion()
    s.empezar(0.0)
    s.avanzar(1000.0)
    assert s.resumen.aciertos == 0
    assert s.desfase_sugerido_notas_ms is None
    assert s.desfase_sugerido_acordes_ms is None


def test_notas_y_rasgueos_se_miden_y_se_sugieren_por_separado():
    """El caso real: notas sueltas casi a tiempo, rasgueos 109 ms adelante.

    Con un desfase unico calibrado con acordes, las notas quedarian unos
    90 ms tarde. Por eso cada tipo tiene el suyo.
    """
    s = tocar_pista_mixta(adelanto_notas=0.010, adelanto_acordes=0.109)
    resumen = s.resumen
    assert resumen.aciertos == resumen.total
    assert resumen.error_temporal_notas_s == pytest.approx(-0.010, abs=1e-6)
    assert resumen.error_temporal_acordes_s == pytest.approx(-0.109, abs=1e-6)
    assert s.desfase_sugerido_notas_ms is None
    assert s.desfase_sugerido_acordes_ms == 109


def test_compensar_los_acordes_no_mueve_las_notas():
    s = tocar_pista_mixta(adelanto_notas=0.010, adelanto_acordes=0.109,
                          desfase_acorde=0.109)
    resumen = s.resumen
    assert resumen.error_temporal_acordes_s == pytest.approx(0.0, abs=1e-6)
    assert resumen.error_temporal_notas_s == pytest.approx(-0.010, abs=1e-6)
    assert s.desfase_sugerido_acordes_ms is None


def test_una_nota_que_no_suena_clara_lo_dice():
    """Antes salia "rasgueo de mas" aunque hubiera una nota pedida ahi mismo."""
    from nucleo.simulacion import energias_de
    s = sesion(ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0, [AtaqueFalso(3.0, energias=energias_de([40]))])
    assert "no sono clara" in [a.texto for a in s.avisos_vigentes()]


# ------------------------------------------------------- diagrama de acorde

def test_una_pista_de_solo_punteo_no_tiene_acorde_que_mostrar():
    s = sesion([cargar("pistas/02_escala_do_mayor.json")], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0)
    assert s.acorde_a_la_vista() is None


def test_el_diagrama_muestra_el_acorde_que_viene():
    """Desde el arranque, antes incluso de que el acorde entre en pantalla."""
    pista = cargar("pistas/04_acordes_y_melodia.json")
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0)
    primero = next(e for e in pista.eventos if e.tipo == "acorde")
    assert s.acorde_a_la_vista() is primero


def test_el_acorde_sigue_visible_un_rato_despues_de_tocarlo():
    """Para poder comprobar la posicion de la mano recien hecha."""
    pista = cargar("pistas/04_acordes_y_melodia.json")
    primero = next(e for e in pista.eventos if e.tipo == "acorde")
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0 + primero.t + 0.3)
    assert s.acorde_a_la_vista() is primero


def test_el_diagrama_pasa_al_acorde_siguiente():
    pista = cargar("pistas/04_acordes_y_melodia.json")
    acordes = [e for e in pista.eventos if e.tipo == "acorde"]
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0 + acordes[0].t + 1.0)   # el primero ya quedo atras
    assert s.acorde_a_la_vista() is acordes[1]


def test_al_final_de_la_pista_ya_no_hay_acorde():
    pista = cargar("pistas/04_acordes_y_melodia.json")
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0 + pista.duracion + 1.0)
    assert s.acorde_a_la_vista() is None


# --------------------------------------------------------- rasgueo de acordes

def energias_de_acorde(midis):
    from nucleo.simulacion import energias_de
    return energias_de(midis)


def test_un_rasgueo_correcto_acierta_el_acorde():
    pista = cargar("pistas/03_acordes_basicos.json")
    primero = pista.eventos[0]
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    t = 3.0 + primero.t
    s.avanzar(t, [AtaqueFalso(t, energias=energias_de_acorde(primero.notas))])
    assert s.resumen.aciertos == 1
    assert s.avisos_vigentes()[0].texto == "PERFECTO"


def test_un_acorde_con_una_cuerda_floja_avisa_cual():
    """La devolucion que sirve para aprender es que cuerda no sono."""
    pista = cargar("pistas/03_acordes_basicos.json")
    primero = pista.eventos[0]           # Em: 6a 5a 4a 3a 2a 1a
    sin_la_tercera = [m for m in primero.notas if m != 55]
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    t = 3.0 + primero.t
    s.avanzar(t, [AtaqueFalso(t, energias=energias_de_acorde(sin_la_tercera))])
    textos = [a.texto for a in s.avisos_vigentes()]
    assert any("3a" in texto for texto in textos), textos


def test_un_acorde_mal_armado_avisa_las_cuerdas_graves_que_faltan():
    pista = cargar("pistas/03_acordes_basicos.json")
    primero = pista.eventos[0]
    solo_agudas = list(primero.notas)[2:]
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    t = 3.0 + primero.t
    s.avanzar(t, [AtaqueFalso(t, energias=energias_de_acorde(solo_agudas))])
    s.avanzar(1000.0)
    assert s.resumen.aciertos == 0
    assert s.resumen.extras == 1


def test_un_rasgueo_sin_evento_cerca_no_revienta():
    """Antes el aviso de nota de mas leia la frecuencia, que en un rasgueo
    viene en None."""
    pista = cargar("pistas/03_acordes_basicos.json")
    s = sesion([pista], ventana_vista_s=3.0)
    s.empezar(0.0)
    s.avanzar(3.0 + 1.0,
              [AtaqueFalso(3.0 + 1.0, energias=energias_de_acorde([40, 47]))])
    assert any("rasgueo" in a.texto or "falta" in a.texto
               for a in s.avisos_vigentes())
