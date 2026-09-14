# Tutor de guitarra tipo juego ritmico

Aplicacion de escritorio que baja una pista de notas en pantalla, escucha la
guitarra acustica por el microfono de la laptop y solo avanza si la nota suena
correcta.

Este repositorio tambien contiene `NodoAlertaTempranaMultiriesgo/`, un
proyecto distinto y sin relacion con el tutor.

Estado: **fases 1 (motor de audio), 2 (modelo de pista) y 3 (evaluador)
terminadas**. Faltan las fases 4 a 6 (juego, acordes, generador).

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
python3 -m pytest tests/ -q          # 229 pruebas, ~5 s
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

Para entender **por que** disparo cada ataque:

```bash
python3 detector_notas.py --detalle
```

Agrega tres columnas: `dt` (hueco desde el ataque anterior), `flujo` y
`umbral`, y el `margen` entre los dos. Un ataque real de guitarra dispara con
margen de 6x a 30x; un margen cerca de 1x es un falso positivo al filo del
umbral. Es la unica forma de distinguir "el detector dispara de mas" de
"se toco de mas".

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

## Como verificar la fase 3

El evaluador es logica pura, asi que se prueba con `pytest`. Para verlo
funcionando, `--simular` toca una pista con detecciones inventadas y muestra
como la calificaria, sin microfono:

```bash
python3 mostrar_pista.py pistas/02_escala_do_mayor.json --simular todos
python3 mostrar_pista.py pistas/01_cuerdas_al_aire.json --simular tarde
python3 mostrar_pista.py pistas/02_escala_do_mayor.json --simular tarde \
    --tolerancia-ms 50          # apretar la ventana y ver que ya no pasa
```

Perfiles: `perfecto`, `tarde` (80 ms tarde de forma sistematica),
`desafinado` (25 cents bajo, como la 4a cuerda real) y `desprolijo`.

La simulacion corre el evaluador como lo hara el juego: bucle de 60 fps y
detecciones que llegan con el retardo real del motor. Eso es lo que prueba
que el retardo no inventa fallos cuando se toca bien.

## Tolerancias del evaluador

| | Defecto | Que significa |
|---|---|---|
| Temporal | +-120 ms | Cuanto antes o despues del `t` esperado vale el golpe. |
| Afinacion | +-35 cents | Cuanta desviacion se perdona. +-50 seria "cualquier cosa que redondee a la nota correcta". |

Ambas configurables en `nucleo/evaluador.py` (`Tolerancias`) y desde la CLI.
35 cents es generoso a proposito: una guitarra acustica con las cuerdas algo
bajas da desviaciones de 15 a 25 cents constantes, y con una ventana mas
estrecha el juego marcaria fallo por la afinacion del instrumento en vez de
por como se toca.

La desviacion se mide en cents contra la frecuencia pedida, no comparando
nombres de nota. Una nota 55 cents alta de E2 se lee como F2 a -45 cents:
comparando nombres parece estar a 45 y pasaria, medida contra lo pedido esta
a 55 y no pasa.

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
  evaluador.py   decide acierto, fallo o nota de mas; puntaje y racha
  simulacion.py  toca una pista con detecciones inventadas, para probar
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
| `factor` (onset) | 6.0 | Cuantas veces la mediana reciente del flujo hay que superar. Bajar si pierde pulsaciones suaves, subir si dispara de mas. |
| `refractario_s` | 0.08 | Minimo entre dos ataques. Subir si un golpe cuenta doble. |
| `retardo_onset_s` | 0.014 | Correccion del timestamp. Recalibrar contra un metronomo en la fase 4. |
| `saltos_espera` / `saltos_pitch` | 3 / 3 | Cuanto esperar y cuantas lecturas promediar. Bajar da feedback mas rapido y pitch menos estable. |
