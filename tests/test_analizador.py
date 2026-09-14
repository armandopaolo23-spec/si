"""Pruebas de la canalizacion completa, sin microfono ni ventana.

Todas las señales se sintetizan en tests/sintesis.py. El Analizador solo
recibe arrays, asi que estas pruebas cubren el camino que en produccion
alimenta sounddevice.
"""

import numpy as np
import pytest

from audio.analizador import SALTO, Analizador
from audio.notas import CUERDAS_ESTANDAR, midi_a_hz, nombre_midi
from tests.sintesis import SR, pulsacion, secuencia

# Tolerancia temporal de las pruebas. El timestamp se corrige con
# RETARDO_ONSET_S y el error residual medido queda por debajo de 20 ms, que es
# menos de dos saltos de analisis.
TOLERANCIA_S = 0.025


def analizar(x, bloque=SALTO, **opciones):
    analizador = Analizador(**opciones)
    ataques = []
    for inicio in range(0, len(x), bloque):
        ataques.extend(analizador.procesar(x[inicio:inicio + bloque]))
    return ataques, analizador


def emparejar(ataques, reales):
    """Para cada ataque, el error de timestamp contra el golpe real mas cercano."""
    return [ataque.t - min(reales, key=lambda t: abs(t - ataque.t))
            for ataque in ataques]


# La puerta de ruido tiene que ir acorde al nivel de entrada: con una señal
# cuyas notas apenas llegan a 0.004 de RMS, la puerta por defecto de 0.003 se
# come las cuerdas centrales. Es justo el ajuste que expone --umbral en la CLI.
@pytest.mark.parametrize("recorte_graves, amplitud, umbral_ruido", [
    (0.0, 0.15, 0.003),      # señal limpia
    (0.7, 0.15, 0.003),      # microfono que recorta graves
    (0.9, 0.02, 0.003),      # graves debiles, al filo de la puerta por defecto
    (1.0, 0.012, 0.0015),    # sin fundamental y muy debil: el peor caso
])
def test_seis_cuerdas_al_aire(recorte_graves, amplitud, umbral_ruido):
    notas = [(0.5 + 0.6 * i, midi_a_hz(midi), 0.55)
             for i, midi in enumerate(CUERDAS_ESTANDAR)]
    x, reales = secuencia(notas, 4.8, recorte_graves=recorte_graves,
                          amplitud=amplitud)
    ataques, analizador = analizar(x, umbral_ruido=umbral_ruido)

    assert len(ataques) == 6
    assert analizador.descartados == 0
    assert [a.nota.nombre for a in ataques] == \
        [nombre_midi(m) for m in CUERDAS_ESTANDAR]
    assert max(abs(e) for e in emparejar(ataques, reales)) < TOLERANCIA_S
    assert all(abs(a.nota.cents) < 5.0 for a in ataques)
    assert all(a.confianza > 0.7 for a in ataques)


def test_una_nota_sostenida_cuenta_una_sola_vez():
    """El motivo de existir del detector de onset."""
    x = np.concatenate([
        np.zeros(int(0.3 * SR)),
        pulsacion(midi_a_hz(40), 2.5, decaimiento=0.6, recorte_graves=0.7,
                  semilla=1),
    ]).astype(np.float32)
    ataques, _ = analizar(x)
    assert len(ataques) == 1
    assert ataques[0].nota.nombre == "E2"
    assert abs(ataques[0].t - 0.3) < TOLERANCIA_S


@pytest.mark.parametrize("separacion", [0.125, 0.15, 0.2, 0.3])
def test_repique_de_la_misma_cuerda(separacion):
    """Repicar sin dejar apagar la cuerda: el caso que el RMS no ve."""
    notas = [(0.3 + separacion * i, midi_a_hz(45), 0.45) for i in range(8)]
    x, reales = secuencia(notas, 0.3 + separacion * 8 + 0.8,
                          recorte_graves=0.7)
    ataques, analizador = analizar(x)

    assert len(ataques) == 8
    assert analizador.descartados == 0
    assert all(a.nota.nombre == "A2" for a in ataques)
    assert max(abs(e) for e in emparejar(ataques, reales)) < TOLERANCIA_S


def test_escala_cromatica_completa():
    notas = [(0.3 + 0.25 * i, midi_a_hz(40 + i), 0.5) for i in range(13)]
    x, reales = secuencia(notas, 0.3 + 0.25 * 13 + 0.8, recorte_graves=0.6)
    ataques, _ = analizar(x)

    assert [a.nota.midi for a in ataques] == list(range(40, 53))
    assert max(abs(e) for e in emparejar(ataques, reales)) < TOLERANCIA_S


def test_ligado_sin_golpe_de_pua_tambien_cuenta_como_ataque():
    """Hammer-on: la envolvente no se reinicia, solo cambia la frecuencia.

    El flujo espectral lo detecta igual porque los armonicos se mudan a bins
    nuevos, y eso cuenta como energia nueva. Por eso no hace falta un segundo
    disparador por cambio de pitch.
    """
    duracion, cambio = 1.2, 0.35
    n = int(duracion * SR)
    t = np.arange(n) / SR
    f1, f2 = midi_a_hz(64), midi_a_hz(67)
    frecuencia = np.where(t < cambio, f1, f2)
    fase = 2 * np.pi * np.cumsum(frecuencia) / SR   # continua: no hay click
    rng = np.random.default_rng(3)
    onda = np.zeros(n)
    for k in range(1, 8):
        onda += (0.85 ** (k - 1)) * np.exp(-1.2 * (1 + 0.35 * (k - 1)) * t) \
            * np.sin(k * fase + rng.uniform(0, 2 * np.pi))
    onda *= 0.12 / np.max(np.abs(onda))

    x = np.zeros(int(1.8 * SR))
    x[int(0.3 * SR):int(0.3 * SR) + n] += onda
    x = (x + rng.normal(0, 0.0012, len(x))).astype(np.float32)

    ataques, _ = analizar(x)
    assert [a.nota.nombre for a in ataques] == ["E4", "G4"]
    assert abs(ataques[0].t - 0.3) < TOLERANCIA_S
    assert abs(ataques[1].t - (0.3 + cambio)) < TOLERANCIA_S


def test_solo_ruido_no_produce_ataques():
    x = np.random.default_rng(3).normal(0, 0.0015, int(6 * SR)).astype(np.float32)
    ataques, analizador = analizar(x)
    assert ataques == []
    assert analizador.descartados == 0


def test_silencio_absoluto_no_produce_ataques():
    ataques, _ = analizar(np.zeros(int(2 * SR), dtype=np.float32))
    assert ataques == []


@pytest.mark.parametrize("bloque", [128, 333, 512, 1024, 4096])
def test_el_resultado_no_depende_del_tamano_de_bloque(bloque):
    """El reloj del analizador es el conteo de muestras, no el de pared.

    sounddevice puede entregar bloques de tamaño variable y pygame consume la
    cola a 60 fps, asi que el troceado no debe mover ni un timestamp.
    """
    notas = [(0.4 + 0.35 * i, midi_a_hz(m), 0.5)
             for i, m in enumerate(CUERDAS_ESTANDAR)]
    x, _ = secuencia(notas, 3.2, recorte_graves=0.7)

    referencia, _ = analizar(x, bloque=SALTO)
    obtenidos, _ = analizar(x, bloque=bloque)
    assert [(a.t, a.nota.midi) for a in obtenidos] == \
        [(a.t, a.nota.midi) for a in referencia]


def test_los_timestamps_crecen_y_siguen_el_reloj_de_muestras():
    notas = [(0.4 + 0.3 * i, midi_a_hz(m), 0.45)
             for i, m in enumerate(CUERDAS_ESTANDAR)]
    x, _ = secuencia(notas, 3.0, recorte_graves=0.7)
    ataques, analizador = analizar(x)

    tiempos = [a.t for a in ataques]
    assert tiempos == sorted(tiempos)
    assert analizador.t_actual == pytest.approx(
        (len(x) // SALTO) * SALTO / SR)
    assert all(0.0 <= t <= analizador.t_actual for t in tiempos)


def test_la_puerta_de_ruido_es_configurable():
    """Con la puerta muy alta no debe detectar nada; con la normal, si."""
    notas = [(0.4, midi_a_hz(45), 0.6)]
    x, _ = secuencia(notas, 1.5, amplitud=0.03)
    assert analizar(x, umbral_ruido=0.2)[0] == []
    assert len(analizar(x, umbral_ruido=0.003)[0]) == 1


def test_una_puerta_demasiado_alta_se_come_las_notas_debiles():
    """Documenta el modo de falla que hay que diagnosticar con --umbral.

    Si el microfono entrega las cuerdas graves muy debiles, la puerta por
    defecto las descarta antes de que YIN las vea: no es un fallo del detector
    de pitch sino de calibracion del nivel de entrada.
    """
    notas = [(0.5 + 0.6 * i, midi_a_hz(midi), 0.55)
             for i, midi in enumerate(CUERDAS_ESTANDAR)]
    x, _ = secuencia(notas, 4.8, recorte_graves=1.0, amplitud=0.012)
    assert len(analizar(x, umbral_ruido=0.003)[0]) < 6
    assert len(analizar(x, umbral_ruido=0.0015)[0]) == 6


def test_ataque_sin_pitch_claro_se_descarta_y_se_cuenta():
    """Un golpe en la caja de la guitarra no es una nota."""
    rng = np.random.default_rng(9)
    golpe = rng.normal(0, 0.25, int(0.09 * SR)) * np.exp(
        -np.linspace(0, 9, int(0.09 * SR)))
    x = np.zeros(int(1.5 * SR))
    x[int(0.4 * SR):int(0.4 * SR) + len(golpe)] += golpe
    x = (x + rng.normal(0, 0.0012, len(x))).astype(np.float32)

    ataques, analizador = analizar(x)
    assert ataques == []
    assert analizador.descartados == 1
