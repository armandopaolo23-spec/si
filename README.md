# Tutor de guitarra tipo juego ritmico

Aplicacion de escritorio que baja una pista de notas en pantalla, escucha la
guitarra acustica por el microfono de la laptop y solo avanza si la nota suena
correcta.

Este repositorio tambien contiene `NodoAlertaTempranaMultiriesgo/`, un
proyecto distinto y sin relacion con el tutor.

Estado: **fases 1 (motor de audio) y 2 (modelo de pista) terminadas**.
Faltan las fases 3 a 6 (evaluador, juego, acordes, generador).

## Instalacion

Ubuntu 23.04 y posteriores no dejan instalar con pip en el Python del
sistema (PEP 668), asi que conviene un entorno virtual:

```bash
sudo apt install libportaudio2 python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`pygame` se agrega en la fase 4. Cada vez que abras una terminal nueva hay
que volver a hacer `source .venv/bin/activate`.

## Como verificar la fase 1

Las pruebas no usan microfono ni audio grabado: todas las señales se
sintetizan dentro de `tests/sintesis.py`.

```bash
python3 -m pytest tests/ -q          # 160 pruebas, ~4 s
```

Con la guitarra, una linea por cada pulsacion detectada:

```bash
python3 detector_notas.py --lista        # ver dispositivos de entrada
python3 detector_notas.py                # modo ataques
```

Si falla al abrir el dispositivo, el error dice a que frecuencia lo declara
el sistema; en ese caso `python3 detector_notas.py --sr 48000`.

```
   t (s)  nota            Hz    cents   conf    nivel
   1.243  E2 (Mi2)     82.35     -1.3   0.98   0.0412
   1.836  A2 (La2)    110.12     +1.9   0.97   0.0388
```

Al salir con Ctrl+C imprime el nivel maximo registrado. **Si con la 6a cuerda
no pasa de ~0.01, el microfono esta cortando los graves**: acerca la laptop a
la boca de la guitarra, sube la ganancia de entrada, o baja la puerta de ruido
con `--umbral 0.0015`.

Para comprobar que el microfono capta bien cada cuerda y para afinar:

```bash
python3 detector_notas.py --afinador
```

Que conviene probar a mano:

- Las seis cuerdas al aire: deben salir E2, A2, D3, G3, B3, E4.
- Una nota sostenida 3 segundos: **una sola linea**, no una por ventana.
- Repicar la misma cuerda sin dejarla apagar: una linea por golpe.
- Guitarra en silencio con ruido de ambiente: ninguna linea. Si aparecen,
  sube `--umbral`.
- Un golpe en la caja: no debe salir nota; se cuenta como descartado.

## Como verificar la fase 2

```bash
python3 mostrar_pista.py pistas/01_cuerdas_al_aire.json
python3 mostrar_pista.py pistas/*.json        # revisar las tres
```

Imprime la linea de tiempo de la pista: instante, pulso, duracion, notas y
digitacion sugerida de cada evento.

Si la pista tiene errores, los informa **todos** de una vez con el numero de
evento, y sale con codigo 1. Las pistas se escriben a mano, asi que se valida:
tipos de cada campo, rango de notas que el detector puede oir, digitaciones
que de verdad produzcan el pitch pedido, orden temporal, y acordes con nombre
y al menos dos notas.

## Formato de pista

```json
{
  "titulo": "Ejercicio 1 - cuerdas al aire",
  "bpm": 60,
  "afinacion": ["E2", "A2", "D3", "G3", "B3", "E4"],
  "eventos": [
    {"t": 0.0, "dur": 1.5, "tipo": "nota", "midi": 40, "cuerda": 6, "traste": 0},
    {"t": 2.0, "dur": 1.8, "tipo": "acorde", "nombre": "Em",
     "notas": [40, 47, 52, 55, 59, 64]}
  ]
}
```

- `t` y `dur` en segundos. `t` es el instante del ataque y es lo que califica
  el evaluador; `dur` es cuanto deberia sonar y sirve para dibujar la nota.
- La `dur` de un evento **puede** pisar el `t` del siguiente: una cuerda sigue
  sonando mientras se toca la que viene. Lo que no se permite es que dos
  eventos compartan el mismo `t`; dos notas simultaneas son un `acorde`.
- `cuerda` (1 = la mas aguda) y `traste` son opcionales y solo sugieren una
  digitacion. La deteccion por frecuencia no distingue en que cuerda se toco,
  asi que el evaluador acepta cualquier digitacion que produzca el pitch. Si
  se incluyen, tienen que ser coherentes con `midi` y con `afinacion`.
- `afinacion` es opcional; por defecto la estandar.
- Rango valido de notas: D2 (MIDI 38) a D6 (MIDI 86), derivado de los limites
  del detector. Una nota fuera de ahi seria imposible de acertar.

## Estructura

```
audio/
  notas.py       frecuencia <-> MIDI <-> nombre de nota, cents
  yin.py         deteccion de pitch (YIN sobre numpy)
  onset.py       deteccion de ataques por flujo espectral
  analizador.py  canalizacion pura: bloques de muestras -> ataques con nota
  captura.py     envoltorio de sounddevice (unico modulo que lo importa)
  calibracion.py medida de umbrales contra el microfono real
nucleo/
  pista.py       modelo de pista: carga y validacion del JSON
pistas/
  01_cuerdas_al_aire.json      seis cuerdas al aire, 60 bpm
  02_escala_do_mayor.json      escala de Do mayor, 80 bpm
  03_acordes_y_melodia.json    Em Am C G con melodia, 90 bpm
tests/
  sintesis.py    generador de pulsaciones de guitarra para las pruebas
detector_notas.py  CLI de diagnostico (ataques, afinador, calibrar)
mostrar_pista.py   CLI que imprime la linea de tiempo de una pista
```

`audio/analizador.py` y todo lo que esta debajo son funciones puras sobre
arrays: no importan `sounddevice` ni `pygame`, asi que las fases siguientes
se pueden testear sin audio ni ventana.

## Numeros medidos

| | |
|---|---|
| Exactitud de pitch, seis cuerdas al aire | < 0.2 cents |
| Exactitud con el fundamental ausente (E2 sin 82 Hz) | octava correcta, < 1 cent |
| Error de timestamp del ataque | < 20 ms (sesgo ~ -5 ms) |
| Retraso entre el golpe y la emision del evento | ~70 ms |
| CPU | 4.7 % de un nucleo (0.54 ms por ventana de 11.6 ms) |

## Parametros ajustables

En `audio/analizador.py` y `audio/onset.py`, todos como argumentos del
constructor:

| Parametro | Defecto | Que hace |
|---|---|---|
| `umbral_ruido` | 0.003 | Puerta de ruido RMS. Bajar si el micro entrega poco nivel. |
| `factor` (onset) | 6.0 | Cuantas veces la mediana reciente del flujo hay que superar. Bajar si pierde pulsaciones suaves. |
| `refractario_s` | 0.08 | Minimo entre dos ataques. Subir si un golpe cuenta doble. |
| `retardo_onset_s` | 0.014 | Correccion del timestamp. Recalibrar contra un metronomo en la fase 4. |
| `saltos_espera` / `saltos_pitch` | 3 / 3 | Cuanto esperar y cuantas lecturas promediar. Bajar da feedback mas rapido y pitch menos estable. |
